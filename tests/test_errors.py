from airframe.adapters.llama_server import _categorize_exception
from airframe.airframe_types import ErrorCategory


class DummyTimeoutError(Exception):
    pass


class DummyNetworkError(Exception):
    pass


def test_categorize_timeout():
    err = _categorize_exception(DummyTimeoutError("t"))
    assert err.category == ErrorCategory.TIMEOUT


def test_categorize_network():
    err = _categorize_exception(DummyNetworkError("n"))
    assert err.category in {ErrorCategory.CONNECTION, ErrorCategory.BACKEND}
