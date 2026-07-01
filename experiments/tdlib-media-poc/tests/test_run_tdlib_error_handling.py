import pytdbot
import pytest

from benchmark.run_tdlib import raise_if_error


def test_raise_if_error_passes_through_non_error_result():
    result = raise_if_error("some value")
    assert result == "some value"


def test_raise_if_error_raises_on_pytdbot_error():
    error = pytdbot.types.Error(code=400, message="MESSAGE_ID_INVALID")
    with pytest.raises(RuntimeError, match="MESSAGE_ID_INVALID"):
        raise_if_error(error)
