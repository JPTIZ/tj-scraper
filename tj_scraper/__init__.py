"""A package of tools for brazilian Tribunal de Justiça pages."""
from typing import Callable, cast

from importlib_metadata import version

_version = cast(Callable[[str], str], version)

__version__ = _version(__package__)
__all__ = [
    "__version__",
]
