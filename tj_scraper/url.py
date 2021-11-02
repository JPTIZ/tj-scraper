"""General tools for URL building."""


def build_url(page: str, params: dict[str, str]):
    """Builds URL with correct query string. For API purposes."""
    query_string = "&".join(f"{p}={v}" for p, v in params.items())

    return f"{page}?{query_string}"


def build_tjrj_process_url(process_id):
    """Creates process info page url from process_id."""
    root = "http://www4.tjrj.jus.br"
    page = "consultaProcessoWebV2/consultaMov.do"

    params = {
        "numProcesso": process_id,
        "acessoIP": "internet",
    }
    return build_url(f"{root}/{page}", params=params)
