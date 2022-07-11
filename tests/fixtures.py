"""Pytest fixtures for tj_scraper's unit tests."""
from pathlib import Path
from typing import Generator, TypeVar

import pytest


@pytest.fixture()
def results_sink(tmp_path: Path) -> Generator[Path, None, None]:
    """A sink file for tests' collected download items."""
    sink = tmp_path / "test_results.jsonl"
    yield sink
    sink.unlink(missing_ok=True)


T = TypeVar("T")  # pylint: disable=invalid-name


def flatten(list_of_lists: list[list[T]]) -> list[T]:
    """Flattens a list of lists into a simple 1D list."""
    return [item for sublist in list_of_lists for item in sublist]
