"""Related to a TJ's juridical process."""
from dataclasses import dataclass
from typing import Optional, Union


IdRange = Union[tuple[str, str], str]


@dataclass
class Process:
    """The information we want from a single process from a TJ."""

    process_id: str
    uf: str  # pylint: disable=invalid-name
    subject: str


def id_or_range(process_id: str) -> Union[tuple[str, str], str]:
    """Evaluates a "<start>..<end>" or a "<process id>" string."""
    start, *end = process_id.split("..")
    if end:
        return start, end[0]
    return start


def to_parts(process_id: str) -> list[str]:
    """Splits process ID's number parts"""
    return process_id.replace("-", ".").split(".")


def cap_with_carry(number: int, limit: int) -> tuple[int, int]:
    """
    Bounds `number` to the limit specified and returns it and a carry value if
    number exceeds the limit.
    """
    return number % limit, number // limit


def next_(range_: tuple[str, str]) -> Optional[str]:
    """
    Returns the next valid process ID within specified range.

    Example: 2021.001.150080-0 -> 2021.001.150080-1.
             0169689-05.2021.8.19.0001 -> 0169689-05.2021.8.19.0002
    """
    start, end = ([int(part) for part in to_parts(id_)] for id_ in range_)

    if not any(x < y for x, y in zip(start, end)):
        return None

    year, class_1, class_2, digit = start
    digit, carry = cap_with_carry(digit + 1, 10)
    class_2, carry = cap_with_carry(class_2 + carry, 1000000)
    class_1, carry = cap_with_carry(class_1 + carry, 1000)
    year += carry

    return f"{year:04}.{class_1:03}.{class_2:06}-{digit:1}"


def all_from(range_: Union[tuple[str, str], str]):
    """Yields all valid process IDs from range (or the provided ID if not a range)."""
    if isinstance(range_, str):
        yield range_
        return

    assert not isinstance(range_, str)
    start, end = range_
    yield start

    while (start_ := next_((start, end))) is not None:
        start = start_
        yield start
