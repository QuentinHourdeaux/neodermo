"""Password policy and normalized account identity without external lookups."""

from unittest.mock import patch

import pytest
from argon2 import PasswordHasher, Type, extract_parameters

from neodermo.auth.passwords import hash_new_password, validate_password_input, verify_password
from neodermo.auth.validation import normalize_email


@pytest.mark.parametrize("value, expected", [
    ("  Demo.User+Care@Example.COM  ", "demo.user+care@example.com"),
    ("Demo@bücher.de", "demo@xn--bcher-kva.de"),
])
def test_email_policy_preserves_provider_specific_parts(value, expected):
    with patch("dns.resolver.resolve", side_effect=AssertionError("DNS lookup")):
        assert normalize_email(value) == expected
        assert normalize_email(expected) == expected


@pytest.mark.parametrize("value", [
    None, 3, [], "", "not-an-email", "demo@example.com\nBcc: other@example.com",
    "a" * 1025, "a" * 65 + "@example.com", "é@example.com", "\ud800@example.com",
])
def test_email_rejects_invalid_input_without_echo(value):
    with pytest.raises(ValueError) as error:
        normalize_email(value)
    assert str(error.value) == "Enter a valid email address within the length limit."


@pytest.mark.parametrize("password", [None, 3, [], "", "a" * 14, "a" * 129, "\ud800" * 15])
def test_password_bounds_fail_without_echo(password):
    with pytest.raises(ValueError) as error:
        hash_new_password(password)
    assert str(error.value) == "Password must contain 15–128 valid Unicode characters."


@pytest.mark.parametrize("password", ["a" * 15, "é" * 128, "  unusual phrase 🐢  "])
def test_password_hash_preserves_exact_input_and_uses_random_salt(password):
    first = hash_new_password(password)
    second = hash_new_password(password)
    assert first != second
    parameters = extract_parameters(first)
    assert parameters.type is Type.ID
    assert (parameters.memory_cost, parameters.time_cost, parameters.parallelism) == (65536, 3, 4)
    assert (parameters.salt_len, parameters.hash_len) == (16, 32)
    assert verify_password(first, password)
    assert not verify_password(first, password + "x")
    if password != password.strip():
        assert not verify_password(first, password.strip())


def test_local_blocklist_applies_to_new_passwords_not_login():
    # A public entry from the vendored list, long enough to pass the length rule.
    candidate = "Polniypizdec0211"
    validate_password_input(candidate)
    with pytest.raises(ValueError, match="not commonly used"):
        hash_new_password(candidate)
    existing_hash = PasswordHasher().hash(candidate)
    assert verify_password(existing_hash, candidate)


def test_unknown_accounts_verify_precomputed_dummy_hash(app):
    with app.app_context():
        dummy = app.extensions["auth_dummy_hash"]
        with patch("neodermo.auth.passwords._hasher") as hasher:
            hasher.verify.return_value = True
            assert not verify_password(None, "A fictional password")
            assert not verify_password(None, "Another fictional password")
        assert [call.args[0] for call in hasher.verify.call_args_list] == [dummy, dummy]
        hasher.hash.assert_not_called()
    assert not verify_password("broken hash", "A fictional password")
