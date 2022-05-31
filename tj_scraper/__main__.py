"""
A program that fetches information from brazilian Tribunal de Justiça pages.
"""
from .cli import make_app

if __name__ == "__main__":
    app = make_app()
    app()
