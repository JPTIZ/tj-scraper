"""Related to a TJ's juridical process."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Mapping, NamedTuple, Optional, Union

from .errors import InvalidProcessNumber


@dataclass
class SourceUnit:
    name: str
    code: int


@dataclass(frozen=True)
class TJ:
    name: str
    code: int
    cnj_endpoint: str
    main_endpoint: str
    source_units: list[SourceUnit]


@dataclass
class TJInfo:
    tjs: Mapping[str, TJ]


class CNJProcessNumber(NamedTuple):
    number: int
    digits: int
    year: int
    tr_code: int
    source_unit: int  # 4 digits


class TJRJProcessNumber(NamedTuple):
    year: int
    source_unit: int  # 3 digits
    number: int
    digit: int


class IdRange(NamedTuple):
    start: CNJProcessNumber
    end: CNJProcessNumber


Value = str
Object = Mapping[str, str]
ProcessField = Union[str, list[Object]]


# class ProcessRequiredFields(TypedDict):
#     idProc: str
#
#
# class Process(ProcessRequiredFields, total=False):
#     codProc: str
#     txtAssunto: str


ProcessJSON = Mapping[str, ProcessField]


REAL_ID_FIELD = "codCnj"


def get_process_id(process: ProcessJSON) -> str:
    """Gets the process ID used as a unique identifier given by TJ."""
    return str(process[REAL_ID_FIELD])


def id_or_range(process_id: str) -> IdRange | CNJProcessNumber:
    """Evaluates a "<start>..<end>" or a "<process id>" string."""
    start, *end = process_id.split("..")

    if len(end) > 1:
        raise ValueError(
            f'Invalid range format. Expected just one "..", got "{process_id}".'
        )

    if end:
        return IdRange(to_cnj_number(start), to_cnj_number(end[0]))
    return to_cnj_number(start)


def to_cnj_number(process_id: str) -> CNJProcessNumber:
    """Evaluates a single string into a CNJ process number."""
    import re

    matched = re.fullmatch(r"(\d{7})-(\d{2}).(\d{4}).8.(\d{2})\.(\d{4})", process_id)

    if matched is None:
        raise InvalidProcessNumber(
            f'A string "{process_id}" não corresponde a um número válido do CNJ.'
        )
    return CNJProcessNumber(*map(int, matched.groups()))


def cap_with_carry(number: int, limit: int) -> tuple[int, int]:
    """
    Bounds `number` to the limit specified and returns it and a carry value if
    number exceeds the limit.
    """
    return number % limit, number // limit


def next_in_range(range_: IdRange, tj: TJ) -> Optional[CNJProcessNumber]:
    """
    Returns the next valid process ID within specified range.

    Example: 0169689-05.2021.8.19.0001 -> 0169689-05.2021.8.19.0002
    """
    start, end = range_.start, range_.end

    if not any(x < y for x, y in zip(start, end)):
        return None

    return advance(start, tj=tj)


def iter_in_range(range_: IdRange, tj: TJ) -> Generator[CNJProcessNumber, None, None]:
    """Iters through a process ID range."""
    new_start: Optional[CNJProcessNumber] = range_.start

    while new_start is not None:
        yield new_start

        new_start = next_in_range(IdRange(new_start, range_.end), tj=tj)


def all_from(
    range_: IdRange | CNJProcessNumber, tj: TJ
) -> Generator[CNJProcessNumber, None, None]:
    """Yields all valid process IDs from range (or the provided ID if not a range)."""
    if isinstance(range_, CNJProcessNumber):
        yield range_
        return

    start, end = range_

    assert start < end, "End should be higher than start."

    yield start

    while (start_ := next_in_range(IdRange(start, end), tj=tj)) is not None:
        start = start_
        yield start


def make_cnj_code(number: CNJProcessNumber) -> str:
    return f"{number.number:07}-{number.digits:02}.{number.year:04}.8.{number.tr_code:02}.{number.source_unit:04}"


def next_source_unit(number: CNJProcessNumber, tj: TJ) -> Optional[CNJProcessNumber]:
    """Gets the next process number by advancing the 'source_unit' part."""
    current_unit_index = [unit.code for unit in tj.source_units].index(
        number.source_unit
    )
    try:
        return CNJProcessNumber(
            number=number.number,
            digits=number.digits,
            year=number.year,
            tr_code=number.tr_code,
            source_unit=tj.source_units[current_unit_index + 1].code,
        )
    except IndexError:
        return None


def next_digit(number: CNJProcessNumber) -> Optional[CNJProcessNumber]:
    """Gets the next process number by advancing the 'digits' part."""
    new_digit = number.digits + 1

    if new_digit >= 100:
        return None

    return CNJProcessNumber(
        number=number.number,
        digits=new_digit,
        year=number.year,
        tr_code=number.tr_code,
        source_unit=number.source_unit,
    )


def next_number(number: CNJProcessNumber) -> Optional[CNJProcessNumber]:
    """Gets the next process number by advancing the 'number' part."""
    new_number = number.number + 1

    if new_number >= 1000000:
        return None

    return CNJProcessNumber(
        number=new_number,
        digits=number.digits,
        year=number.year,
        tr_code=number.tr_code,
        source_unit=number.source_unit,
    )


def advance(number: CNJProcessNumber, tj: TJ) -> Optional[CNJProcessNumber]:
    """
    Advances the process number into the next possible (not necessarily
    existing) process number.
    """

    def reset_for(field: str) -> Callable[[CNJProcessNumber], CNJProcessNumber]:
        return lambda number: CNJProcessNumber(**{**number._asdict(), field: 0})

    # Units can be ordered by [known] frequency, so testing digits for the most
    # frequent unit might cut much more work.
    steps = [
        (next_digit, reset_for("digits")),
        (lambda n: next_source_unit(n, tj), reset_for("source_unit")),
        (next_number, reset_for("number")),
    ]

    for (step, reset) in steps:
        new_number = step(number)
        if new_number is not None:
            return new_number
        number = reset(number)

    return None


def has_words_in_subject(data: ProcessJSON, words: list[str]) -> bool:
    """Checks if data's subject field contains any of certains words."""
    assunto = data.get("txtAssunto", "Sem Assunto")
    if isinstance(assunto, list):
        assunto = " ".join(map(str, assunto))
    assunto = assunto.lower()
    has = any(word.lower() in assunto for word in words)
    return has


def load_tj_info(path: Path) -> TJInfo:
    import toml

    with open(path) as f:
        toml_contents = toml.load(f)

    return TJInfo(
        tjs={
            name: TJ(
                name=name,
                code=tj["code"],
                source_units=sorted(
                    [
                        SourceUnit(name=unit["name"], code=unit["code"])
                        for unit in tj["source_units"]
                    ],
                    key=lambda unit: unit.code,
                ),
                cnj_endpoint=tj["cnj_endpoint"],
                main_endpoint=tj["main_endpoint"],
            )
            for name, tj in toml_contents["tjs"].items()
        }
    )


TJ_INFO = load_tj_info(Path(__file__).parent / "tj_info.toml")
TJRJ = TJ_INFO.tjs["rj"]
