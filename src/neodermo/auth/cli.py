"""Interactive local auth commands. No password command-line arguments."""

import getpass
import signal
import warnings
from contextlib import contextmanager
from collections.abc import Iterator

import click
from flask.cli import AppGroup

from neodermo.auth.bootstrap import ProvisioningError, operator_exists, provision_operator
from neodermo.auth.cleanup import CleanupUnavailable, cleanup_expired
from neodermo.auth.validation import normalize_email

auth_cli = AppGroup("auth", help="Manage the locally provisioned operator.")
BOOTSTRAP_TIMEOUT_SECONDS = 120


class BootstrapTimedOut(Exception):
    """The interactive command exceeded its total wall-clock deadline."""


@contextmanager
def _bootstrap_deadline() -> Iterator[None]:
    """Bound the command's lifetime, including waits for terminal input.

    SIGALRM interrupts blocking reads on the supported macOS/Linux hosts. The
    previous handler is restored even when a prompt or database write fails.
    """
    if not hasattr(signal, "setitimer"):
        raise click.ClickException("Interactive bootstrap requires a Unix terminal.")
    previous_handler = signal.getsignal(signal.SIGALRM)
    if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
        raise click.ClickException("Cannot bootstrap while another process timer is active.")

    def expire(signum: int, frame: object) -> None:
        raise BootstrapTimedOut

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, BOOTSTRAP_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


@auth_cli.command("bootstrap")
def bootstrap() -> None:
    """Confirm the recovery mailbox and read a password without echo."""
    try:
        with _bootstrap_deadline():
            if operator_exists():
                raise ProvisioningError("An operator already exists; no account was created.")
            email = normalize_email(click.prompt("Recovery email"))
            confirmation = normalize_email(click.prompt("Confirm recovery email"))
            if email != confirmation:
                raise ValueError("Email addresses did not match.")
            click.confirm("Is this a recovery mailbox you control?", abort=True)
            # getpass normally falls back to echoed input when no terminal exists.
            # Refuse that fallback instead of accidentally exposing a password.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Password: ")
                confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                raise ValueError("Passwords did not match.")
            provision_operator(email, password)
    except BootstrapTimedOut:
        raise click.ClickException(
            f"Bootstrap timed out after {BOOTSTRAP_TIMEOUT_SECONDS} seconds."
        ) from None
    except getpass.GetPassWarning:
        raise click.ClickException("A terminal with hidden password input is required.") from None
    except (ValueError, ProvisioningError) as error:
        raise click.ClickException(str(error)) from None
    except EOFError:
        raise click.Abort() from None
    click.echo("Operator created.")


@auth_cli.command("cleanup")
def cleanup() -> None:
    """Delete expired sessions and password-reset tokens."""
    try:
        sessions, reset_tokens = cleanup_expired()
    except CleanupUnavailable:
        raise click.ClickException(
            "Could not clean up expired credentials. "
            "Check database availability and migrations."
        ) from None
    click.echo(f"Deleted {sessions} expired sessions and {reset_tokens} expired reset tokens.")
