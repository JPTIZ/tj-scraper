"""
A program that fetches information from brazilian Tribunal de Justiça pages.
"""
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any, Callable, Union

from typer import Typer

from .process import all_from, id_or_range, Process


app = Typer()


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

    import aiohttp
    import asyncio
    import jsonlines
    import json

    results = Path("results")

    def cache(data):
        # with open(results / "cache-valid.json", "w+") as f:
        #     valids = json.load(f)
        #     valids[data[]]

        with jsonlines.open(results / "cache.jsonl", mode="a") as sink_f:
            sink_f.write(data)

    def is_invalid_process(data):
        return data in (
            ["Número do processo inválido."],
            ["O processo informado não foi encontrado."],
        )

    async def fetch_process(session: aiohttp.ClientSession, id_: str):
        async with session.post(
            base_url,
            json={
                "tipoProcesso": "1",
                "codigoProcesso": id_,
            },
        ) as response:
            data = json.loads(await response.text())

        if is_invalid_process(data):
            # print(f"{id_}: Invalid/Not Found")
            return

        if not filter_function(data):
            cache(data)
            print(
                f"{id_}: Filtered  -- ({data.get('txtAssunto', 'Sem Assunto')}) -- Cached"
            )
            return "Filtered"

        if fetch_all:
            fields = data.keys()

        data = {k: v for k, v in data.items() if k in fields}
        print(f"{id_}: {data.get('txtAssunto', 'Sem Assunto')}")
        return data

    async def fetch_all_processes(ids):
        step = 100
        async with aiohttp.ClientSession() as session:
            for start in range(0, len(ids), step):
                end = min(start + step, len(ids))
                sub_ids = ids[start:end]
                print(f"Wave: {(start // step) + 1} ({sub_ids[0]}..{sub_ids[-1]})")
                requests = (fetch_process(session, id_) for id_ in sub_ids)
                data = await asyncio.gather(
                    *requests,
                )

                filtered = sum(
                    1 if item != "Filtered" else 0 for item in data if item is not None
                )
                invalid = sum(1 if item is None else 0 for item in data)
                data = [
                    item for item in data if item is not None and item != "Filtered"
                ]
                with jsonlines.open(sink, mode="a") as sink_f:
                    sink_f.write_all(data)
                print(
                    f"Partial result: {data} ({filtered} filtered, {invalid} invalid)"
                )
        print("Finished.")

    base_url = (
        "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
    )
    # fields = ["idProc", "codProc"]

    asyncio.run(fetch_all_processes(ids))

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

    if "--export" in args:
        import jsonlines
        from .export import export_to_xlsx

        with jsonlines.open(Path("results") / "items.jsonl") as reader:
            data = [item for item in reader if item != "Filtered"]
            export_to_xlsx(data, Path("exported.xlsx"))
        return 0

    processes_by_subject(id_or_range(arg), ["furto"])

    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv))
