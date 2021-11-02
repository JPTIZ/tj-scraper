"""Common errors that may be thrown."""


class BadProcessId(Exception):
    """Thrown when an invalid Process ID/Number is used in a request."""


class BlockedByCaptcha(Exception):
    """
    Thrown when trying to access a page that contains a captcha (thus stopping
    this crawler of going forward).
    """
