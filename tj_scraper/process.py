"""Related to a TJ's juridical process."""
from dataclasses import dataclass
from typing import Callable, Generator, Mapping, NamedTuple, Optional, Union


from .errors import InvalidProcessNumber


@dataclass
class SourceUnit:
    name: str
    code: int


@dataclass(frozen=True)
class TJ:
    code: int
    source_units: list[SourceUnit]


class ProcessNumber(NamedTuple):
    number: int
    digits: int
    year: int
    tr_code: int
    source_unit: int


class IdRange(NamedTuple):
    start: ProcessNumber
    end: ProcessNumber


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


Process = Mapping[str, ProcessField]


REAL_ID_FIELD = "codProc"


def get_process_id(process: Process) -> str:
    """Gets the process ID used as a unique identifier given by TJ."""
    return str(process[REAL_ID_FIELD])


def id_or_range(process_id: str) -> IdRange | ProcessNumber:
    """Evaluates a "<start>..<end>" or a "<process id>" string."""
    start, *end = process_id.split("..")

    if len(end) > 1:
        raise ValueError(
            f'Invalid range format. Expected just one "..", got "{process_id}".'
        )

    if end:
        return IdRange(to_number(start), to_number(end[0]))
    return to_number(start)


def to_number(process_id: str) -> ProcessNumber:
    """Evaluates a single string into a process number."""
    import re

    matched = re.fullmatch(r"(\d{7})-(\d{2}).(\d{4}).8.(\d{2})\.(\d{4})", process_id)

    if matched is None:
        raise InvalidProcessNumber(
            f'A string "{process_id}" não corresponde a um número de processo válido.'
        )
    return ProcessNumber(*map(int, matched.groups()))


def cap_with_carry(number: int, limit: int) -> tuple[int, int]:
    """
    Bounds `number` to the limit specified and returns it and a carry value if
    number exceeds the limit.
    """
    return number % limit, number // limit


def next_in_range(range_: IdRange, tj: TJ) -> Optional[ProcessNumber]:
    """
    Returns the next valid process ID within specified range.

    Example: 0169689-05.2021.8.19.0001 -> 0169689-05.2021.8.19.0002
    """
    start, end = range_.start, range_.end

    if not any(x < y for x, y in zip(start, end)):
        return None

    return advance(start, tj=tj)


def all_from(
    range_: IdRange | ProcessNumber, tj: TJ
) -> Generator[ProcessNumber, None, None]:
    """Yields all valid process IDs from range (or the provided ID if not a range)."""
    if isinstance(range_, ProcessNumber):
        yield range_
        return

    start, end = range_

    assert start < end, "End should be higher than start."

    yield start

    while (start_ := next_in_range(IdRange(start, end), tj=tj)) is not None:
        start = start_
        yield start


def make_cnj_code(number: ProcessNumber) -> str:
    return f"{number.number:06}-{number.digits:02}.{number.year:04}.8.{number.tr_code:02}.{number.source_unit:04}"


def next_source_unit(number: ProcessNumber, tj: TJ) -> Optional[ProcessNumber]:
    """Gets the next process number by advancing the 'source_unit' part."""
    current_unit_index = [unit.code for unit in tj.source_units].index(
        number.source_unit
    )
    try:
        return ProcessNumber(
            number=number.number,
            digits=number.digits,
            year=number.year,
            tr_code=number.tr_code,
            source_unit=tj.source_units[current_unit_index + 1].code,
        )
    except KeyError:
        return None


def next_digit(number: ProcessNumber) -> Optional[ProcessNumber]:
    """Gets the next process number by advancing the 'digits' part."""
    new_digit = number.digits + 1

    if new_digit >= 100:
        return None

    return ProcessNumber(
        number=number.number,
        digits=new_digit,
        year=number.year,
        tr_code=number.tr_code,
        source_unit=number.source_unit,
    )


def next_number(number: ProcessNumber) -> Optional[ProcessNumber]:
    """Gets the next process number by advancing the 'number' part."""
    new_number = number.number + 1

    if new_number >= 1000000:
        return None

    return ProcessNumber(
        number=new_number,
        digits=number.digits,
        year=number.year,
        tr_code=number.tr_code,
        source_unit=number.source_unit,
    )


