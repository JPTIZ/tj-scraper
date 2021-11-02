"""A package of tools for brazilian Tribunal de Justiça pages."""
from collections.abc import Collection

from importlib_metadata import version

from .process import Process


def processes_by_subject(words: Collection[str]) -> Collection[Process]:
    """Search for processes that contain the given words on its subject."""
    print(words)
    return []


__version__ = version(__package__)
__all__ = [
    "__version__",
]
