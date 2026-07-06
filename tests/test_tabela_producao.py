import numpy as np
import pandas as pd
import pytest

from components import tabela_producao as tp


# ── _fmt_ts ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("val", [None, np.nan, float("nan"), pd.NaT])
def test_fmt_ts_missing_returns_dash(val):
    assert tp._fmt_ts(val) == "—"


def test_fmt_ts_naive_timestamp_formatted():
    assert tp._fmt_ts("2024-01-15 08:30:00") == "15/01/2024 08:30"


def test_fmt_ts_tz_aware_converted_to_sao_paulo():
    # 12:00 UTC -> 09:00 in America/Sao_Paulo (UTC-3)
    assert tp._fmt_ts("2024-01-15T12:00:00+00:00") == "15/01/2024 09:00"


def test_fmt_ts_invalid_string_returns_dash():
    assert tp._fmt_ts("not-a-date") == "—"


# ── render_tabela ────────────────────────────────────────────────────────────
def test_render_tabela_empty_shows_info(fake_st, monkeypatch):
    monkeypatch.setattr(tp, "st", fake_st)
    tp.render_tabela(pd.DataFrame())
    assert fake_st.info_calls
    assert fake_st.dataframe_calls == []


def test_render_tabela_builds_status_column_and_renames(fake_st, monkeypatch):
    monkeypatch.setattr(tp, "st", fake_st)
    df = pd.DataFrame(
        {
            "placa": ["ABC1234", "XYZ9876"],
            "modelo": ["Honda", "Yamaha"],
            "ordem_prioridade": [1, 2],
            "necessidade": ["Revisão", "Troca"],
            "status_atual": ["finalizada", "não direcionada"],
            "data_entrada": ["2024-01-15 08:30:00", None],
            "data_finalizacao": ["2024-01-16 10:00:00", None],
        }
    )
    tp.render_tabela(df)

    assert len(fake_st.dataframe_calls) == 1
    rendered = fake_st.dataframe_calls[0]
    # Icons prefixed onto status values.
    assert rendered["Status"].tolist() == ["🟢 finalizada", "🔴 não direcionada"]
    # Renamed, ordered columns.
    assert list(rendered.columns) == [
        "Placa", "Modelo", "Prioridade", "Necessidade", "Status", "Entrada", "Saída",
    ]
    # Entrada uses seconds precision; missing value -> dash.
    assert rendered["Entrada"].tolist() == ["15/01/2024 08:30:00", "—"]
    # Missing data_finalizacao -> dash; present -> formatted.
    assert rendered["Saída"].tolist() == ["16/01/2024 10:00", "—"]


def test_render_tabela_prefers_data_saida_over_finalizacao(fake_st, monkeypatch):
    monkeypatch.setattr(tp, "st", fake_st)
    df = pd.DataFrame(
        {
            "placa": ["ABC1234"],
            "status_atual": ["finalizada"],
            "data_saida": ["2024-02-01 11:00:00"],
            "data_finalizacao": ["2024-03-01 11:00:00"],
        }
    )
    tp.render_tabela(df)
    rendered = fake_st.dataframe_calls[0]
    assert rendered["Saída"].tolist() == ["01/02/2024 11:00"]


def test_render_tabela_unknown_status_has_empty_icon(fake_st, monkeypatch):
    monkeypatch.setattr(tp, "st", fake_st)
    df = pd.DataFrame({"placa": ["A"], "status_atual": ["desconhecido"]})
    tp.render_tabela(df)
    rendered = fake_st.dataframe_calls[0]
    assert rendered["Status"].tolist() == [" desconhecido"]
