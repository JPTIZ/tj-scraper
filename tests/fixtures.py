"""Pytest fixtures for tj_scraper's unit tests."""
from pathlib import Path
from typing import Any, Generator, TypeVar

from aioresponses import aioresponses, CallbackResult
import pytest

from . import LOCAL_URL, MOCK_DB, REAL_IDS
from .helpers import reverse_lookup


@pytest.fixture()
def results_sink() -> Generator[Path, None, None]:
    """A sink file for tests' collected download items."""
    sink = Path("tests") / "test_results.jsonl"
    yield sink
    sink.unlink(missing_ok=True)


@pytest.fixture()
def local_tj() -> Generator[aioresponses, None, None]:
    """
    Gives a aioresponses wrapper so aiohttp requests actually fallback to a
    local TJ database.
    """

    def callback(_: Any, **kwargs: dict[str, Any]) -> CallbackResult:
        json = kwargs["json"]
        process_id = reverse_lookup(REAL_IDS, json["codigoProcesso"])
        payload = (
            MOCK_DB[process_id]
            if process_id is not None
            else ["Número do processo inválido."]
        )
        return CallbackResult(status=200, payload=payload)  # type: ignore

    with aioresponses() as mocked_aiohttp:  # type: ignore
        mocked_aiohttp.post(LOCAL_URL, callback=callback, repeat=True)
        yield mocked_aiohttp


T = TypeVar("T")


def flatten(list_of_lists: list[list[T]]) -> list[T]:
    """Flattens a list of lists into a simple 1D list."""
    return [item for sublist in list_of_lists for item in sublist]
