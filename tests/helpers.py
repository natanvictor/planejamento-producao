"""Test doubles shared across the test suite."""
from unittest.mock import MagicMock


class FakeColumn:
    """Stand-in for a Streamlit column: usable as a context manager and
    records ``.metric(...)`` calls."""

    def __init__(self):
        self.metric_calls = []

    def metric(self, label, value, *args, **kwargs):
        self.metric_calls.append((label, value))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeStreamlit:
    """Minimal Streamlit stand-in implementing only what the components call."""

    def __init__(self, number_input_value=1):
        self._number_input_value = number_input_value
        self.markdown_calls = []
        self.info_calls = []
        self.dataframe_calls = []
        self.last_columns = []

    def columns(self, spec):
        n = spec if isinstance(spec, int) else len(spec)
        cols = [FakeColumn() for _ in range(n)]
        self.last_columns = cols
        return cols

    def number_input(self, *args, **kwargs):
        return self._number_input_value

    def markdown(self, body, **kwargs):
        self.markdown_calls.append(body)

    def info(self, msg, **kwargs):
        self.info_calls.append(msg)

    def dataframe(self, data, **kwargs):
        self.dataframe_calls.append(data)


def fake_secrets_mapping(**overrides):
    """A MagicMock usable as both ``st.secrets["x"]`` and ``st.secrets.get``."""
    secrets = {
        "username": "user@mottu.com.br",
        "password": "pw",
        "gcp_project_id": "proj",
    }
    secrets.update(overrides)
    m = MagicMock()
    m.__getitem__.side_effect = secrets.__getitem__
    m.get.side_effect = secrets.get
    return m
