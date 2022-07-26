"""Related to a TJ's juridical process."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Mapping, NamedTuple, Optional, Union

from .errors import InvalidProcessNumber


class JudicialSegment(Enum):
    """Judicial segment values according to CNJ number specification."""

    STF = 1  # Supremo Tribunal Federal
    CNJ = 2  # Conselho Nacional de Justiça
    STJ = 3  # Supremo Tribunal de Justiça
    JF = 4  # Justiça Federal
    JT = 5  # Justiça do Trabalho
    JE = 6  # Justiça Eleitoral
    JMU = 7  # Justiça Militar da União
    JEDFT = 8  # Justiça dos Estados e do Distrito Federal e Territórios
    JME = 9  # Justiça Militar dos Estados


@dataclass
class SourceUnit:
    """Abstraction for "Unidade de Origem"."""

    name: str
    code: int


@dataclass(frozen=True)
class TJ:
    """Info about a single TJ."""

    name: str
    code: int
    cnj_endpoint: str
    main_endpoint: str
    source_units: list[SourceUnit]


@dataclass
class TJInfo:
    """General info about TJs."""

    tjs: Mapping[str, TJ]

    def tj_by_code(self, code: int) -> TJ | None:
        """Searches which TJ has code `code`."""
        tjs = [tj for tj in self.tjs.values() if tj.code == code]

        return tjs[0] if tjs else None


class CNJProcessNumber(NamedTuple):
    """A single process number in the format used in CNJ (Unified)."""

    sequential_number: int
    year: int
    segment: JudicialSegment
    tr_code: int
    source_unit: int  # 4 digits

    @property
    def digits(self) -> int:
        """Calculates verification digits."""
        return calculate_digits(
            self.sequential_number,
            self.year,
            self.segment,
            self.tr_code,
            self.source_unit,
        )


class TJRJProcessNumber(NamedTuple):
    """A single process number in the format used in TJ-RJ."""

    year: int
    source_unit: int  # 3 digits
    number: int
    digit: int


@dataclass(frozen=True)
class CNJNumberCombinations:
    """
    Parameters to find possible CNJ numbers in a range of values for NNNNNNN
    part.
    """

    sequence_start: int
    sequence_end: int
    tj: TJ
    year: int
    segment: JudicialSegment

    def __iter__(self) -> Iterator[CNJProcessNumber]:
        """Iters through a process ID range."""
        number: Optional[CNJProcessNumber] = CNJProcessNumber(
            sequential_number=self.sequence_start,
            year=self.year,
            segment=self.segment,
            tr_code=self.tj.code,
            source_unit=self.tj.source_units[0].code,
        )

        while number is not None and number.sequential_number <= self.sequence_end:
            yield number

            number = advance(number, tj=self.tj)


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


def number_or_range(process_id: str) -> CNJNumberCombinations | CNJProcessNumber:
    """Evaluates a "<start>..<end>" or a "<process id>" string."""
    start, *end = process_id.split("..")

    if len(end) > 1:
        raise ValueError(
            f'Invalid range format. Expected just one "..", got "{process_id}".'
        )

    start_number = to_cnj_number(start)

    tjs = [tj for tj in TJ_INFO.tjs.values() if tj.code == start_number.tr_code]

    if not tjs:
        raise ValueError(f"Unknown TR code '{start_number.tr_code}'.")

    tj = tjs[0]

    if end:
        return CNJNumberCombinations(
            start_number.sequential_number,
            to_cnj_number(end[0]).sequential_number,
            tj,
            start_number.year,
            start_number.segment,
        )
    return to_cnj_number(start)


def to_cnj_number(process_id: str) -> CNJProcessNumber:
    """
    Evaluates a single string into a CNJ process number. The digits part is
    unused and calculated automatically.
    """
    import re

    matched = re.fullmatch(r"(\d{7})-(\d{2}).(\d{4}).(\d).(\d{2})\.(\d{4})", process_id)

    if matched is None:
        raise InvalidProcessNumber(
            f'A string "{process_id}" não corresponde a um número válido do CNJ.'
        )

    (number, _, year, segment, tr_code, source_unit) = map(int, matched.groups())

    return CNJProcessNumber(
        number, year, JudicialSegment(segment), tr_code, source_unit
    )


def make_cnj_number_str(number: CNJProcessNumber) -> str:
    """Creates a string in expected CNJ number format."""
    return (
        f"{number.sequential_number:07}"
        f"-{number.digits:02}"
        f".{number.year:04}"
        f".8.{number.tr_code:02}"
        f".{number.source_unit:04}"
    )


def calculate_digits(
    number: int, year: int, segment: JudicialSegment, tr_code: int, source_unit: int
) -> int:
    """Calculates verification digits for the given CNJ number fields."""
    mixed = int(f"{number:07}{year:04}{segment.value}{tr_code:02}{source_unit:04}")
    return 98 - (mixed * 100 % 97)


def make_cnj_number(
    sequential_number: int,
    year: int,
    segment: JudicialSegment,
    tr_code: int,
    source_unit: int,
) -> CNJProcessNumber:
    """
    Returns a complete CNJ process number with its verification digits
    calculated accordinly.
    """
    return CNJProcessNumber(
        sequential_number=sequential_number,
        year=year,
        segment=segment,
        tr_code=tr_code,
        source_unit=source_unit,
    )


def next_source_unit(number: CNJProcessNumber, tj: TJ) -> Optional[CNJProcessNumber]:
    """Gets the next process number by advancing the 'source_unit' part."""
    current_unit_index = [unit.code for unit in tj.source_units].index(
        number.source_unit
    )
    try:
        return make_cnj_number(
            sequential_number=number.sequential_number,
            year=number.year,
            segment=number.segment,
            tr_code=number.tr_code,
            source_unit=tj.source_units[current_unit_index + 1].code,
        )
    except IndexError:
        return None


def next_number(number: CNJProcessNumber) -> Optional[CNJProcessNumber]:
    """Gets the next process number by advancing the 'number' part."""
    new_number = number.sequential_number + 1

    if new_number >= 1000000:
        return None

    return make_cnj_number(
        sequential_number=new_number,
        year=number.year,
        segment=number.segment,
        tr_code=number.tr_code,
        source_unit=number.source_unit,
    )


ResetFunction = Callable[[CNJProcessNumber], CNJProcessNumber]


def advance(number: CNJProcessNumber, tj: TJ) -> Optional[CNJProcessNumber]:
    """
    Advances the process number into the next possible (not necessarily
    existing) process number.
    """

    def reset_for(field: str) -> ResetFunction:
        def zero_field(number: CNJProcessNumber) -> CNJProcessNumber:
            number_as_dict = {
                k: v for k, v in number._asdict().items() if k not in [field, "digits"]
            }

            number_as_dict[field] = 0

            return make_cnj_number(**number_as_dict)

        return zero_field

    # Units can be ordered by [known] frequency, so testing digits for the most
    # frequent unit might cut much more work.
    steps: list[
        tuple[Callable[[CNJProcessNumber], CNJProcessNumber | None], ResetFunction]
    ] = [
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
    """Loads a TOML file containing information about TJs."""
    import toml

    with open(path, encoding="utf-8") as f:
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
