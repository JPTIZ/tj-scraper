"""
Tests cache's low-level operations. `test_download` contains high-level
testing.
"""
# pylint: disable=redefined-outer-name
from pathlib import Path

import pytest


@pytest.fixture()
def cache_file():
    """A sink file for tests' collected download items."""
    sink = Path("tests") / "test_cache.jsonl"
    yield sink
    sink.unlink(missing_ok=True)


@pytest.fixture()
def cache_metadata_file():
    """A sink file for tests' collected download items."""
    from textwrap import dedent

    sink = Path("tests") / "test_cache-meta.toml"
    with open(sink, "w", encoding="utf-8") as file_:
        file_.write(
            dedent(
                """
            [meta]
            describes = "test_cache.jsonl"

            [states]
            "2" = "CACHED"
        """
            )
        )
    yield sink
    sink.unlink(missing_ok=True)


def test_filter_cached_ids(cache_file, cache_metadata_file):
    """Tests if cache is able to filter IDs that are already cached."""
    _ = cache_metadata_file  # Shut pyright's "not being accessed" false-positive
    from tj_scraper.cache import filter_cached

    assert filter_cached(["1", "2", "3"], cache_file) == ({"1", "3"}, {"2"})
