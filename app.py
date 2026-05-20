import json
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from streamlit_autorefresh import st_autorefresh

from data.bigquery_client import get_planejamento_do_dia
from data.realtime_client import get_status_em_tempo_real
from data.conquiste_client import get_conquiste_anomalias
from components.kpi_cards import render_kpi_cards
from components.tabela_producao import render_tabela
from components.anomalias_conquiste import render_kpi_cards_conquiste, render_tabela_conquiste

st.set_page_config(
    page_title="Produção Mottu",
    layout="wide",
    initial_sidebar_state="expanded",
)

st_autorefresh(interval=300_000, key="producao_refresh")

_TZ_BR = ZoneInfo("America/Sao_Paulo")


@st.cache_resource
def _load_filiais() -> dict:
    with open("filiais.json", encoding="utf-8-sig") as f:
        return json.load(f)


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_planejamento(bq_filial: str, api_codigo: str) -> pd.DataFrame:
    planejamento = get_planejamento_do_dia(bq_filial)
    status_rt = get_status_em_tempo_real(api_codigo)
    df = planejamento.merge(status_rt, on="placa", how="left")
    df["status_atual"] = df["status_atual"].fillna("não direcionada")
    df["mecanico"] = df["mecanico"].fillna("")
    df["rampa"] = df["rampa"].fillna("")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_conquiste() -> pd.DataFrame:
    return get_conquiste_anomalias()


# ── Sidebar ────────────────────────────────────────────────────────────────────
filiais = _load_filiais()
st.sidebar.title("Filtros")
filial_selecionada = st.sidebar.selectbox("Filial (Planejamento)", list(filiais.keys()))
filial_info = filiais[filial_selecionada]
api_codigo  = filial_info["api_codigo"]
bq_filial   = filial_info.get("bq_filial", filial_selecionada)

# ── Abas ───────────────────────────────────────────────────────────────────────
tab_plan, tab_anom = st.tabs(["📋 Planejamento de Produção", "🚨 Anomalias — Conquiste"])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — PLANEJAMENTO
# ══════════════════════════════════════════════════════════════════════════════
with tab_plan:
    with st.spinner("Carregando planejamento..."):
        try:
            df_plan = _carregar_planejamento(bq_filial, api_codigo)
        except Exception as e:
            st.error(f"Erro ao carregar planejamento: {e}")
            st.stop()

    prioridades = ["Todas"] + sorted(
        df_plan["ordem_prioridade"].dropna().astype(int).unique().tolist()
    )

    c1, c2, _ = st.columns([2, 2, 6])
    status_filter    = c1.selectbox("Status", ["Todos", "não direcionada", "em andamento", "finalizada"])
    prioridade_filter = c2.selectbox("Prioridade", prioridades)

    df_plan_f = df_plan.copy()
    if status_filter != "Todos":
        df_plan_f = df_plan_f[df_plan_f["status_atual"] == status_filter]
    if prioridade_filter != "Todas":
        df_plan_f = df_plan_f[df_plan_f["ordem_prioridade"].astype("Int64") == int(prioridade_filter)]

    agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
    st.caption(f"Filial: **{filial_selecionada}** · Atualizado às {agora} · Próxima atualização em 5 min")

    render_kpi_cards(df_plan)
    st.divider()
    render_tabela(df_plan_f)
    st.caption("Planejamento: 1x/dia via BigQuery · Status: tempo real via API Mottu")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — ANOMALIAS CONQUISTE
# ══════════════════════════════════════════════════════════════════════════════
with tab_anom:
    with st.spinner("Carregando anomalias Conquiste..."):
        try:
            df_anom = _carregar_conquiste()
        except Exception as e:
            st.error(f"Erro ao carregar anomalias: {e}")
            df_anom = pd.DataFrame()

    if not df_anom.empty:
        filiais_anom = ["Todas"] + sorted(df_anom["Filial"].dropna().unique().tolist())
        cats         = ["Todas"] + sorted(df_anom["produto_categoria"].dropna().unique().tolist())

        c1, c2, _ = st.columns([2, 2, 6])
        filial_filter_anom = c1.selectbox("Filial", filiais_anom, key="filial_anom")
        cat_filter         = c2.selectbox("Produto Categoria", cats, key="cat_anom")

        df_anom_f = df_anom.copy()
        if filial_filter_anom != "Todas":
            df_anom_f = df_anom_f[df_anom_f["Filial"] == filial_filter_anom]
        if cat_filter != "Todas":
            df_anom_f = df_anom_f[df_anom_f["produto_categoria"] == cat_filter]

        agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
        st.caption(f"Atualizado às {agora} · Próxima atualização em 5 min")

        render_kpi_cards_conquiste(df_anom_f)
        st.divider()
        render_tabela_conquiste(df_anom_f)
        st.caption("Fonte: BigQuery · Motos Conquiste com cliente ativo, em manutenção e > 3 dias paradas")
