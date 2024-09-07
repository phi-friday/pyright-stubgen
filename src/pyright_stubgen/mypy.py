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

_MYPY_DEFAULT_OUTPUT = Path("out")


def _create_stub_command(module: str, *, options: StrictOptions) -> list[str]:
    args = options["args"]
    stubgen = Path(sys.executable).with_name("stubgen")
    command = [str(stubgen), "-m", module]
    if args.no_analysis:
        command.append("--no-analysis")
    if args.inspect_mode:
        command.append("--inspect-mode")
    if args.include_private:
        command.append("--include-private")
    if args.include_docstrings:
        command.append("--include-docstrings")
    if options["verbose"]:
        command.append("--verbose")
    return command


_MYPY_CONFIG = Config(
    default_out_dir=_MYPY_DEFAULT_OUTPUT, command_factory=_create_stub_command
)


def main() -> None:
    parser = create_default_parser()
    parser.add_argument("--no-analysis", action="store_true", help="no analysis")
    parser.add_argument("--inspect-mode", action="store_false", help="inspect mode")
    parser.add_argument(
        "--include-private", action="store_true", help="include private"
    )
    parser.add_argument(
        "--include-docstrings", action="store_true", help="include docstrings"
    )

    args = parser.parse_args()
    options = create_options_from_parser(args)
    stubgen = partial(
        run_stubgen, args.module, config=_MYPY_CONFIG, naive_options=options
    )
    anyio.run(stubgen)
