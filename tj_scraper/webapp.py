"""A web application front/backend for the library's operations."""
from pathlib import Path
from typing import Union

from flask import Flask, jsonify, render_template, request, send_file
from flask.wrappers import Response as FlaskResponse
from werkzeug.wrappers.response import Response as WerkzeugResponse

from .cache import jsonl_reader, restore
from .process import TJRJ, CNJProcessNumber, IdRange, all_from, to_cnj_number

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


def make_intervals(known_ids: list[CNJProcessNumber]) -> list[IdRange]:
    """
    Creates a list of (start, end) intervals of sequential IDs in `known_ids`.
    """
    intervals = []
    start, end = min(known_ids), max(known_ids)
    interval_start, interval_end = start, start
    known_ids_set = set(known_ids)
    started_sequence = True
    for id_ in all_from(IdRange(start, end), tj=TJRJ):
        if id_ in known_ids_set:
            if not started_sequence:
                interval_start = id_
            interval_end = id_
            started_sequence = True
        else:
            if started_sequence:
                intervals.append(IdRange(interval_start, interval_end))
            started_sequence = False

    if started_sequence:
        intervals.append(IdRange(interval_start, interval_end))

    print(f"{intervals=}")
    return intervals


def make_webapp(cache_path: Path = Path("cache.db")) -> Flask:
    """Creates the tj_scraper flask application."""
    # pylint: disable=redefined-outer-name
    # pylint: disable=too-many-statements
    app = Flask(__name__)
    # from tj_scraper.cache import quickfix_db_id_to_real_id
    # quickfix_db_id_to_real_id(cache_path)
    from tj_scraper.timing import report_time

    @app.route("/")
    def _root() -> Response:
        known_ids = [
            to_cnj_number(str(item.get("codProc"))) for item in restore(cache_path)
        ]
        intervals = report_time(make_intervals, known_ids).value

        import json

        range_files = Path("id_ranges.json")
        print("Loading known ids")
        if range_files.exists():
            print("Loading predefined intervals...")
            with open(range_files, encoding="utf-8") as file_:
                intervals = json.load(file_)
        elif cache_path.exists():
            known_ids = [
                to_cnj_number(str(item.get("codProc"))) for item in restore(cache_path)
            ]
            print("Making intervals...")
            intervals = make_intervals(known_ids)
            with open(range_files, "w", encoding="utf-8") as file_:
                json.dump(intervals, file_)
        else:
            print("No cache file found. No intervals then...")
            intervals = []
        return render_template("mainpage.html", intervals=intervals)

    @app.route("/buscar", methods=["GET"])
    def _search() -> Response:
        # pylint: disable=too-many-locals
        from tj_scraper.download import (
            download_all_from_range,
            download_from_json,
            processes_by_subject,
        )

        start_arg = request.args.get("intervalo_inicio")
        end_arg = request.args.get("intervalo_fim")

        if start_arg is None or end_arg is None:
            return (
                f"Wrong inputs for either start or end: {start_arg=}, {end_arg=}.",
                400,
            )

        id_range = IdRange(to_cnj_number(start_arg), to_cnj_number(end_arg))
        subject = ""

        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile() as sink:
            sink_file = Path(sink.name)

            match request.args:
                case {"assunto": subject}:
                    print(f"Com assunto, {subject=}")
                    processes_by_subject(
                        id_range,
                        words=subject.split(),
                        download_function=download_from_json,
                        output=sink_file,
                        cache_path=cache_path,
                    )
                case _:
                    print(f"{subject=}")
                    download_all_from_range(id_range, sink_file, cache_path=cache_path)

            sink.seek(0)

            with jsonl_reader(sink_file) as sink_f:
                data = list(sink_f)

        print(f"{data=}")
        if not data:
            return "Nenhum dado retornado."

        match tipo_download := request.args.get("tipo_download"):
            case "json":
                return jsonify(data), 200
            case "xlsx":
                suffix = "_".join(subject.split())
                filename = f"Processos-TJ-{id_range.start}-{id_range.end}-{suffix}.xlsx"
                with NamedTemporaryFile() as xlsx_file:
                    from tj_scraper.export import export_to_xlsx

                    export_to_xlsx(data, Path(xlsx_file.name))
                    xlsx_file.seek(0)
                    return send_file(xlsx_file.name, attachment_filename=filename), 200

        return (
            f'tipo_download should be "json" or "xlsx", but it is {tipo_download}.',
            300,
        )

    return app


# FIXME: For now, it is just to ensure UWSGI will properly load this object.
app = make_webapp()
