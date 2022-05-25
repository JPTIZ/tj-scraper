"""A web application front/backend for the library's operations."""
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from .process import all_from
from .cache import jsonl_reader, restore


def make_intervals(known_ids: list[str]) -> list[tuple[str, str]]:
    """
    Creates a list of (start, end) intervals of sequential IDs in `known_ids`.
    """
    intervals = []
    start, end = min(known_ids), max(known_ids)
    interval_start, interval_end = start, start
    started_sequence = True
    for id_ in all_from((start, end)):
        if id_ in known_ids:
            if not started_sequence:
                interval_start = id_
            interval_end = id_
            started_sequence = True
        else:
            if started_sequence:
                intervals.append((interval_start, interval_end))
            started_sequence = False

    if started_sequence:
        intervals.append((interval_start, interval_end))

    print(f"{intervals=}")
    return intervals


def make_webapp(cache_path=Path("cache.db")):
    """Creates the tj_scraper flask application."""
    # pylint: disable=redefined-outer-name
    app = Flask(__name__)

    @app.route("/")
    def root():
        known_ids = [str(item["codProc"]) for item in restore(cache_path)]
        return render_template("mainpage.html", intervals=make_intervals(known_ids))

    @app.route("/buscar", methods=["GET"])
    def search():
        # pylint: disable=too-many-locals
        from tj_scraper.download import (
            download_all_from_range,
            download_from_json,
            processes_by_subject,
        )

        start_arg = request.args.get("intervalo_inicio")
        end_arg = request.args.get("intervalo_fim")

        if not (start_arg or end_arg):
            return (
                f"Wrong inputs for either start or end: {start_arg=}, {end_arg=}.",
                400,
            )

        start = str(start_arg)
        end = str(end_arg)
        subject = ""

        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile() as sink:
            sink_file = Path(sink.name)
            match request.args:
                case {"assunto": subject}:
                    print(f"Com assunto, {subject=}")
                    processes_by_subject(
                        (start, end),
                        words=subject.split(),
                        download_function=download_from_json,
                        output=sink_file,
                        cache_path=cache_path,
                    )
                case _:
                    print(f"{subject=}")
                    download_all_from_range(
                        (start, end), sink_file, cache_path=cache_path
                    )

            sink.seek(0)

            with jsonl_reader(sink_file) as sink_f:
                data = list(sink_f)

        print(f"{data=}")
        if not data:
            return "Nenhum dado retornado."

        match request.args.get("tipo_download"):
            case "json":
                return jsonify(data), 200
            case "xlsx":
                suffix = "_".join(subject.split())
                filename = f"Processos-TJ-{start}-{end}-{suffix}.xlsx"
                with NamedTemporaryFile() as xlsx_file:
                    from tj_scraper.export import export_to_xlsx

                    export_to_xlsx(data, Path(xlsx_file.name))
                    xlsx_file.seek(0)
                    return send_file(xlsx_file.name, attachment_filename=filename)

    return app


# FIXME: For now, it is just to ensure UWSGI will properly load this object.
app = make_webapp()
