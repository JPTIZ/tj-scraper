"""
Tests URL building utilities.

TJ-specific URL building aren't tested since they're just hardcoded shortcuts
to URL building.
"""
from tj_scraper.url import build_url


def test_build_url_without_parameters() -> None:
    """Tests if URLs without parameters are built properly."""
    assert build_url("a", {}) == "a?"
    assert build_url("a?b=1", {}) == "a?b=1"


def test_build_url_with_parameters() -> None:
    """Tests if URLs with parameters are built properly."""
    assert build_url("a", {"b": 1}) == "a?b=1"
    assert build_url("a", {"b": 1, "c": "123"}) == "a?b=1&c=123"
    assert build_url("a?", {"b": 1}) == "a?b=1"
