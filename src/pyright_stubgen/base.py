from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from asyncio import Queue
from dataclasses import dataclass
from functools import partial
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import anyio
from typing_extensions import TypedDict, Unpack

if TYPE_CHECKING:
    from os import PathLike


__all__ = []

logger = logging.getLogger("pyright_stubgen")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))


class CommandFactory(Protocol):
    def __call__(self, module: str, *, options: StrictOptions) -> list[str]: ...


@dataclass(frozen=True)
class Config:
    default_out_dir: Path[str]
    command_factory: CommandFactory


class Options(TypedDict, total=False):
    ignore_error: bool
    verbose: bool
    concurrency: int | anyio.Semaphore
    out_dir: str | PathLike[str]


class StrictOptions(TypedDict, total=True):
    ignore_error: bool
    verbose: bool
    concurrency: anyio.Semaphore
    out_dir: Path[str]


def _ensure_options(
    naive_options: Options | StrictOptions, config: Config
) -> StrictOptions:
    if naive_options.get("_strict_options_", False) is True:
        return cast(StrictOptions, naive_options)

    result: dict[str, Any] = dict(naive_options)

    for key, default in [
        ("ignore_error", False),
        ("verbose", False),
        ("concurrency", 5),
        ("out_dir", config.default_out_dir),
    ]:
        result.setdefault(key, default)

    if isinstance(result["concurrency"], int):
        result["concurrency"] = anyio.Semaphore(result["concurrency"])
    if result["out_dir"] is None:
        result["out_dir"] = config.default_out_dir
    result["out_dir"] = Path(result["out_dir"])

    result["_strict_options_"] = True
    return cast(StrictOptions, result)


async def run_stubgen(
    name: str, *, config: Config, **naive_options: Unpack[Options]
) -> None:
    options = _ensure_options(naive_options, config=config)
    package = name.split(".", 1)[0] if "." in name else name
    spec = find_spec(name, package)

    if spec is None or not spec.origin:
        error_msg = f"Module '{name}' not found"
        raise ModuleNotFoundError(error_msg)

    root = Path(spec.origin)
    if root.name == "__init__.py":
        root = root.parent
    await _run_stubgen_process(name, options, config)

    stubgen = partial(_run_stubgen, options=options)
    queue: Queue[anyio.Path] = Queue()

    async with anyio.create_task_group() as task_group:
        for path in root.glob("**/*.py"):
            task_group.start_soon(stubgen, path, root, queue, config)
        for path in root.glob("**/*.pyi"):
            task_group.start_soon(stubgen, path, root, queue, config)

    while not queue.empty():
        target = await queue.get()
        await _rm_empty_directory(target)

    _run_stubgen_outdir(package, options, config)


def _run_stubgen_outdir(
    package: str, options: Options | StrictOptions, config: Config
) -> None:
    options = _ensure_options(options, config)
    if options["out_dir"] == config.default_out_dir:
        return

    origin_dir = config.default_out_dir / package
    out_dir = options["out_dir"]
    target_dir = out_dir / package
    origin_dir, target_dir = origin_dir.resolve(), target_dir.resolve()

    temp_dir: Path[str] | None = None
    if target_dir.exists():
        temp_dir = target_dir.with_suffix(".bak")
        shutil.move(target_dir, temp_dir)

    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(origin_dir, target_dir)
    except:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        if temp_dir and temp_dir.exists():
            shutil.move(temp_dir, target_dir)
        raise
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)


async def _run_stubgen(
    path: str | PathLike[str],
    root: str | PathLike[str],
    queue: Queue[anyio.Path],
    options: Options | StrictOptions,
    config: Config,
) -> None:
    options = _ensure_options(options, config)

    apath, aroot = anyio.Path(path), anyio.Path(root)
    apath, aroot = await apath.resolve(), await aroot.resolve()

    target = anyio.Path(config.default_out_dir) / apath.relative_to(aroot.parent)
    target = target.with_name(target.stem)
    await queue.put(target)

    pyi = target.with_suffix(".pyi")
    if await pyi.exists():
        logger.info("Already generated stub %s", pyi)
        return
    module = _path_to_module(path, root)

    await _run_stubgen_process(module, options, config)


async def _run_stubgen_process(
    module: str, options: Options | StrictOptions, config: Config
) -> None:
    options = _ensure_options(options, config)
    command = config.command_factory(module, options=options)

    async with options["concurrency"]:
        process = await anyio.run_process(
            command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    logger.info(process.stdout.decode())
    if process.stderr:
        logger.error(process.stderr.decode())
    if options["ignore_error"]:
        process.check_returncode()


def _path_to_module(path: str | PathLike[str], root: str | PathLike[str]) -> str:
    path, root = Path(path).resolve(), Path(root).resolve()
    path = path.relative_to(root.parent)
    path = path.with_name(path.stem)
    return path.as_posix().replace("/", ".")


async def _rm_empty_directory(target: anyio.Path) -> None:
    if not (await target.exists()):
        return

    if not (await target.is_dir()):
        return

    flag = False
    async for file in target.glob("*"):
        if await file.is_file():
            flag = True
            continue
        await _rm_empty_directory(file)
    if flag:
        return

    logger.info("Incorretly generated stubs found, removing directory %s", target)
    await target.rmdir()
