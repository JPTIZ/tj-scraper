"""A web application front/backend for the library's operations."""
from flask import Flask


def make_webapp():
    """Creates the tj_scraper flask application."""
    app = Flask(__name__)

    @app.route("/")
    def root():
        return """
            It works!
        """

    return app
