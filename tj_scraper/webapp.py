"""A web application front/backend for the library's operations."""
from flask import Flask, jsonify, request, send_file


from .cache import jsonl_reader


def make_webapp():
    """Creates the tj_scraper flask application."""
    app = Flask(__name__)

    @app.route("/")
    def root():
        return """
            <h1>Extrator de dados de TJs</h1>

            <h3>Sobre</h3>

            Esta é uma ferramenta para permitir buscar, através de filtros
            personalizados, dados de processos dos Tribunais de Justiça do
            Brasil.

            <h3>Baixar dados</h3>
            <form action="/buscar" action="GET">
                Intervalo de processos:<br>

                <label for="intervalo_inicio">Início:</label>
                <input type="text"
                    name="intervalo_inicio"
                    placeholder="Ex: 2021.001.149800-0"
                ><br>

                <label for="intervalo_fim">Fim:</label>
                <input type="text"
                    name="intervalo_fim"
                    placeholder="Ex: 2021.001.149899-9"
                ><br>

                <label for="assunto">Assunto:</label>
                <input type="text"
                    name="assunto"
                    placeholder="Ex: Furto"
                ><br>

                <label for="tipo_download">Baixar como:</label>
                <select name="tipo_download">
                    <option value="xlsx" selected>Planilha XLSX</option>
                    <option value="json">JSON</option>
                </select>

                <input type="submit" value="Buscar">
            </form>
        """

    @app.route("/buscar", methods=["GET"])
    def search():
        # pylint: disable=too-many-locals
        from pathlib import Path
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

        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile() as sink:
            sink_file = Path(sink.name)
            match request.args:
                case {"assunto": subject}:
                    processes_by_subject(
                        (start, end),
                        words=subject.split(),
                        download_function=download_from_json,
                        output=sink_file,
                    )
                case _:
                    download_all_from_range((start, end), sink_file, Path("cache.db"))

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

                    export_to_xlsx(data, xlsx_file.name)
                    xlsx_file.seek(0)
                    return send_file(xlsx_file.name, attachment_filename=filename)

    return app