def advance(number: ProcessNumber, tj: TJ) -> Optional[ProcessNumber]:
    """
    Advances the process number into the next possible (not necessarily
    existing) process number.
    """

    def reset_for(field: str) -> Callable[[ProcessNumber], ProcessNumber]:
        return lambda number: ProcessNumber(**{**number._asdict(), field: 0})

    # Units can be ordered by [known] frequency, so testing digits for the most
    # frequent unit might cut much more work.
    steps = [
        (next_digit, reset_for("digits")),
        (lambda n: next_source_unit(n, tj), reset_for("units")),
        (next_number, reset_for("number")),
    ]

    for (step, reset) in steps:
        new_number = step(number)
        if new_number is not None:
            return new_number
        number = reset(number)

    return None


def has_words_in_subject(data: Process, words: list[str]) -> bool:
    """Checks if data's subject field contains any of certains words."""
    assunto = data.get("txtAssunto", "Sem Assunto")
    if isinstance(assunto, list):
        assunto = " ".join(map(str, assunto))
    assunto = assunto.lower()
    has = any(word.lower() in assunto for word in words)
    # print(f"{has} for {words} in {assunto}")
    return has


TJRJ = TJ(
    code=19,
    source_units=sorted(
        [
            SourceUnit(name="Comarca da Capital", code=1),
            SourceUnit(name="Comarca de Angra dos Reis", code=3),
            SourceUnit(name="Comarca de Araruama", code=52),
            SourceUnit(name="Comarca de Arraial do Cabo", code=5),
            SourceUnit(name="Comarca de Barra Mansa", code=7),
            SourceUnit(name="Comarca de Barra do Piraí", code=6),
            SourceUnit(name="Comarca de Belford Roxo", code=8),
            SourceUnit(name="Comarca de Bom Jardim", code=9),
            SourceUnit(name="Comarca de Bom Jesus de Itabapoana", code=10),
            SourceUnit(name="Comarca de Búzios", code=78),
            SourceUnit(name="Comarca de Cabo Frio", code=11),
            SourceUnit(name="Comarca de Cachoeiras de Macacu", code=12),
            SourceUnit(name="Comarca de Cambuci", code=13),
            SourceUnit(name="Comarca de Campos dos Goytacazes", code=14),
            SourceUnit(name="Comarca de Cantagalo", code=15),
            SourceUnit(name="Comarca de Carmo", code=16),
            SourceUnit(name="Comarca de Casimiro de Abreu", code=17),
            SourceUnit(name="Comarca de Conceição de Macabu", code=18),
            SourceUnit(name="Comarca de Cordeiro", code=19),
            SourceUnit(name="Comarca de Duas Barras", code=20),
            SourceUnit(name="Comarca de Duque de Caxias", code=21),
            SourceUnit(name="Comarca de Engenheiro Paulo de Frontin", code=22),
            SourceUnit(name="Comarca de Guapimirim", code=73),
            SourceUnit(name="Comarca de Iguaba Grande", code=69),
            SourceUnit(name="Comarca de Itaboraí", code=23),
            SourceUnit(name="Comarca de Itaguaí", code=24),
            SourceUnit(name="Comarca de Italva", code=80),
            SourceUnit(name="Comarca de Itaocara", code=25),
            SourceUnit(name="Comarca de Itaperuna", code=26),
            SourceUnit(name="Comarca de Itatiaia", code=81),
            SourceUnit(name="Comarca de Japeri", code=83),
            SourceUnit(name="Comarca de Laje do Muriaé", code=27),
            SourceUnit(name="Comarca de Macaé", code=28),
            SourceUnit(name="Comarca de Magé - Regional de Inhomirim", code=75),
            SourceUnit(name="Comarca de Magé", code=29),
            SourceUnit(name="Comarca de Mangaratiba", code=30),
            SourceUnit(name="Comarca de Maricá", code=31),
            SourceUnit(name="Comarca de Mendes", code=32),
            SourceUnit(name="Comarca de Miguel Pereira", code=33),
            SourceUnit(name="Comarca de Miracema", code=34),
            SourceUnit(name="Comarca de Natividade", code=35),
            SourceUnit(name="Comarca de Nilópolis", code=36),
            SourceUnit(name="Comarca de Niterói", code=2),
            SourceUnit(name="Comarca de Nova Friburgo", code=37),
            SourceUnit(name="Comarca de Nova Iguaçu", code=38),
            SourceUnit(name="Comarca de Paracambi", code=39),
            SourceUnit(name="Comarca de Paraty", code=41),
            SourceUnit(name="Comarca de Paraíba do Sul", code=40),
            SourceUnit(name="Comarca de Paty do Alferes", code=72),
            SourceUnit(name="Comarca de Petrópolis", code=42),
            SourceUnit(name="Comarca de Pinheiral", code=82),
            SourceUnit(name="Comarca de Piraí", code=43),
            SourceUnit(name="Comarca de Porciúncula", code=44),
            SourceUnit(name="Comarca de Porto Real - Quatis", code=71),
            SourceUnit(name="Comarca de Queimados", code=67),
            SourceUnit(name="Comarca de Resende", code=45),
            SourceUnit(name="Comarca de Rio Bonito", code=46),
            SourceUnit(name="Comarca de Rio Claro", code=47),
            SourceUnit(name="Comarca de Rio das Flores", code=48),
            SourceUnit(name="Comarca de Rio das Ostras", code=68),
            SourceUnit(name="Comarca de Santa Maria Madalena", code=49),
            SourceUnit(name="Comarca de Santo Antônio de Pádua", code=50),
            SourceUnit(name="Comarca de Sapucaia", code=57),
            SourceUnit(name="Comarca de Saquarema", code=58),
            SourceUnit(name="Comarca de Seropédica", code=77),
            SourceUnit(name="Comarca de Silva Jardim", code=59),
            SourceUnit(name="Comarca de Sumidouro", code=60),
            SourceUnit(name="Comarca de São Fidelis", code=51),
            SourceUnit(name="Comarca de São Francisco do Itabapoana", code=70),
            SourceUnit(name="Comarca de São Gonçalo", code=4),
            SourceUnit(name="Comarca de São José do Vale do Rio Preto", code=76),
            SourceUnit(name="Comarca de São João da Barra", code=53),
            SourceUnit(name="Comarca de São João de Meriti", code=54),
            SourceUnit(name="Comarca de São Pedro da Aldeia", code=55),
            SourceUnit(name="Comarca de São Sebastião do Alto", code=56),
            SourceUnit(name="Comarca de Teresópolis", code=61),
            SourceUnit(name="Comarca de Trajano de Moraes", code=62),
            SourceUnit(name="Comarca de Três Rios", code=63),
            SourceUnit(name="Comarca de Valença", code=64),
            SourceUnit(name="Comarca de Vassouras", code=65),
            SourceUnit(name="Comarca de Volta Redonda", code=66),
            SourceUnit(name="Processos da VEP", code=1),
            SourceUnit(name="Processos das Turmas Recursais", code=9000),
            SourceUnit(name="Processos de 2ª Instância", code=0000),
            SourceUnit(name="RComarca de Carapebus / Quissamã", code=84),
            SourceUnit(name="Regional da Barra da Tijuca", code=209),
            SourceUnit(name="Regional da Ilha do Governador", code=207),
            SourceUnit(name="Regional da Leopoldina", code=210),
            SourceUnit(name="Regional da Pavuna", code=211),
            SourceUnit(name="Regional da Região Oceânica", code=212),
            SourceUnit(name="Regional de Alcântara", code=87),
            SourceUnit(name="Regional de Bangu", code=204),
            SourceUnit(name="Regional de Campo Grande", code=205),
            SourceUnit(name="Regional de Itaipava", code=79),
            SourceUnit(name="Regional de Jacarepaguá", code=203),
            SourceUnit(name="Regional de Madureira", code=202),
            SourceUnit(name="Regional de Santa Cruz", code=206),
            SourceUnit(name="Regional do Méier", code=208),
        ],
        key=lambda unit: unit.code,
    ),
)
