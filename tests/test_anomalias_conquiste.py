import pandas as pd
import pytest

from components import anomalias_conquiste as ac
from components import utils


def _metrics(fake_st):
    out = {}
    for col in fake_st.last_columns:
        for label, value in col.metric_calls:
            out[label] = value
    return out


# ── _color_dias ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "val,expected",
    [
        (0, "background-color: #D4AC0D; color: black"),
        (13, "background-color: #D4AC0D; color: black"),
        (14, "background-color: #E67E22; color: white"),
        (30, "background-color: #E67E22; color: white"),
        (31, "background-color: #C0392B; color: white"),
        (60, "background-color: #C0392B; color: white"),
        (61, "background-color: #7B241C; color: white"),
        ("45", "background-color: #C0392B; color: white"),
    ],
)
def test_color_dias_thresholds(val, expected):
    assert ac._color_dias(val) == expected


def test_color_dias_non_numeric_returns_empty():
    assert ac._color_dias("abc") == ""
    assert ac._color_dias(None) == ""


# ── _color_kanban ────────────────────────────────────────────────────────────
def test_color_kanban_known_stage():
    assert ac._color_kanban("7. Concluída") == "background-color: #1E8449; color: white"


def test_color_kanban_unknown_returns_empty():
    assert ac._color_kanban("qualquer") == ""


# ── render_kpi_cards_conquiste ───────────────────────────────────────────────
def test_render_kpi_cards_conquiste_counts(fake_st, monkeypatch):
    monkeypatch.setattr(ac, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "cobranca": ["Cobrar", "Cobrar", "Não Cobrar"],
            "justificativa": ["Não justificou", "Falha", "Não justificou"],
            "orcamento_pendente": ["Sim", "Não", "Sim"],
            "status_execucao": ["🟢 Finalizado", "🟡 Em Andamento", "🔴 Aguardando Manutenção"],
        }
    )
    ac.render_kpi_cards_conquiste(df)
    m = _metrics(fake_st)
    assert m["🚨 Total Anomalias"] == 3
    assert m["🔴 Cobrar"] == 2
    assert m["🟢 Não Cobrar"] == 1
    assert m["⚠️ Sem Justificativa"] == 2
    assert m["⏳ Orçamento Pendente"] == 2


# ── render_tabela_conquiste ──────────────────────────────────────────────────
def test_render_tabela_conquiste_empty_shows_info(fake_st, monkeypatch):
    monkeypatch.setattr(ac, "st", fake_st)
    ac.render_tabela_conquiste(pd.DataFrame())
    assert fake_st.info_calls
    assert fake_st.dataframe_calls == []


def test_render_tabela_conquiste_renames_and_dashes(fake_st, monkeypatch):
    monkeypatch.setattr(ac, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "placa": ["ABC1234"],
            "Filial": ["SP"],
            "modelo": ["Honda"],
            "produto_categoria": ["Cat"],
            "diasSituacao": [10],
            "ultimo_evento_fluxo": ["Evt"],
            "kanban_coluna": ["7. Concluída"],
            "status_execucao": ["🟢 Finalizado"],
            "mecanico": ["João"],
            "data_entrada_manutencao": ["2024-01-15T12:00:00+00:00"],
            "data_finalizacao": [None],
        }
    )
    ac.render_tabela_conquiste(df)
    styler = fake_st.dataframe_calls[0]
    rendered = styler.data  # pandas Styler -> underlying DataFrame
    assert "Rampa" in rendered.columns
    assert rendered["Rampa"].tolist() == ["—"]
    assert rendered["Saída"].tolist() == ["—"]
    # UTC 12:00 -> 09:00 America/Sao_Paulo
    assert rendered["Entrada"].tolist() == ["15/01/2024 09:00"]
