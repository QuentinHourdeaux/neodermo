"""Shared pytest fixtures.

A fixture is a reusable setup function. pytest injects it into tests
that name it as an argument — similar to a beforeEach that returns a value.
"""

import pytest

from neodermo import create_app


@pytest.fixture
def app():
    """Build a testing app that uses in-memory SQLite."""
    return create_app("testing")


@pytest.fixture
def client(app):
    """In-process HTTP client. No real port is opened."""
    return app.test_client()
