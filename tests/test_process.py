"""Tests process object manipulation through tj_scraper.process module."""
import pytest

from tj_scraper.process import (
    TJRJ,
    CNJProcessNumber,
    IdRange,
    advance,
    all_from,
    cap_with_carry,
    has_words_in_subject,
    id_or_range,
    make_cnj_code,
    to_cnj_number,
)


def test_make_cnj_code() -> None:
    """Tests if CNJ number is properly generated."""
    assert (
        make_cnj_code(CNJProcessNumber(0, 1, 2021, TJRJ.code, 3))
        == "0000000-01.2021.8.19.0003"
    )
    assert (
        make_cnj_code(CNJProcessNumber(1234, 20, 2021, TJRJ.code, 45))
        == "0001234-20.2021.8.19.0045"
    )


def test_advance_process_number() -> None:
    """
    Tests if getting the next CNJ number for a process number specification
    works as expected.
    """
    unit = TJRJ.source_units[3]
    assert advance(
        CNJProcessNumber(0, 1, 2021, 2, unit.code), tj=TJRJ
    ) == CNJProcessNumber(0, 2, 2021, 2, unit.code)
    assert advance(
        CNJProcessNumber(0, 99, 2021, 2, unit.code), tj=TJRJ
    ) == CNJProcessNumber(0, 0, 2021, 2, TJRJ.source_units[4].code)


def test_to_number_with_valid_input() -> None:
    """
    Tests if ID string's parts are correctly splitted. Does not check if format
    is correct.
    """
    assert to_cnj_number("0000000-11.2222.8.44.5555") == CNJProcessNumber(
        number=0, digits=11, year=2222, tr_code=44, source_unit=5555
    )


def test_id_or_range_with_valid_input() -> None:
    """Tests if `id_or_range` handles valid inputs correctly."""
    range_ = IdRange(CNJProcessNumber(0, 0, 0, 0, 0), CNJProcessNumber(1, 1, 1, 1, 1))
    str_range = ("0000000-00.0000.8.00.0000", "0000001-01.0001.8.01.0001")

    assert id_or_range(str_range[0]) == range_.start
    assert id_or_range("..".join(str_range)) == range_


def test_split_id_with_invalid_input() -> None:
    """Tests if `id_or_range` handles invalid inputs correctly."""
    with pytest.raises(ValueError):
        id_or_range("0..1..2")


def test_cap_with_carry() -> None:
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


def test_all_from_with_valid_input() -> None:
    """Tests if `all_from` returns all process IDs in given ranges."""
    processes = []

    for digits in range(100):
        processes.append(
            CNJProcessNumber(number=1, digits=digits, year=3, tr_code=4, source_unit=5)
        )

    processes.append(
        CNJProcessNumber(number=1, digits=0, year=3, tr_code=4, source_unit=6)
    )

    assert list(all_from(processes[0], tj=TJRJ)) == [processes[0]]

    assert (
        list(all_from(IdRange(processes[0], processes[1]), tj=TJRJ)) == processes[0:2]
    )
    assert (
        list(all_from(IdRange(processes[5], processes[6]), tj=TJRJ)) == processes[5:7]
    )
    assert list(all_from(IdRange(processes[0], processes[-1]), tj=TJRJ)) == processes


def test_all_from_with_invalid_input() -> None:
    """Tests if invalid inputs for `all_from` are properly handled."""
    with pytest.raises(AssertionError):
        list(
            all_from(
                IdRange(
                    CNJProcessNumber(1, 2, 3, 4, 5), CNJProcessNumber(0, 0, 0, 0, 0)
                ),
                tj=TJRJ,
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
