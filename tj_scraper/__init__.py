"""A package of tools for brazilian Tribunal de Justiça pages."""
from importlib_metadata import version

from typing import cast, Callable

_version = cast(Callable[[str], str], version)

__version__ = _version(__package__)
__all__ = [
    "__version__",
]
