"""General tools for URL building."""
from typing import Mapping


def build_url(page: str, params: Mapping[str, str | int]) -> str:
    """Builds URL with correct query string. For API purposes."""
    page, *query_strings = page.split("?", maxsplit=1)
    query_string = query_strings[0] if query_strings else ""

    params = (
        dict(
            param_string.split("=", maxsplit=1)
            for param_string in query_string.split("&")
            if param_string
        )
        | params
    )
    query_string = "&".join(f"{p}={v}" for p, v in params.items())

    return f"{page}?{query_string}"


def build_tjrj_process_url(process_id: str) -> str:
    """Creates process info page url from process_id."""
    root = "http://www4.tjrj.jus.br"
    page = "consultaProcessoWebV2/consultaMov.do"

    params = {
        "numProcesso": process_id,
        "acessoIP": "internet",
    }
    return build_url(f"{root}/{page}", params=params)
