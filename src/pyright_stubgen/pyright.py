from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import anyio

from pyright_stubgen.base import Config, Options, StrictOptions, run_stubgen

__all__ = []

_PYRIGHT_DEFAULT_OUTPUT = Path("typings")


def _create_stub_command(module: str, *, options: StrictOptions) -> list[str]:
    command = [sys.executable, "-m", "pyright", "--createstub", module]
    if options["verbose"]:
        command.append("--verbose")
    return command


_PYRIGHT_CONFIG = Config(
    default_out_dir=_PYRIGHT_DEFAULT_OUTPUT, command_factory=_create_stub_command
)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--module", type=str, help="module name", required=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose")
    parser.add_argument("--ignore-error", action="store_true", help="ignore error")
    parser.add_argument("--concurrency", type=int, default=5, help="concurrency")
    parser.add_argument("--out", type=str, default="out", help="output directory")

    args = parser.parse_args()
    options: Options = {
        "ignore_error": args.ignore_error,
        "verbose": args.verbose,
        "concurrency": args.concurrency,
        "out_dir": args.out,
        "args": args,
    }

    stubgen = partial(
        run_stubgen, args.module, config=_PYRIGHT_CONFIG, naive_options=options
    )
    anyio.run(stubgen)
