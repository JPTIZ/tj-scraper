"""Common errors that may be thrown."""


class InvalidProcessNumber(Exception):
    """Thrown when an invalid Process Number is used."""


class BlockedByCaptcha(Exception):
    """
    Thrown when trying to access a page that contains a captcha (thus stopping
    this crawler of going forward).
    """
