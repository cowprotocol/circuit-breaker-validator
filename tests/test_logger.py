"""Test logger functions"""

from circuit_breaker_validator.logger import get_logger


def test_logger_writes_to_stdout(capsys):
    """Check that logger writes to correct stream
    The default target is stderr. This causes problems with alerts. Thus the logger
    should only log errors to stderr and other logs to stdout.
    """
    logger = get_logger("test")

    logger.info("This is an info message")
    logger.error("This is an error message")
    captured = capsys.readouterr()

    assert "This is an info message" in captured.out
    assert not "This is an info message" in captured.err

    assert "This is an error message" in captured.err
    assert not "This is an error message" in captured.out
