"""Pytest conftest module."""
from pathlib import Path
from typing import Any, Generator

import pluggy
import pytest

from _pytest.fixtures import SubRequest
from _pytest.python import Function
from _pytest.runner import CallInfo

from tj_scraper.cache import load_all

from . import CACHE_PATH


@pytest.fixture(autouse=True)
def cache_db() -> Generator[Path, None, None]:
    """
    Creates (once for each test function) a temporary ".db" cache file and
    deletes after test ends.
    """
    path = Path("cache_tests.db")
    yield path
    path.unlink(missing_ok=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)  # type: ignore
def pytest_runtest_makereport(
    item: Function, call: CallInfo[Any]
) -> Generator[pluggy.callers._Result, None, None]:
    """
    Ensures `request.node.rep_[setup,call,teardown]` from pytest is set to the
    respective stage result.
    """
    _ = call
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()  # type: ignore

    # set a report attribute for each phase of a call, which can
    # be "setup", "call", "teardown"

    setattr(item, "rep_" + rep.when, rep)


@pytest.fixture(autouse=True)
def show_cache_state(request: SubRequest) -> Generator[None, None, None]:
    """Shows current cache state when a test fails."""
    from pprint import pprint

    yield

    if request.node.rep_call.failed:
        print("Download test failed. Cache state:")
        try:
            state = {
                i: {"ID": i, "CacheState": s, "Assunto": a, "JSON": v}
                for (i, s, a, v) in load_all(cache_path=CACHE_PATH)
            }
            pprint(state, depth=3)
        except Exception as error:  # pylint: disable=broad-except
            print(" [ Failed to fetch cache state. ]")
            print(f" [ Reason: {error}. ]")
