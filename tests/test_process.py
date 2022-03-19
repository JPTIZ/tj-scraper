"""Tests process object manipulation through tj_scraper.process module."""
import pytest

from tj_scraper.process import (
    all_from,
    cap_with_carry,
    has_words_in_subject,
    id_or_range,
    to_parts,
)


def test_split_id_with_valid_input():
    """Tests if `id_or_range` handles valid inputs correctly."""
    assert id_or_range("0") == "0"
    assert id_or_range("0..1") == ("0", "1")


def test_split_id_with_invalid_input():
    """Tests if `id_or_range` handles invalid inputs correctly."""
    with pytest.raises(ValueError):
        id_or_range("0..1..2")


def test_split_parts_with_valid_input():
    """
    Tests if ID string's parts are correctly splitted. Does not check if format is correct.
    """
    assert to_parts("1111.222.333333-4") == ["1111", "222", "333333", "4"]


def test_cap_with_carry():
    """Tests if `cap_with_carry` returns correct capped value and carry."""
    assert cap_with_carry(0, 10) == (0, 0)
    assert cap_with_carry(9, 10) == (9, 0)
    assert cap_with_carry(10, 10) == (0, 1)
    assert cap_with_carry(19, 10) == (9, 1)
    assert cap_with_carry(29, 10) == (9, 2)
    assert cap_with_carry(29, 100) == (29, 0)
    assert cap_with_carry(129, 100) == (29, 1)

    assert cap_with_carry(11, 11) == (0, 1)
    assert cap_with_carry(12, 11) == (1, 1)
    assert cap_with_carry(12, 5) == (2, 2)


def test_all_from_with_valid_input():
    """Tests if `all_from` returns all process IDs in given ranges."""
    assert list(all_from("1111.222.333333-4")) == ["1111.222.333333-4"]

    assert list(all_from(("0000.000.000000-0", "0000.000.000000-1"))) == [
        "0000.000.000000-0",
        "0000.000.000000-1",
    ]
    assert list(all_from(("1111.222.333333-4", "1111.222.333333-5"))) == [
        "1111.222.333333-4",
        "1111.222.333333-5",
    ]
    assert list(all_from(("1111.222.333333-4", "1111.222.333334-0"))) == [
        "1111.222.333333-4",
        "1111.222.333333-5",
        "1111.222.333333-6",
        "1111.222.333333-7",
        "1111.222.333333-8",
        "1111.222.333333-9",
        "1111.222.333334-0",
    ]
    assert list(all_from(("1111.222.333333-4", "1111.222.333335-0"))) == [
        "1111.222.333333-4",
        "1111.222.333333-5",
        "1111.222.333333-6",
        "1111.222.333333-7",
        "1111.222.333333-8",
        "1111.222.333333-9",
        "1111.222.333334-0",
        "1111.222.333334-1",
        "1111.222.333334-2",
        "1111.222.333334-3",
        "1111.222.333334-4",
        "1111.222.333334-5",
        "1111.222.333334-6",
        "1111.222.333334-7",
        "1111.222.333334-8",
        "1111.222.333334-9",
        "1111.222.333335-0",
    ]
    assert list(all_from(("1111.222.999999-9", "1111.223.000000-1"))) == [
        "1111.222.999999-9",
        "1111.223.000000-0",
        "1111.223.000000-1",
    ]
    assert list(all_from(("1111.999.999999-9", "1112.000.000000-1"))) == [
        "1111.999.999999-9",
        "1112.000.000000-0",
        "1112.000.000000-1",
    ]


def test_all_from_with_invalid_input():
    """Tests if invalid inputs for `all_from` are properly handled."""
    with pytest.raises(ValueError):
        list(all_from(("1111.222.333333-4",)))

    with pytest.raises(AssertionError):
        list(all_from(("1111.222.333333-4", "1111.222.333333.0")))


def test_process_has_words_in_subject():
    """
    Tests if it is possible to check which words are present in a process's subject.
    """
    process = {
        "txtAssunto": "Furto  (Art. 155 - CP)",
    }

    assert has_words_in_subject(process, ["furto"])
    assert has_words_in_subject(process, ["Furto"])
    assert has_words_in_subject(process, ["FURTO"])
    assert not has_words_in_subject(process, ["Homicídio"])

    assert has_words_in_subject(process, ["furto", "art"])
