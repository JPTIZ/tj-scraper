"""Helper functions for tj_scraper's unit tests."""
from collections.abc import Collection
from typing import Any, Optional, TypeVar

import pytest

from tj_scraper.process import ProcessJSON, get_process_id


def has_same_entries(
    lhs: Collection[ProcessJSON], rhs: Collection[ProcessJSON]
) -> bool:
    """
    Checks if `lhs` and `rhs` contain the same entries even if they're on
    different positions.
    """
    assert sorted(list(lhs), key=get_process_id) == sorted(
        list(rhs), key=get_process_id
    )
    return True


def ignore_unused(
    *args: Any, reason: str = "Pyright emmits an info that LSP is not able to ignore."
) -> None:
    """Shuts up language-servers' warnings about an unused variable/function/fixture."""
    _ = args, reason


Key = TypeVar("Key")
Value = TypeVar("Value")


def reverse_lookup(dict_: dict[Key, Value], value: Value) -> Optional[Key]:
    """Returns which key has a certain value."""
    for key, value_ in dict_.items():
        if value_ == value:
            return key
    return None
