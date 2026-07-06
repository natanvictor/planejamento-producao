"""Tests for data.realtime_client.

Every network call goes through the module-level ``requests``; we replace it
with a MagicMock and drive responses per-URL. ``st.secrets`` is stubbed too.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data import realtime_client as rc
from tests.helpers import fake_secrets_mapping


def _resp(json_data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.raise_for_status = MagicMock()
    return r


@pytest.fixture
def patched_st(monkeypatch):
    st = MagicMock()
    st.secrets = fake_secrets_mapping()
    monkeypatch.setattr(rc, "st", st)
    return st


# ── _headers ─────────────────────────────────────────────────────────────────
def test_headers_builds_bearer():
    assert rc._headers("abc") == {
        "Authorization": "Bearer abc",
        "Content-Type": "application/json",
    }


# ── _get_token ───────────────────────────────────────────────────────────────
def test_get_token_returns_access_token(patched_st, monkeypatch):
    req = MagicMock()
    req.post.return_value = _resp({"access_token": "TOK123"})
    monkeypatch.setattr(rc, "requests", req)

    assert rc._get_token() == "TOK123"
    # Password grant against the SSO endpoint.
    args, kwargs = req.post.call_args
    assert args[0] == rc._SSO_URL
    assert kwargs["data"]["grant_type"] == "password"
    assert kwargs["data"]["username"] == "user@mottu.com.br"


# ── _get_branch_guid ─────────────────────────────────────────────────────────
def test_get_branch_guid_extracts_first_result_id(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp({"result": [{"id": "guid-1"}, {"id": "guid-2"}]})
    monkeypatch.setattr(rc, "requests", req)

    assert rc._get_branch_guid("tok", "FILIAL01") == "guid-1"
    url = req.get.call_args[0][0]
    assert "codes=FILIAL01" in url


# ── _get_mechanic_position_ids ───────────────────────────────────────────────
def test_get_mechanic_position_ids_filters_by_known_positions(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp(
        {
            "result": [
                {"id": "p1", "name": "Mecânico I"},
                {"id": "p2", "name": "Gerente"},          # not a mechanic
                {"id": "p3", "name": "Auxiliar de Mecânico"},
            ]
        }
    )
    monkeypatch.setattr(rc, "requests", req)

    assert rc._get_mechanic_position_ids("tok") == ["p1", "p3"]


def test_get_mechanic_position_ids_handles_items_wrapper(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp(
        {"result": {"items": [{"id": "p1", "name": "Mecânico II"}]}}
    )
    monkeypatch.setattr(rc, "requests", req)

    assert rc._get_mechanic_position_ids("tok") == ["p1"]


def test_get_mechanic_position_ids_no_match_returns_empty(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp({"result": [{"id": "p1", "name": "Faxineiro"}]})
    monkeypatch.setattr(rc, "requests", req)

    assert rc._get_mechanic_position_ids("tok") == []


# ── _get_mecanicos ───────────────────────────────────────────────────────────
def test_get_mecanicos_excludes_fired_and_builds_url(patched_st, monkeypatch):
    monkeypatch.setattr(rc, "_get_branch_guid", lambda tok, code: "BGUID")
    monkeypatch.setattr(rc, "_get_mechanic_position_ids", lambda tok: ["pid1", "pid2"])

    req = MagicMock()
    req.get.return_value = _resp(
        {
            "result": [
                {"fullName": "Ana", "code": "A1", "isFired": False},
                {"fullName": "Bruno", "code": "B2", "isFired": True},
                {"fullName": "Carla", "code": "C3"},  # missing isFired -> active
            ]
        }
    )
    monkeypatch.setattr(rc, "requests", req)

    result = rc._get_mecanicos("tok", "FILIAL01")
    assert result == [
        {"fullName": "Ana", "code": "A1"},
        {"fullName": "Carla", "code": "C3"},
    ]
    url = req.get.call_args[0][0]
    assert "BranchId=BGUID" in url
    assert "PositionId=pid1" in url and "PositionId=pid2" in url


# ── _get_manutencoes_hoje ────────────────────────────────────────────────────
def test_get_manutencoes_hoje_filters_to_today(patched_st, monkeypatch):
    hoje = datetime.now(rc._TZ_BR).date().isoformat()
    req = MagicMock()
    req.get.return_value = _resp(
        {
            "dataResult": {
                "manutencoes": [
                    {"id": 1, "placa": "AAA", "situacao": 2, "atualizacaoData": f"{hoje}T09:00:00"},
                    {"id": 2, "placa": "BBB", "situacao": 4, "atualizacaoData": "2000-01-01T09:00:00"},
                ]
            }
        }
    )
    monkeypatch.setattr(rc, "requests", req)

    result = rc._get_manutencoes_hoje("tok", "MEC1")
    assert result == [{"id": 1, "placa": "AAA", "situacao": 2}]


def test_get_manutencoes_hoje_non_200_returns_empty(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp({}, status=500)
    monkeypatch.setattr(rc, "requests", req)
    assert rc._get_manutencoes_hoje("tok", "MEC1") == []


# ── _get_eventos ─────────────────────────────────────────────────────────────
def test_get_eventos_picks_last_entrada_saida_and_rampa(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp(
        {
            "dataResult": [
                {"criacaoDataUTC": "2024-01-15T10:00:00Z", "criacaoData": "2024-01-15T10:00:00Z",
                 "situacaoId": 2, "deviceName": "Rampa 1"},
                {"criacaoDataUTC": "2024-01-15T11:00:00Z", "criacaoData": "2024-01-15T11:00:00Z",
                 "situacaoId": 2, "deviceName": "Rampa 2"},  # later entrada wins
                {"criacaoDataUTC": "2024-01-15T12:00:00Z", "criacaoData": "2024-01-15T12:00:00Z",
                 "situacaoId": 4},  # saida
            ]
        }
    )
    monkeypatch.setattr(rc, "requests", req)

    ev = rc._get_eventos("tok", "M1")
    assert ev["rampa"] == "Rampa 2"
    # 11:00 UTC -> 08:00 BR ; 12:00 UTC -> 09:00 BR
    assert ev["data_entrada"].strftime("%H:%M") == "08:00"
    assert ev["data_saida"].strftime("%H:%M") == "09:00"


def test_get_eventos_non_200_returns_empty_dict(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp({}, status=404)
    monkeypatch.setattr(rc, "requests", req)
    assert rc._get_eventos("tok", "M1") == {}


def test_get_eventos_skips_events_without_timestamp(patched_st, monkeypatch):
    req = MagicMock()
    req.get.return_value = _resp(
        {"dataResult": [{"criacaoDataUTC": "2024-01-15T10:00:00Z", "situacaoId": 2, "criacaoData": ""}]}
    )
    monkeypatch.setattr(rc, "requests", req)
    ev = rc._get_eventos("tok", "M1")
    assert ev == {"rampa": "", "data_entrada": None, "data_saida": None}


# ── get_status_em_tempo_real ─────────────────────────────────────────────────
def test_get_status_no_mecanicos_returns_empty_df(patched_st, monkeypatch):
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(rc, "_get_mecanicos", lambda tok, code: [])

    df = rc.get_status_em_tempo_real("FILIAL01")
    assert df.empty
    assert list(df.columns) == [
        "placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"
    ]


def test_get_status_maps_situacao_and_dedups(patched_st, monkeypatch):
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(
        rc, "_get_mecanicos", lambda tok, code: [{"fullName": "Ana", "code": "A1"}]
    )
    monkeypatch.setattr(
        rc,
        "_get_manutencoes_hoje",
        lambda tok, mec: [
            {"id": 1, "placa": "AAA", "situacao": 2},   # em andamento
            {"id": 2, "placa": "BBB", "situacao": 4},   # finalizada
            {"id": 3, "placa": "CCC", "situacao": 1},   # skipped (not 2/4)
            {"id": 4, "placa": "", "situacao": 2},      # skipped (no placa)
        ],
    )
    monkeypatch.setattr(
        rc, "_get_eventos",
        lambda tok, mid: {"rampa": "R1", "data_entrada": None, "data_saida": None},
    )

    df = rc.get_status_em_tempo_real("FILIAL01")
    by_placa = df.set_index("placa")["status_atual"].to_dict()
    assert by_placa == {"AAA": "em andamento", "BBB": "finalizada"}
    assert "CCC" not in by_placa


def test_get_status_string_situacao_normalized(patched_st, monkeypatch):
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(
        rc, "_get_mecanicos", lambda tok, code: [{"fullName": "Ana", "code": "A1"}]
    )
    monkeypatch.setattr(
        rc, "_get_manutencoes_hoje",
        lambda tok, mec: [{"id": 1, "placa": "AAA", "situacao": "4"}],
    )
    monkeypatch.setattr(
        rc, "_get_eventos",
        lambda tok, mid: {"rampa": "", "data_entrada": None, "data_saida": None},
    )
    df = rc.get_status_em_tempo_real("FILIAL01")
    assert df.loc[0, "status_atual"] == "finalizada"


def test_get_status_finalizada_not_overwritten(patched_st, monkeypatch):
    """A placa already marked finalizada must not be downgraded by a later
    'em andamento' record for the same plate."""
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(
        rc, "_get_mecanicos", lambda tok, code: [{"fullName": "Ana", "code": "A1"}]
    )
    monkeypatch.setattr(
        rc, "_get_manutencoes_hoje",
        lambda tok, mec: [
            {"id": 1, "placa": "AAA", "situacao": 4},
            {"id": 2, "placa": "AAA", "situacao": 2},
        ],
    )
    monkeypatch.setattr(
        rc, "_get_eventos",
        lambda tok, mid: {"rampa": "", "data_entrada": None, "data_saida": None},
    )
    df = rc.get_status_em_tempo_real("FILIAL01")
    assert df.set_index("placa")["status_atual"].to_dict() == {"AAA": "finalizada"}


def test_get_status_unparseable_situacao_is_skipped(patched_st, monkeypatch):
    """A situacao that cannot be coerced to int falls through to -1 and is
    skipped rather than raising."""
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(
        rc, "_get_mecanicos", lambda tok, code: [{"fullName": "Ana", "code": "A1"}]
    )
    monkeypatch.setattr(
        rc, "_get_manutencoes_hoje",
        lambda tok, mec: [
            {"id": 1, "placa": "AAA", "situacao": "não é número"},
            {"id": 2, "placa": "BBB", "situacao": None},
        ],
    )
    df = rc.get_status_em_tempo_real("FILIAL01")
    assert df.empty


def test_get_status_all_skipped_returns_empty_df(patched_st, monkeypatch):
    monkeypatch.setattr(rc, "_get_token", lambda: "tok")
    monkeypatch.setattr(
        rc, "_get_mecanicos", lambda tok, code: [{"fullName": "Ana", "code": "A1"}]
    )
    monkeypatch.setattr(
        rc, "_get_manutencoes_hoje",
        lambda tok, mec: [{"id": 3, "placa": "CCC", "situacao": 1}],
    )
    df = rc.get_status_em_tempo_real("FILIAL01")
    assert df.empty
    assert list(df.columns) == [
        "placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"
    ]
