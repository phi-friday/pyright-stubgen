from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import anyio

from pyright_stubgen.base import (
    Config,
    StrictOptions,
    create_default_parser,
    create_options_from_parser,
    run_stubgen,
)

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
    parser = create_default_parser()

    args = parser.parse_args()
    options = create_options_from_parser(args)
    stubgen = partial(
        run_stubgen, args.module, config=_PYRIGHT_CONFIG, naive_options=options
    )
    anyio.run(stubgen)
