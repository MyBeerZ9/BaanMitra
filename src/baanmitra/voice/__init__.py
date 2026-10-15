"""BaanMitra voice providers (lazy imports)."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import stt, telephony, tts

__all__ = ["tts", "stt", "telephony"]


def __getattr__(name):
    if name in __all__:
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(name)
