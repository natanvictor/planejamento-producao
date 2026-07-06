"""Tests for the BigQuery-backed data clients.

The BigQuery client is mocked; we assert on the SQL/params passed and that the
returned DataFrame is propagated unchanged.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data import bigquery_client as bq
from data import conquiste_client as cq
from data import transferencia_client as tr
from tests.helpers import fake_secrets_mapping


class _FakeQueryJob:
    def __init__(self, df):
        self._df = df

    def to_dataframe(self):
        return self._df


def _install_fake_client(monkeypatch, module, df):
    """Patch ``module._get_client`` to a mock and capture query() calls."""
    captured = {}

    def _query(query, job_config=None):
        captured["query"] = query
        captured["job_config"] = job_config
        return _FakeQueryJob(df)

    client = MagicMock()
    client.query.side_effect = _query
    monkeypatch.setattr(module, "_get_client", lambda: client)
    return captured


# ── _get_client uses gcp_project_id from secrets ─────────────────────────────
def test_bigquery_get_client_uses_project_from_secrets(monkeypatch):
    st = MagicMock()
    st.secrets = fake_secrets_mapping(gcp_project_id="my-proj")
    monkeypatch.setattr(bq, "st", st)
    fake_ctor = MagicMock(return_value="CLIENT")
    monkeypatch.setattr(bq.bigquery, "Client", fake_ctor)

    assert bq._get_client() == "CLIENT"
    fake_ctor.assert_called_once_with(project="my-proj")


# ── get_planejamento_do_dia ──────────────────────────────────────────────────
def test_get_planejamento_without_filial_has_no_params(monkeypatch):
    df = pd.DataFrame({"placa": ["A"]})
    captured = _install_fake_client(monkeypatch, bq, df)

    out = bq.get_planejamento_do_dia()
    assert out is df
    assert "@filial" not in captured["query"]
    assert captured["job_config"].query_parameters == []
    assert "ORDER BY o.ordem_prioridade ASC NULLS LAST" in captured["query"]


def test_get_planejamento_with_filial_adds_param(monkeypatch):
    df = pd.DataFrame({"placa": ["A"]})
    captured = _install_fake_client(monkeypatch, bq, df)

    bq.get_planejamento_do_dia("SP01")
    assert "AND o.filial = @filial" in captured["query"]
    params = captured["job_config"].query_parameters
    assert len(params) == 1
    assert params[0].name == "filial"
    assert params[0].value == "SP01"


# ── conquiste / transferencia just run the static query ──────────────────────
def test_get_conquiste_anomalias_returns_dataframe(monkeypatch):
    df = pd.DataFrame({"placa": ["A", "B"]})
    captured = _install_fake_client(monkeypatch, cq, df)
    out = cq.get_conquiste_anomalias()
    assert out is df
    assert captured["query"] == cq._QUERY


def test_get_transferencia_anomalias_returns_dataframe(monkeypatch):
    df = pd.DataFrame({"placa": ["A"]})
    captured = _install_fake_client(monkeypatch, tr, df)
    out = tr.get_transferencia_anomalias()
    assert out is df
    assert captured["query"] == tr._QUERY


@pytest.mark.parametrize("module", [cq, tr])
def test_get_client_passes_project_from_secrets(monkeypatch, module):
    st = MagicMock()
    st.secrets = fake_secrets_mapping(gcp_project_id="proj-x")
    monkeypatch.setattr(module, "st", st)
    fake_ctor = MagicMock(return_value="CLIENT")
    monkeypatch.setattr(module.bigquery, "Client", fake_ctor)

    assert module._get_client() == "CLIENT"
    fake_ctor.assert_called_once_with(project="proj-x")
