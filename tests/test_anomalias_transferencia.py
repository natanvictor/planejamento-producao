import pandas as pd
import pytest

from components import anomalias_transferencia as at
from components import utils


def _metrics(fake_st):
    out = {}
    for col in fake_st.last_columns:
        for label, value in col.metric_calls:
            out[label] = value
    return out


# ── _color_prazo ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "val,expected",
    [
        ("Passou do Prazo", "background-color: #C0392B; color: white"),
        ("Dia de Transferencia", "background-color: #E67E22; color: white"),
        ("Atenção Proximo do Prazo", "background-color: #D4AC0D; color: black"),
        ("No Prazo", "background-color: #1E8449; color: white"),
        ("desconhecido", ""),
    ],
)
def test_color_prazo(val, expected):
    assert at._color_prazo(val) == expected


# ── render_kpi_cards_transferencia ───────────────────────────────────────────
def test_render_kpi_cards_transferencia_counts(fake_st, monkeypatch):
    monkeypatch.setattr(at, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "valida_prazo": [
                "Passou do Prazo", "Passou do Prazo",
                "Atenção Proximo do Prazo", "Dia de Transferencia", "No Prazo",
            ],
            "status_execucao": [
                "🟢 Finalizado", "🟡 Em Andamento",
                "🔴 Aguardando Manutenção", "🔴 Aguardando Manutenção", "🟢 Finalizado",
            ],
        }
    )
    at.render_kpi_cards_transferencia(df)
    m = _metrics(fake_st)
    assert m["🔄 Total Anomalias"] == 5
    assert m["🔴 Passou do Prazo"] == 2
    assert m["⚠️ Atenção Próximo do Prazo"] == 1
    assert m["🟠 Dia de Transferência"] == 1
    assert m["🟢 No Prazo"] == 1


# ── render_tabela_transferencia ──────────────────────────────────────────────
def test_render_tabela_transferencia_empty_shows_info(fake_st, monkeypatch):
    monkeypatch.setattr(at, "st", fake_st)
    at.render_tabela_transferencia(pd.DataFrame())
    assert fake_st.info_calls
    assert fake_st.dataframe_calls == []


def test_render_tabela_transferencia_fills_missing_mecanico(fake_st, monkeypatch):
    monkeypatch.setattr(at, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "placa": ["ABC1234"],
            "filial": ["SP"],
            "prazo_fim_transferencia": ["2024-01-10"],
            "data_ate_vencimento": [-5],
            "situacao_manutencao": ["Finalizada"],
            "valida_prazo": ["Passou do Prazo"],
            "status_execucao": ["🟢 Finalizado"],
            "mecanico": [None],
            "data_entrada_manutencao": [None],
        }
    )
    at.render_tabela_transferencia(df)
    rendered = fake_st.dataframe_calls[0].data
    assert rendered["Mecânico"].tolist() == ["—"]
    assert rendered["Rampa"].tolist() == ["—"]
    assert rendered["Saída"].tolist() == ["—"]
    assert rendered["Entrada"].tolist() == ["—"]


def test_render_tabela_transferencia_derives_status_when_absent(fake_st, monkeypatch):
    monkeypatch.setattr(at, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "placa": ["ABC1234"],
            "filial": ["SP"],
            "prazo_fim_transferencia": ["2024-01-10"],
            "data_ate_vencimento": [-5],
            "situacao_manutencao": ["Em Execução"],
            "valida_prazo": ["Passou do Prazo"],
        }
    )
    at.render_tabela_transferencia(df)
    rendered = fake_st.dataframe_calls[0].data
    assert rendered["Status Execução"].tolist() == ["🟡 Em Andamento"]
