from __future__ import annotations

from typing import Any

__all__ = []
__version__: str


def main() -> None:
    import argparse
    from functools import partial

    import anyio

    from pyright_stubgen.stubgen import run_pyright_stubgen

    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--module", type=str, help="module name", required=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose")
    parser.add_argument("--ignore-error", action="store_true", help="ignore error")
    parser.add_argument("--concurrency", type=int, default=5, help="concurrency")
    parser.add_argument("--out", type=str, default=None, help="output directory")

    args = parser.parse_args()

    stubgen = partial(
        run_pyright_stubgen,
        args.module,
        verbose=args.verbose,
        ignore_error=args.ignore_error,
        concurrency=args.concurrency,
        out_dir=args.out,
    )
    anyio.run(stubgen)


def __getattr__(name: str) -> Any:
    if name == "__version__":
        from importlib.metadata import version

        _version = version("pyright-stubgen")
        globals()["__version__"] = _version
        return _version

    error_msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(error_msg)
