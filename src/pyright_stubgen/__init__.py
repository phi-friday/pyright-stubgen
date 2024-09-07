from __future__ import annotations

from typing import Any

__all__ = []
__version__: str


def __getattr__(name: str) -> Any:
    if name == "__version__":
        from importlib.metadata import version

        _version = version("pyright-stubgen")
        globals()["__version__"] = _version
        return _version

    error_msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(error_msg)
