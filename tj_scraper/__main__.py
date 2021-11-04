"""
A program that fetches information from brazilian Tribunal de Justiça pages.
"""
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any, Callable, Union

from .process import all_from, id_or_range, Process


def print_usage(exe_name):
    """Prints a user-friendly minimal guide to use this software."""
    # pylint: disable=line-too-long
    from textwrap import dedent

    print(
        dedent(
            f"""
        Uso: {exe_name} <Nº do processo>
             {exe_name} <intervalo de nºs de processos>

             Passando apenas o Nº do processo, o programa irá adquirir apenas
             as informações do processo com tal nº e não buscará por outros.

             Passando um intervalo no formato "<nº inicial>..<nº final>", o
             programa irá buscar por todos os processos indo do nº inicial ao
             nº final.

        Exemplos:

            - Buscar informações do processo 2021.000.000000-0:
                Comando:
                    {exe_name} 2021.000.000000-0

                Resultado:
                    {{"process_id": "2021.000.000000-0", ...}}

            - Buscar informações dos processos 2021.000.000000-0 ao 2021.000.000000-3:
                Comando:
                    {exe_name} 2021.000.000000-0..2021.000.000000-3

                Resultado:
                    {{"process_id": "2021.000.000000-0", ...}}
                    {{"process_id": "2021.000.000000-1", ...}}
                    {{"process_id": "2021.000.000000-2", ...}}
                    {{"process_id": "2021.000.000000-3", ...}}
    """
        ).strip()
    )


def download_all_from_range(
    ids: list[str],
    sink: Path,
    fetch_all: bool = True,
    filter_function: Callable[[dict[str, Any]], bool] = lambda _: True,
):
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """

    def is_invalid_process(data):
        return data in (
            ["Número do processo inválido."],
            ["O processo informado não foi encontrado."],
        )

    import requests
    import jsonlines

    base_url = (
        "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
    )
    fields = ["idProc", "codProc"]

    for id_ in ids:
        response = requests.post(
            base_url,
            json={
                "tipoProcesso": "1",
                "codigoProcesso": id_,
            },
        )

        data = response.json()

        if is_invalid_process(data):
            print(f"{id_}: Invalid/Not Found")
            continue

        if not filter_function(data):
            print(f"{id_}: Filtered  -- ({data.get('txtAssunto', 'Sem Assunto')})")
            continue

        if fetch_all:
            fields = data.keys()

        data = {k: v for k, v in data.items() if k in fields}
        print(f"{id_}: {data.get('txtAssunto', 'Sem Assunto')}")

        with jsonlines.open(sink, mode="a") as sink_f:
            sink_f.write(data)

    # start_urls = [build_tjrj_process_url(id_) for id_ in ids]
    # print(f"{start_urls=}")

    # crawler_settings = {
    #     "FEED_EXPORT_ENCODING": "utf-8",
    #     "FEEDS": {
    #         sink: {"format": "jsonlines"},
    #     },
    # }

    # run_spider(
    #     TJRJSpider,
    #     start_urls=start_urls,
    #     settings=crawler_settings,
    # )


def processes_by_subject(
    id_range: Union[tuple[str, str], str], words: Collection[str]
) -> Collection[Process]:
    """Search for processes that contain the given words on its subject."""

    def has_word_in_subject(data: dict[str, Any]):
        return any(
            word.lower() in data.get("txtAssunto", "Sem Assunto").lower()
            for word in words
        )

    print(f"Filtering by: {words}")

    all_from_range = all_from(id_range)
    ids = [*all_from_range]

    download_all_from_range(
        ids, Path("results") / "items.jsonl", filter_function=has_word_in_subject
    )
    return []


def main(*args: str):
    """Program's start point. May be used to simulate program execution."""

    try:
        arg = args[1]
    except IndexError:
        print_usage("tj_scraper")
        return 0

    if arg == "--help":
        print_usage("tj_scraper")
        return 0

    processes_by_subject(id_or_range(arg), ["furto"])

    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv))
