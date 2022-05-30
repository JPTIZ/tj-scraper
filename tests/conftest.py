"""Pytest conftest module."""
from pathlib import Path

import pytest


def ignore_unused(
    *args, reason="Pyright emmits an info that LSP is not able to ignore."
):
    """Shuts up language-servers' warnings about an unused variable/function/fixture."""
    _ = args, reason


def reverse_lookup(dict_, value):
    """Returns which key has a certain value."""
    for key, value_ in dict_.items():
        if value_ == value:
            return key
    return None


@pytest.fixture(autouse=True)
def cache_db():
    """
    Creates (once for each test function) a temporary ".db" cache file and
    deletes after test ends.
    """
    path = Path("cache_tests.db")
    yield path
    path.unlink(missing_ok=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Ensures `request.node.rep_[setup,call,teardown]` from pytest is set to the
    respective stage result.
    """
    _ = call
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # set a report attribute for each phase of a call, which can
    # be "setup", "call", "teardown"

    setattr(item, "rep_" + rep.when, rep)
