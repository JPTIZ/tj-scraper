"""Related to a TJ's juridical process."""
from typing import Optional, Union


from deprecated import deprecated


IdRange = Union[tuple[str, str], str]


Value = str
Object = dict[str, str]
ProcessField = Union[str, list[Object]]


# class ProcessRequiredFields(TypedDict):
#     idProc: str
#
#
# class Process(ProcessRequiredFields, total=False):
#     codProc: str
#     txtAssunto: str


Process = dict[str, ProcessField]


REAL_ID_FIELD = "codProc"
DB_FIELD = REAL_ID_FIELD


@deprecated(
    reason="Should only use get_id, as DB ID is the same as the real process ID now."
)
def get_db_id(process: Process) -> str:
    """Gets the process ID used as a key to the database."""
    return str(process[DB_FIELD])


@deprecated(
    reason="Should only use get_id, as DB ID is the same as the real process ID now."
)
def get_real_id(process: Process) -> str:
    """Gets the process ID used as a unique identifier given by TJ."""
    return get_id(process)


def get_id(process: Process) -> str:
    """Gets the process ID used as a unique identifier given by TJ."""
    return str(process[REAL_ID_FIELD])


def id_or_range(process_id: str) -> IdRange:
    """Evaluates a "<start>..<end>" or a "<process id>" string."""
    start, *end = process_id.split("..")

    if len(end) > 1:
        raise ValueError(
            f'Invalid range format. Expected just one "..", got "{process_id}".'
        )

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


def all_from(range_: IdRange):
    """Yields all valid process IDs from range (or the provided ID if not a range)."""
    if isinstance(range_, str):
        yield range_
        return

    assert not isinstance(range_, str)
    start, end = range_
    assert int("".join(to_parts(start))) <= int(
        "".join(to_parts(end))
    ), "End should be higher than start."
    yield start

    while (start_ := next_((start, end))) is not None:
        start = start_
        yield start


def has_words_in_subject(data: Process, words: list[str]):
    """Checks if data's subject field contains any of certains words."""
    assunto = data.get("txtAssunto", "Sem Assunto")
    if isinstance(assunto, list):
        assunto = " ".join(map(str, assunto))
    assunto = assunto.lower()
    has = any(word.lower() in assunto for word in words)
    # print(f"{has} for {words} in {assunto}")
    return has
