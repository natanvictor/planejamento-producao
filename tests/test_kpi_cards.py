import pandas as pd

from components import kpi_cards
from components import utils


def _metrics(fake_st):
    """Flatten all (label, value) metric calls across the fake columns."""
    out = {}
    for col in fake_st.last_columns:
        for label, value in col.metric_calls:
            out[label] = value
    return out


def test_render_kpi_cards_counts_and_percentage(fake_st, monkeypatch):
    monkeypatch.setattr(kpi_cards, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame(
        {
            "status_atual": [
                "finalizada", "finalizada", "em andamento",
                "não direcionada", "não direcionada", "não direcionada",
            ]
        }
    )
    kpi_cards.render_kpi_cards(df)
    m = _metrics(fake_st)
    assert m["Total Planejado"] == 6
    assert m["Concluídas"] == 2
    assert m["Em Andamento"] == 1
    assert m["Não Direcionadas"] == 3
    assert m["% Conclusão"] == "33.3%"


def test_render_kpi_cards_empty_dataframe_zero_percent(fake_st, monkeypatch):
    monkeypatch.setattr(kpi_cards, "st", fake_st)
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame({"status_atual": []})
    kpi_cards.render_kpi_cards(df)
    m = _metrics(fake_st)
    assert m["Total Planejado"] == 0
    assert m["% Conclusão"] == "0.0%"
