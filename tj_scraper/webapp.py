"""A web application front/backend for the library's operations."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Union

from flask import Flask, jsonify, render_template, request, send_file
from flask.wrappers import Response as FlaskResponse
from werkzeug.wrappers.response import Response as WerkzeugResponse

from .cache import jsonl_reader, restore, load_most_common_subjects
from .errors import InvalidProcessNumber
from .process import (
    TJRJ,
    CNJNumberCombinations,
    CNJProcessNumber,
    JudicialSegment,
    ProcessJSON,
    to_cnj_number,
)
from tj_scraper.download import (
    discover_with_json_api,
    download_all_from_range,
    processes_by_subject,
)

Response = Union[str, tuple[str | FlaskResponse | WerkzeugResponse, int]]

# TODO #1: Mostrar uma tabela com intervalos (pré-definidos) de IDs e habilitar
# salvar esses intervalos.
#
# Exemplo de tabela:
#
# +-------------+---------------+--------+
# |  Intervalo  | Cobertura (%) | Baixar |
# +-------------+---------------+--------+
# | 0.00...0.99 | 100%          | <link> |
# | 1.00...1.99 | 34%           | <link> |
# +-------------+---------------+--------+

# TODO #2: Colocar assuntos comuns (talvez pegar da página de busca por
# Sentença do ww4).

# TODO #3: Salvar HTMLs previamente gerados com o tabelamento dos processos
# conhecidos, atualizados de tempos em tempos, com o objetivo de não
# sobrecarregar o servidor só para mostrar alguns processos.


def make_intervals(known_ids: list[CNJProcessNumber]) -> list[tuple[int, int]]:
    """
    Creates a list of (start, end) intervals of sequential IDs in `known_ids`.
    """
    known_ids = sorted(known_ids)

    intervals = []
    start, *tail = known_ids
    end = start
    for id_ in tail:
        if id_.sequential_number > end.sequential_number + 1:
            intervals.append((start, end))
            start = id_
        end = id_
    last = known_ids[-1]
    if last != end:
        intervals.append((start, last))

    return [
        (start.sequential_number, end.sequential_number) for start, end in intervals
    ]


def to_cnj_number_or_none(item: ProcessJSON) -> CNJProcessNumber | None:
    """Tries to convert item's codCnj to CNJ Number and returns None if failed."""
    try:
        return to_cnj_number(str(item["codCnj"]))
    except (InvalidProcessNumber, KeyError):
        return None


@dataclass(frozen=True)
class DownloadRequest:
    number_combinations: CNJNumberCombinations
    subject: str
    cache_path: Path
    download_type: str


def get_processes(request: DownloadRequest) -> list[ProcessJSON]:
    with NamedTemporaryFile() as sink:
        sink_file = Path(sink.name)

        if request.subject is not None:
            processes_by_subject(
                request.number_combinations,
                words=[request.subject],
                download_function=discover_with_json_api,
                output=sink_file,
                cache_path=request.cache_path,
            )
        else:
            download_all_from_range(
                request.number_combinations, sink_file, cache_path=request.cache_path
            )

        sink.seek(0)

        with jsonl_reader(sink_file) as sink_f:
            return list(sink_f)


def export_file(
    request: DownloadRequest,
    data: list[ProcessJSON],
) -> Response:
    match request.download_type:
        case "json":
            return jsonify(data), 200
        case "xlsx":
            suffix = "_".join(request.subject.split())
            params = map(str, [
                "Processos-TJ",
                request.number_combinations.sequence_start,
                request.number_combinations.sequence_end,
                suffix,
            ])
            filename = f'{"-".join(params)}.xlsx'
            with NamedTemporaryFile() as xlsx_file:
                from tj_scraper.export import export_to_xlsx

                export_to_xlsx(data, Path(xlsx_file.name))
                xlsx_file.seek(0)
                return send_file(xlsx_file.name, attachment_filename=filename), 200
        case _:
            return (
                f'tipo_download should be "json" or "xlsx", but it is {request.download_type}.',
                300,
            )


def make_webapp(cache_path: Path) -> Flask:
    """Creates the tj_scraper flask application."""
    # pylint: disable=redefined-outer-name
    # pylint: disable=too-many-statements
    app = Flask(__name__)
    # from tj_scraper.cache import quickfix_db_id_to_real_id
    # quickfix_db_id_to_real_id(cache_path)
    # from tj_scraper.cache import quickfix_db_id_to_cnj_id
    # quickfix_db_id_to_cnj_id(cache_path)
    # from tj_scraper.timing import report_time

    @app.route("/")
    def _root() -> Response:
        import json

        range_files = Path("id_ranges.json")
        print("Loading known ids")
        if range_files.exists():
            print("Loading predefined intervals...")
            with open(range_files, encoding="utf-8") as file_:
                intervals = json.load(file_)
        elif cache_path.exists():
            known_ids = [
                number
                for item in restore(cache_path)
                if (number := to_cnj_number_or_none(item)) is not None
            ]
            print("Making intervals...")
            intervals = make_intervals(known_ids)
            with open(range_files, "w", encoding="utf-8") as file_:
                json.dump(intervals, file_)
        else:
            print("No cache file found. No intervals then...")
            intervals = []
        subjects = load_most_common_subjects(cache_path)
        return render_template("mainpage.html", intervals=intervals, subjects=subjects)

    @app.route("/buscar", methods=["GET"])
    def _search() -> Response:
        # pylint: disable=too-many-locals
        start_arg = request.args.get("intervalo_inicio")
        end_arg = request.args.get("intervalo_fim")

        if start_arg is None or end_arg is None:
            return (
                f"Wrong inputs for either start or end: {start_arg=}, {end_arg=}.",
                400,
            )

        year_arg = request.args.get("ano")
        if year_arg is None:
            return "Year must not be empty.", 400

        year_arg = year_arg.lstrip("0")

        number_combinations = CNJNumberCombinations(
            int(start_arg),
            int(end_arg),
            tj=TJRJ,
            segment=JudicialSegment.JEDFT,
            year=int(year_arg),
        )
        subject = request.args.get("assunto-predef", "")
        print(f"{subject=}")

        if subject == "Sem Assunto":
            subject = request.args.get("assunto-outro", "")
            print(f"Changed: {subject=}")

        download_request = DownloadRequest(
            number_combinations=number_combinations,
            subject=subject,
            cache_path=cache_path,
            download_type=request.args.get("tipo_download", ""),
        )

        data = get_processes(download_request)

        if not data:
            return "Nenhum dado retornado."

        subject = subject if subject is not None else ""

        return export_file(download_request, data)

    return app


# FIXME: For now, it is just to ensure UWSGI will properly load this object.
# app = make_webapp()
