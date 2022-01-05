"""CLI part of the project. Interface should be in portuguese."""
from enum import Enum
from pathlib import Path
from typing import Optional

from typer import Argument, Option, Typer

from .download import (
    download_from_html,
    download_from_json,
    processes_by_subject,
)
from .process import id_or_range


def make_app():
    """Creates CLI application."""
    app = Typer()

    @app.command()
    def export(input_: Path, output: Path):  # pylint: disable=unused-variable
        """Exporta os dados para uma planilha XLSX."""
        print(f"Exporting {input_} to {output}")
        import jsonlines
        from .export import export_to_xlsx

        with jsonlines.open(input_) as reader:
            data = [item for item in reader if item != "Filtered"]  # type: ignore
            export_to_xlsx(data, output)

    class DownloadModes(str, Enum):
        """
        Which download mode to use. HTML downloads from HTML pages, JSON downloads
        from JSON response bodies.
        """

        HTML = "html"
        JSON = "json"

    @app.command()
    def download(  # pylint: disable=unused-variable
        id_range: str = Argument(
            ..., help="Intervalo ou número específico do processo", metavar="INTERVALO"
        ),
        mode: DownloadModes = Argument(
            DownloadModes.JSON.value,
        ),
        subjects: Optional[list[str]] = Option(
            ...,
            "--assuntos",
            help=(
                "Filtrar por determinadas palavras que aparecerem no assunto"
                " dos processos",
            ),
        ),
    ) -> None:
        """
        Baixa dados de todos os processos em um intervalo (ou de apenas um
        processo, caso seja passado um número exato).

        Passando apenas o Nº do processo, o programa irá adquirir apenas
        as informações do processo com tal nº e não buscará por outros.

        Passando um intervalo no formato "<nº inicial>..<nº final>", o
        programa irá buscar por todos os processos indo do nº inicial ao
        nº final.

        Exemplos:

            - Buscar informações do processo 2021.000.000000-0:

                INTERVALO:

                    2021.000.000000-0

                Resultado:

                    {{"process_id": "2021.000.000000-0", ...}}

            - Buscar informações dos processos 2021.000.000000-0 ao 2021.000.000000-3:

                INTERVALO:

                    2021.000.000000-0..2021.000.000000-3

                Resultado:

                    {{"process_id": "2021.000.000000-0", ...}}
                    {{"process_id": "2021.000.000000-1", ...}}
                    {{"process_id": "2021.000.000000-2", ...}}
                    {{"process_id": "2021.000.000000-3", ...}}
        """

        download_function = {
            DownloadModes.HTML: download_from_html,
            DownloadModes.JSON: download_from_json,
        }[mode]

        processes_by_subject(
            id_or_range(id_range),
            subjects or [],
            download_function=download_function,  # type: ignore
        )

    return app