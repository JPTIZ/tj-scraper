"""Time measurement utilities."""
from time import time
from typing import Callable


def report_time(function: Callable, *args, **kwargs):
    """
    Runs a function and reports (prints) how much time in seconds it took to
    execute it.
    """
    start = time()
    result = function(*args, **kwargs)
    end = time()

    print(f"{function.__name__} took {end - start:.2}s to execute.")
    return result
