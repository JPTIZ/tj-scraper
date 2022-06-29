"""
Tests cache's low-level operations. `test_download` contains high-level
testing.
"""
from pathlib import Path
from typing import Iterable

from tj_scraper.cache import CacheState, DBProcess, Filtered
from tj_scraper.process import CNJProcessNumber, to_cnj_number

from .helpers import reverse_lookup
from .mock import CNJ_IDS, MOCKED_TJRJ_BACKEND_DB, REAL_IDS

# pylint: disable=redefined-outer-name


def make_number_set(numbers: set[str]) -> set[CNJProcessNumber]:
    return {to_cnj_number(number) for number in numbers}


def make_number_list(numbers: Iterable[str]) -> list[CNJProcessNumber]:
    return [to_cnj_number(number) for number in numbers]


def make_filtered(
    not_cached: set[str], cached: set[str], invalid: set[str]
) -> Filtered:
    return Filtered(
        not_cached=make_number_set(not_cached),
        cached=make_number_set(cached),
        invalid=make_number_set(invalid),
    )


def test_filter_cached_ids_with_cached(cache_db: Path) -> None:
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import filter_cached, save_to_cache

    cached = {CNJ_IDS["2"]}
    not_cached = set(CNJ_IDS.values()) - cached

    for cached_id in cached:
        cnj_number = reverse_lookup(CNJ_IDS, cached_id)

        assert cnj_number is not None

        save_to_cache(MOCKED_TJRJ_BACKEND_DB[cnj_number], cache_db)

    assert filter_cached(make_number_list(CNJ_IDS.values()), cache_db) == make_filtered(
        not_cached, cached, set()
    )


def test_filter_cached_ids_with_cached_and_invalid(cache_db: Path) -> None:
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import filter_cached, save_to_cache

    cached = {CNJ_IDS["2"]}
    invalid = {CNJ_IDS["4"]}
    not_cached = set(CNJ_IDS.values()) - (cached | invalid)

    for cached_id in cached:
        real_id = reverse_lookup(CNJ_IDS, cached_id)

        assert real_id is not None

        save_to_cache(MOCKED_TJRJ_BACKEND_DB[real_id], cache_db)

    for cached_id in invalid:
        real_id = reverse_lookup(CNJ_IDS, cached_id)

        assert real_id is not None

        save_to_cache(
            MOCKED_TJRJ_BACKEND_DB[real_id], cache_db, state=CacheState.INVALID
        )

    assert filter_cached(make_number_list(CNJ_IDS.values()), cache_db) == make_filtered(
        not_cached=not_cached,
        cached=cached,
        invalid=invalid,
    )


def test_restore_ids_no_filter_function(cache_db: Path) -> None:
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import restore_json_for_ids, save_to_cache

    expected_ids = {CNJ_IDS["2"]}

    for process in MOCKED_TJRJ_BACKEND_DB.values():
        save_to_cache(process, cache_db)

    expected_values = [
        item
        for item in MOCKED_TJRJ_BACKEND_DB.values()
        if item["codCnj"] in expected_ids
    ]

    assert (
        restore_json_for_ids(
            cache_db, ids=make_number_list(expected_ids), filter_function=lambda _: True
        )
        == expected_values
    )


def test_restore_ids_with_filter_function(cache_db: Path) -> None:
    """Tests if cache is able to filter IDs that are already cached."""
    from tj_scraper.cache import CacheState, restore_json_for_ids, save_to_cache

    expected_ids = {CNJ_IDS["3"]}

    for process in MOCKED_TJRJ_BACKEND_DB.values():
        save_to_cache(process, cache_db)

    def custom_filter(process: DBProcess) -> bool:
        return "furto" in process.json.get("txtAssunto", "").lower()

    expected_values = [
        item
        for item in MOCKED_TJRJ_BACKEND_DB.values()
        if item["codCnj"] in expected_ids
        and custom_filter(DBProcess("", CacheState.CACHED, "", item))
    ]

    assert (
        restore_json_for_ids(
            cache_db, ids=make_number_list(expected_ids), filter_function=custom_filter
        )
        == expected_values
    )
