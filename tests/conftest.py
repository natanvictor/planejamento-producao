"""Shared pytest fixtures.

These tests exercise pure logic and mock out the Streamlit / network /
BigQuery boundaries so nothing hits the outside world.
"""
import pytest

from tests.helpers import FakeStreamlit, fake_secrets_mapping


@pytest.fixture
def fake_st():
    return FakeStreamlit()


@pytest.fixture
def fake_secrets():
    return fake_secrets_mapping()
