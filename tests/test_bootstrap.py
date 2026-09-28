"""Local provisioning never echoes credentials and cannot create two operators."""

import getpass
import signal
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from sqlalchemy import select

from neodermo.auth.bootstrap import ProvisioningError, provision_operator
from neodermo.auth.passwords import hash_new_password, verify_password
from neodermo.extensions import db
from neodermo.models import User

PASSWORD = "Fictional provisioning phrase!"
PROMPTS = "Demo@Example.com\ndemo@example.com\ny\n"


def test_bootstrap_hidden_input_and_second_operator_refusal(migrated_file_app, caplog):
    runner = migrated_file_app.test_cli_runner()
    with patch("neodermo.auth.cli.getpass.getpass", side_effect=[PASSWORD, PASSWORD]) as hidden:
        result = runner.invoke(args=["auth", "bootstrap"], input=PROMPTS)
    assert result.exit_code == 0, result.output
    assert hidden.call_count == 2
    assert "Operator created." in result.output
    with migrated_file_app.app_context():
        user = db.session.scalar(select(User))
        assert user.email == "demo@example.com"
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(user.password_hash, PASSWORD)
        assert PASSWORD not in user.password_hash
        stored_hash = user.password_hash
    assert PASSWORD not in result.output + caplog.text
    assert stored_hash not in result.output + caplog.text

    with patch("neodermo.auth.cli.getpass.getpass", side_effect=AssertionError("password prompted")):
        second = runner.invoke(args=["auth", "bootstrap"])
    assert second.exit_code != 0
    assert "already exists" in second.output
    with migrated_file_app.app_context():
        assert len(db.session.scalars(select(User)).all()) == 1
        assert db.session.scalar(select(User)).password_hash == stored_hash


@pytest.mark.parametrize("passwords, message", [
    ([PASSWORD, "a different fictional password"], "Passwords did not match"),
    (["short", "short"], "15–128"),
    (["polniypizdec0211"] * 2, "not commonly used"),
])
def test_invalid_passwords_leave_no_operator(migrated_file_app, passwords, message):
    with patch("neodermo.auth.cli.getpass.getpass", side_effect=passwords):
        result = migrated_file_app.test_cli_runner().invoke(args=["auth", "bootstrap"], input=PROMPTS)
    assert result.exit_code != 0
    assert message in result.output
    for password in passwords:
        assert password not in result.output
    with migrated_file_app.app_context():
        assert db.session.scalar(select(User)) is None


def test_bootstrap_refuses_echo_fallback_and_password_arguments(migrated_file_app):
    def unavailable_terminal(prompt):
        warnings.warn("Cannot disable echo", getpass.GetPassWarning)
        raise AssertionError("must abort before echoed fallback")

    with patch("neodermo.auth.cli.getpass.getpass", side_effect=unavailable_terminal):
        result = migrated_file_app.test_cli_runner().invoke(args=["auth", "bootstrap"], input=PROMPTS)
    assert result.exit_code != 0
    assert "hidden password input is required" in result.output
    rejected = migrated_file_app.test_cli_runner().invoke(args=["auth", "bootstrap", "--password"])
    assert rejected.exit_code != 0
    with migrated_file_app.app_context():
        assert db.session.scalar(select(User)) is None


def test_mailbox_confirmation_must_match_and_be_accepted(migrated_file_app):
    runner = migrated_file_app.test_cli_runner()
    with patch("neodermo.auth.cli.getpass.getpass", side_effect=AssertionError("password prompted")):
        mismatch = runner.invoke(args=["auth", "bootstrap"], input="a@example.com\nb@example.com\n")
        declined = runner.invoke(args=["auth", "bootstrap"], input="a@example.com\na@example.com\nn\n")
    assert mismatch.exit_code != 0
    assert "Email addresses did not match" in mismatch.output
    assert declined.exit_code != 0
    with migrated_file_app.app_context():
        assert db.session.scalar(select(User)) is None


def test_concurrent_provisioning_has_one_winner(migrated_file_app, file_app_factory):
    second_app = file_app_factory()
    barrier = Barrier(2)

    def simultaneous_hash(password):
        hashed = hash_new_password(password)
        barrier.wait(timeout=10)
        return hashed

    def provision(app, email):
        with app.app_context():
            try:
                return provision_operator(email, PASSWORD)
            except ProvisioningError as error:
                return str(error)

    with patch("neodermo.auth.bootstrap.hash_new_password", side_effect=simultaneous_hash):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(provision, migrated_file_app, "first@example.com"),
                pool.submit(provision, second_app, "second@example.com"),
            ]
            results = [future.result(timeout=15) for future in futures]
    assert sum("already exists" in result for result in results) == 1
    with migrated_file_app.app_context():
        users = db.session.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].id in results
        assert verify_password(users[0].password_hash, PASSWORD)


def test_missing_migration_failure_is_safe(app):
    result = app.test_cli_runner().invoke(args=["auth", "bootstrap"])
    assert result.exit_code != 0
    assert "Check database migrations" in result.output
    assert "SELECT" not in result.output
    assert "sqlite" not in result.output


@pytest.mark.parametrize("paused_prompt", ["email", "password"])
def test_bootstrap_deadline_ends_idle_prompt_and_leaves_no_operator(
    migrated_file_app, monkeypatch, paused_prompt
):
    monkeypatch.setattr("neodermo.auth.cli.BOOTSTRAP_TIMEOUT_SECONDS", 0.1)
    previous_handler = signal.getsignal(signal.SIGALRM)

    def idle_input(*args, **kwargs):
        time.sleep(0.5)
        raise AssertionError("Deadline failed to interrupt the idle prompt")

    target = (
        "neodermo.auth.cli.click.prompt" if paused_prompt == "email"
        else "neodermo.auth.cli.getpass.getpass"
    )
    with patch(target, side_effect=idle_input):
        result = migrated_file_app.test_cli_runner().invoke(
            args=["auth", "bootstrap"], input=PROMPTS
        )
    assert result.exit_code != 0
    assert "Bootstrap timed out after 0.1 seconds." in result.output
    assert "Deadline failed" not in result.output
    assert signal.getsignal(signal.SIGALRM) is previous_handler
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
    with migrated_file_app.app_context():
        assert db.session.scalar(select(User)) is None
