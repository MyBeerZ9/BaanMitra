"""BaanMitra API (lazy import of `main`)."""

__all__ = ["main"]


def __getattr__(name):
    if name == "main":
        import importlib
        return importlib.import_module(".main", __name__)
    raise AttributeError(name)
