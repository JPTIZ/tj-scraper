"""
Tests cache's low-level operations. `test_download` contains high-level
testing.
"""
from . import MOCK_DB, REAL_IDS
from .conftest import reverse_lookup

# pylint: disable=redefined-outer-name


def test_filter_cached_ids(cache_db):
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import filter_cached, save_to_cache

    not_cached = {"2021.001.150000-1", "2021.001.150000-3"}
    cached = {"2021.001.150000-2"}

    for cached_id in cached:
        real_id = reverse_lookup(REAL_IDS, cached_id)

        assert real_id is not None

        save_to_cache(MOCK_DB[real_id], cache_db)

    assert filter_cached(list(not_cached | cached), cache_db) == (not_cached, cached)
