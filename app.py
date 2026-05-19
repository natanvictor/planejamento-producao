import json
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from streamlit_autorefresh import st_autorefresh

from data.bigquery_client import get_planejamento_do_dia
from data.realtime_client import get_status_em_tempo_real
from components.kpi_cards import render_kpi_cards
from components.tabela_producao import render_tabela

st.set_page_config(
    page_title="Planejamento de Produção",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh a cada 5 minutos (300_000 ms)
st_autorefresh(interval=300_000, key="producao_refresh")

_TZ_BR = ZoneInfo("America/Sao_Paulo")


@st.cache_resource
def _load_filiais() -> dict:
    with open("filiais.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados(bq_filial: str, api_codigo: str) -> pd.DataFrame:
    planejamento = get_planejamento_do_dia(bq_filial)
    status_rt = get_status_em_tempo_real(api_codigo)

    df = planejamento.merge(status_rt, on="placa", how="left")
    df["status_atual"] = df["status_atual"].fillna("não direcionada")
    df["mecanico"] = df["mecanico"].fillna("")
    df["rampa"] = df["rampa"].fillna("")
    return df


# ── Sidebar ────────────────────────────────────────────────────────────────────
filiais = _load_filiais()

st.sidebar.title("Filtros")

filial_selecionada = st.sidebar.selectbox("Filial", list(filiais.keys()))
filial_info = filiais[filial_selecionada]
api_codigo = filial_info["api_codigo"]
bq_filial = filial_info.get("bq_filial", filial_selecionada)

status_filter = st.sidebar.selectbox(
    "Status",
    ["Todos", "não direcionada", "em andamento", "finalizada"],
)

# ── Carrega dados ──────────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    try:
        df = _carregar_dados(bq_filial, api_codigo)
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.stop()

prioridades = ["Todas"] + sorted(
    df["ordem_prioridade"].dropna().astype(int).unique().tolist()
)
prioridade_filter = st.sidebar.selectbox("Prioridade", prioridades)

# ── Filtros ────────────────────────────────────────────────────────────────────
df_filtered = df.copy()
if status_filter != "Todos":
    df_filtered = df_filtered[df_filtered["status_atual"] == status_filter]
if prioridade_filter != "Todas":
    df_filtered = df_filtered[df_filtered["ordem_prioridade"].astype("Int64") == int(prioridade_filter)]

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("Planejamento de Produção")
agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
st.caption(
    f"Filial: **{filial_selecionada}** · Atualizado às {agora} · "
    "Próxima atualização em 5 minutos"
)

st.divider()

# ── KPIs ───────────────────────────────────────────────────────────────────────
render_kpi_cards(df)

st.divider()

# ── Tabela ─────────────────────────────────────────────────────────────────────
render_tabela(df_filtered)

st.caption(
    "Planejamento: atualizado 1x/dia via BigQuery · "
    "Status em tempo real: atualizado a cada 5 min via API Mottu"
)
