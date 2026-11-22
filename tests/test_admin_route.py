from src.services.admin_route import admin_route_allowed


def test_no_secret_means_no_admin_route():
    assert admin_route_allowed({"admin": "anything"}, None) is False
    assert admin_route_allowed({"admin": "anything"}, "") is False


def test_old_admin_one_is_refused():
    assert admin_route_allowed({"admin": "1"}, "a-long-random-key") is False


def test_wrong_and_missing_keys_are_refused():
    assert admin_route_allowed({"admin": "guess"}, "a-long-random-key") is False
    assert admin_route_allowed({}, "a-long-random-key") is False


def test_correct_key_is_accepted():
    assert admin_route_allowed({"admin": "a-long-random-key"}, "a-long-random-key") is True
