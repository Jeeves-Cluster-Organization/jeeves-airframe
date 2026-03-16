"""Pytest fixtures for jeeves-airframe tests."""

from __future__ import annotations

import pytest

from _helpers import MockRunner, make_events


@pytest.fixture
def default_events():
    return make_events()


@pytest.fixture
def mock_runner():
    return MockRunner()
