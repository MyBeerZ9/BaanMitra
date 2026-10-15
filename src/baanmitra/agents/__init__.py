"""BaanMitra agents.

Imports are lazy on purpose: importing `baanmitra.agents` must not pull in
`watchdog` / `triager`, otherwise running

    python -m baanmitra.agents.watchdog

triggers a runpy "found in sys.modules" warning.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # editor/type-checker friendliness only
    from . import triager, watchdog

__all__ = ["watchdog", "triager"]


def __getattr__(name):
    if name in __all__:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(name)
