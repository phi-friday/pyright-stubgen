from __future__ import annotations

import logging
import subprocess
import sys
from asyncio import Queue
from functools import partial
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import anyio
from typing_extensions import TypedDict, Unpack

if TYPE_CHECKING:
    from os import PathLike


__all__ = ["run_pyright_stubgen"]

_OUTPUT = Path("typings")
logger = logging.getLogger("pyright_stubgen")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))


class Options(TypedDict, total=False):
    ignore_error: bool
    verbose: bool
    concurrency: int | anyio.Semaphore


class StrictOptions(TypedDict, total=True):
    ignore_error: bool
    verbose: bool
    concurrency: anyio.Semaphore


def _ensure_options(**naive_options: Unpack[Options]) -> StrictOptions:
    result: dict[str, Any] = dict(naive_options)

    for key, default in [
        ("ignore_error", False),
        ("verbose", False),
        ("concurrency", 5),
    ]:
        result.setdefault(key, default)

    if isinstance(result["concurrency"], int):
        result["concurrency"] = anyio.Semaphore(result["concurrency"])

    return cast(StrictOptions, result)


async def run_pyright_stubgen(name: str, **naive_options: Unpack[Options]) -> None:
    """generate stubs using pyright"""
    options = _ensure_options(**naive_options)
    spec = find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        error_msg = f"Module '{name}' not found"
        raise ModuleNotFoundError(error_msg)

    root = Path(spec.submodule_search_locations[0])
    await _run_pyright_stubgen_process(name, **options)

    stubgen = partial(_run_pyright_stubgen, **options)
    queue: Queue[anyio.Path] = Queue()

    async with anyio.create_task_group() as task_group:
        for path in root.glob("**/*.py"):
            task_group.start_soon(stubgen, path, root, queue)
        for path in root.glob("**/*.pyi"):
            task_group.start_soon(stubgen, path, root, queue)

    while not queue.empty():
        target = await queue.get()
        await _rm_empty_directory(target)


async def _run_pyright_stubgen(
    path: str | PathLike[str],
    root: str | PathLike[str],
    queue: Queue[anyio.Path],
    **naive_options: Unpack[Options],
) -> None:
    options = _ensure_options(**naive_options)

    apath, aroot = anyio.Path(path), anyio.Path(root)
    apath, aroot = await apath.resolve(), await aroot.resolve()

    target = anyio.Path(_OUTPUT) / apath.relative_to(aroot.parent)
    target = target.with_name(target.stem)
    await queue.put(target)

    pyi = target.with_suffix(".pyi")
    if await pyi.exists():
        logger.info("Already generated stub %s", pyi)
        return
    module = _path_to_module(path, root)

    await _run_pyright_stubgen_process(module, **options)


async def _run_pyright_stubgen_process(
    module: str, **naive_options: Unpack[Options]
) -> None:
    options = _ensure_options(**naive_options)
    command = _create_stub_command(module, verbose=options["verbose"])

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


def _create_stub_command(module: str, *, verbose: bool) -> list[str]:
    command = [sys.executable, "-m", "pyright", "--createstub", module]
    if verbose:
        command.append("--verbose")
    return command


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
