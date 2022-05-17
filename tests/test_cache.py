"""
Tests cache's low-level operations. `test_download` contains high-level
testing.
"""
from . import MOCK_DB

# pylint: disable=redefined-outer-name


def test_filter_cached_ids(cache_db):
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import filter_cached, save_to_cache

    save_to_cache(MOCK_DB["2"], cache_db)
    assert filter_cached(["1", "2", "3"], cache_db) == ({"1", "3"}, {"2"})
