"""Tests process object manipulation through tj_scraper.process module."""
import pytest

from tj_scraper.process import (
    TJRJ,
    CNJNumberCombinations,
    CNJProcessNumber,
    JudicialSegment,
    advance,
    has_words_in_subject,
    make_cnj_number_str,
    number_or_range,
    to_cnj_number,
)


def test_make_cnj_number_str() -> None:
    """Tests if CNJ number is properly generated."""
    assert (
        make_cnj_number_str(
            CNJProcessNumber(0, 2021, JudicialSegment.JEDFT, TJRJ.code, 3)
        )
        == "0000000-54.2021.8.19.0003"
    )
    assert (
        make_cnj_number_str(
            CNJProcessNumber(1234, 2021, JudicialSegment.JEDFT, TJRJ.code, 45)
        )
        == "0001234-42.2021.8.19.0045"
    )


def test_advance_process_number() -> None:
    """
    Tests if getting the next CNJ number for a process number specification
    works as expected.
    """
    units = TJRJ.source_units
    assert advance(
        CNJProcessNumber(0, 2021, JudicialSegment.JEDFT, 2, units[0].code), tj=TJRJ
    ) == CNJProcessNumber(0, 2021, JudicialSegment.JEDFT, 2, units[1].code)
    assert advance(
        CNJProcessNumber(0, 2021, JudicialSegment.JEDFT, 2, units[-1].code), tj=TJRJ
    ) == CNJProcessNumber(1, 2021, JudicialSegment.JEDFT, 2, units[0].code)


def test_to_number_with_valid_input() -> None:
    """
    Tests if ID string's parts are correctly splitted. Does not check if format
    is correct.
    """
    assert to_cnj_number("0000000-11.2222.8.44.5555") == CNJProcessNumber(
        sequential_number=0,
        year=2222,
        segment=JudicialSegment.JEDFT,
        tr_code=44,
        source_unit=5555,
    )


def test_id_or_range_with_valid_input() -> None:
    """Tests if `id_or_range` handles valid inputs correctly."""
    segment = JudicialSegment.JEDFT
    range_ = CNJNumberCombinations(
        sequence_start=0,
        sequence_end=1,
        year=0,
        tj=TJRJ,
        segment=segment,
    )
    str_range = ("0000000-00.0000.8.19.0000", "0000001-01.0001.8.19.0000")

    assert number_or_range(str_range[0]) == CNJProcessNumber(
        range_.sequence_start,
        range_.year,
        range_.segment,
        range_.tj.code,
        source_unit=0,
    )
    assert number_or_range("..".join(str_range)) == range_


def test_split_id_with_invalid_input() -> None:
    """Tests if `id_or_range` handles invalid inputs correctly."""
    with pytest.raises(ValueError):
        number_or_range("0..1..2")


def test_iter_through_combinations_yields_expected_numbers() -> None:
    """
    Tests if iteration though `CNJNumberCombinations` yields the expected CNJ
    numbers.
    """
    combinations = CNJNumberCombinations(
        sequence_start=1,
        sequence_end=1,
        year=3,
        segment=JudicialSegment.JEDFT,
        tj=TJRJ,
    )

    expected = [
        CNJProcessNumber(
            sequential_number=1,
            year=3,
            segment=JudicialSegment.JEDFT,
            tr_code=TJRJ.code,
            source_unit=source_unit.code,
        )
        for source_unit in TJRJ.source_units
    ]

    assert sorted(list(combinations)) == sorted(expected)


def test_iter_through_combinations_with_invalid_input_yields_no_value() -> None:
    """Tests if invalid inputs for `all_from` are properly handled."""
    assert not list(
        CNJNumberCombinations(
            sequence_start=1,
            sequence_end=0,
            year=2021,
            tj=TJRJ,
            segment=JudicialSegment.JEDFT,
        )
    )


def test_process_has_words_in_subject() -> None:
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
