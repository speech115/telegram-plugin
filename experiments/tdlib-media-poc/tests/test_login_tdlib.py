from benchmark.login_tdlib import required_arg_for_state


def test_required_arg_for_wait_phone_number():
    assert required_arg_for_state("authorizationStateWaitPhoneNumber") == "phone"


def test_required_arg_for_wait_code():
    assert required_arg_for_state("authorizationStateWaitCode") == "code"


def test_required_arg_for_wait_password():
    assert required_arg_for_state("authorizationStateWaitPassword") == "password"


def test_required_arg_for_ready_state_is_none():
    assert required_arg_for_state("authorizationStateReady") is None


def test_required_arg_for_unknown_state_is_none():
    assert required_arg_for_state("authorizationStateWaitTdlibParameters") is None
