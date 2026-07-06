import numpy as np
import pandas as pd
import pytest

from components import utils
from tests.helpers import FakeStreamlit


# ── get_status_execucao ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "situacao",
    [None, np.nan, float("nan"), "", "   ", pd.NA],
)
def test_get_status_execucao_missing_returns_aguardando(situacao):
    assert utils.get_status_execucao(situacao) == "🔴 Aguardando Manutenção"


@pytest.mark.parametrize("situacao", sorted(utils._FINALIZADO))
def test_get_status_execucao_finalizado(situacao):
    assert utils.get_status_execucao(situacao) == "🟢 Finalizado"


@pytest.mark.parametrize("situacao", sorted(utils._EM_ANDAMENTO))
def test_get_status_execucao_em_andamento(situacao):
    assert utils.get_status_execucao(situacao) == "🟡 Em Andamento"


def test_get_status_execucao_unknown_value_defaults_to_aguardando():
    assert utils.get_status_execucao("Situação Inexistente") == "🔴 Aguardando Manutenção"


def test_finalizado_and_em_andamento_sets_are_disjoint():
    assert utils._FINALIZADO.isdisjoint(utils._EM_ANDAMENTO)


# ── paginar_dataframe ────────────────────────────────────────────────────────
def test_paginar_dataframe_no_pagination_when_below_page_size(fake_st, monkeypatch):
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame({"a": range(10)})
    out = utils.paginar_dataframe(df, page_size=50)
    # Returns the same object untouched and never renders a page selector.
    assert out is df
    assert fake_st.last_columns == []


def test_paginar_dataframe_returns_exact_page_size_boundary(fake_st, monkeypatch):
    monkeypatch.setattr(utils, "st", fake_st)
    df = pd.DataFrame({"a": range(50)})
    out = utils.paginar_dataframe(df, page_size=50)
    assert out is df  # total == page_size -> no pagination


def test_paginar_dataframe_first_page(monkeypatch):
    fake = FakeStreamlit(number_input_value=1)
    monkeypatch.setattr(utils, "st", fake)
    df = pd.DataFrame({"a": range(120)})
    out = utils.paginar_dataframe(df, page_size=50)
    assert list(out["a"]) == list(range(0, 50))


def test_paginar_dataframe_middle_page(monkeypatch):
    fake = FakeStreamlit(number_input_value=2)
    monkeypatch.setattr(utils, "st", fake)
    df = pd.DataFrame({"a": range(120)})
    out = utils.paginar_dataframe(df, page_size=50)
    assert list(out["a"]) == list(range(50, 100))


def test_paginar_dataframe_last_partial_page(monkeypatch):
    fake = FakeStreamlit(number_input_value=3)
    monkeypatch.setattr(utils, "st", fake)
    df = pd.DataFrame({"a": range(120)})
    out = utils.paginar_dataframe(df, page_size=50)
    assert list(out["a"]) == list(range(100, 120))


# ── render_progress_bar ──────────────────────────────────────────────────────
def test_render_progress_bar_zero_total_renders_nothing(fake_st, monkeypatch):
    monkeypatch.setattr(utils, "st", fake_st)
    utils.render_progress_bar(total=0, em_andamento=0, finalizados=0)
    assert fake_st.markdown_calls == []


def test_render_progress_bar_percentages_and_labels(fake_st, monkeypatch):
    monkeypatch.setattr(utils, "st", fake_st)
    utils.render_progress_bar(total=10, em_andamento=3, finalizados=2)
    assert len(fake_st.markdown_calls) == 1
    html = fake_st.markdown_calls[0]
    # 2/10 -> 20%, 3/10 -> 30%, aguardando 5 -> 50%
    assert "width:20.00%" in html
    assert "width:30.00%" in html
    assert "Finalizadas: <b>2</b> (20%)" in html
    assert "Em andamento: <b>3</b> (30%)" in html
    assert "Aguardando: <b>5</b> (50%)" in html


def test_render_progress_bar_clamps_negative_grey(fake_st, monkeypatch):
    monkeypatch.setattr(utils, "st", fake_st)
    # em_andamento + finalizados exceed total -> grey slice must not go negative
    utils.render_progress_bar(total=10, em_andamento=7, finalizados=6)
    html = fake_st.markdown_calls[0]
    assert "(0%)" in html  # aguardando pct clamped to 0
