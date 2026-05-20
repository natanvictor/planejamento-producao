import json
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from streamlit_autorefresh import st_autorefresh

from data.bigquery_client import get_planejamento_do_dia
from data.realtime_client import get_status_em_tempo_real
from data.conquiste_client import get_conquiste_anomalias
from data.transferencia_client import get_transferencia_anomalias
from components.kpi_cards import render_kpi_cards
from components.tabela_producao import render_tabela
from components.anomalias_conquiste import render_kpi_cards_conquiste, render_tabela_conquiste
from components.anomalias_transferencia import render_kpi_cards_transferencia, render_tabela_transferencia
from components.utils import get_status_execucao

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


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_transferencia() -> pd.DataFrame:
    return get_transferencia_anomalias()


# ── Sidebar ────────────────────────────────────────────────────────────────────
filiais = _load_filiais()
st.sidebar.title("Filtros")
filial_selecionada = st.sidebar.selectbox("Filial (Planejamento)", list(filiais.keys()))
filial_info = filiais[filial_selecionada]
api_codigo  = filial_info["api_codigo"]
bq_filial   = filial_info.get("bq_filial", filial_selecionada)

# ── Abas ───────────────────────────────────────────────────────────────────────
tab_plan, tab_anom, tab_trans = st.tabs([
    "📋 Planejamento de Produção",
    "🚨 Anomalias — Conquiste",
    "🔄 Anomalias — Transferência",
])

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
        # Deriva status_execucao aqui para poder filtrar por ele
        df_anom["status_execucao"] = df_anom["situacao_manutencao"].apply(get_status_execucao)

        filiais_anom = ["Todas"] + sorted(df_anom["Filial"].dropna().unique().tolist())
        cats         = ["Todas"] + sorted(df_anom["produto_categoria"].dropna().unique().tolist())
        eventos      = ["Todos"] + sorted(df_anom["ultimo_evento_fluxo"].dropna().unique().tolist())
        status_exec_opts = ["Todos", "🔴 Aguardando Manutenção", "🟡 Em Andamento", "🟢 Finalizado"]
        cobranca_opts    = ["Todos", "Cobrar", "Não Cobrar"]

        # Linha 1 de filtros
        c1, c2, c3, c4 = st.columns(4)
        filial_filter_anom  = c1.selectbox("Filial",             filiais_anom,     key="filial_anom")
        cat_filter          = c2.selectbox("Produto Categoria",  cats,             key="cat_anom")
        cobranca_filter     = c3.selectbox("Cobrança",           cobranca_opts,    key="cobranca_anom")
        status_exec_filter  = c4.selectbox("Status Execução",    status_exec_opts, key="status_exec_anom")

        # Linha 2 de filtros
        c5, c6, _ = st.columns([2, 4, 4])
        placa_filter  = c5.text_input("Placa", key="placa_anom", placeholder="ex: ABC1234")
        evento_filter = c6.selectbox("Evento Manutenção", eventos, key="evento_anom")

        df_anom_f = df_anom.copy()
        if filial_filter_anom != "Todas":
            df_anom_f = df_anom_f[df_anom_f["Filial"] == filial_filter_anom]
        if cat_filter != "Todas":
            df_anom_f = df_anom_f[df_anom_f["produto_categoria"] == cat_filter]
        if cobranca_filter != "Todos":
            df_anom_f = df_anom_f[df_anom_f["cobranca"] == cobranca_filter]
        if status_exec_filter != "Todos":
            df_anom_f = df_anom_f[df_anom_f["status_execucao"] == status_exec_filter]
        if placa_filter.strip():
            df_anom_f = df_anom_f[df_anom_f["placa"].str.contains(placa_filter.strip(), case=False, na=False)]
        if evento_filter != "Todos":
            df_anom_f = df_anom_f[df_anom_f["ultimo_evento_fluxo"] == evento_filter]

        agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
        st.caption(f"Atualizado às {agora} · Próxima atualização em 5 min")

        render_kpi_cards_conquiste(df_anom_f)
        st.divider()
        render_tabela_conquiste(df_anom_f)
        st.caption("Fonte: BigQuery · Motos Conquiste com cliente ativo, em manutenção e > 3 dias paradas")

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — ANOMALIAS TRANSFERÊNCIA
# ══════════════════════════════════════════════════════════════════════════════
with tab_trans:
    with st.spinner("Carregando anomalias de transferência..."):
        try:
            df_trans = _carregar_transferencia()
        except Exception as e:
            st.error(f"Erro ao carregar transferências: {e}")
            df_trans = pd.DataFrame()

    if not df_trans.empty:
        # Deriva status_execucao para poder filtrar
        df_trans["status_execucao"] = df_trans["situacao_manutencao"].apply(get_status_execucao)

        filiais_trans    = ["Todas"] + sorted(df_trans["filial"].dropna().unique().tolist())
        prazos           = ["Todos"] + [
            "Passou do Prazo", "Atenção Proximo do Prazo",
            "Dia de Transferencia", "No Prazo",
        ]
        status_exec_opts = ["Todos", "🔴 Aguardando Manutenção", "🟡 Em Andamento", "🟢 Finalizado"]

        c1, c2, c3, _ = st.columns([2, 2, 2, 4])
        filial_filter_trans = c1.selectbox("Filial",          filiais_trans,    key="filial_trans")
        prazo_filter        = c2.selectbox("Valida Prazo",    prazos,           key="prazo_trans")
        status_exec_trans   = c3.selectbox("Status Execução", status_exec_opts, key="status_exec_trans")

        df_trans_f = df_trans.copy()
        if filial_filter_trans != "Todas":
            df_trans_f = df_trans_f[df_trans_f["filial"] == filial_filter_trans]
        if prazo_filter != "Todos":
            df_trans_f = df_trans_f[df_trans_f["valida_prazo"] == prazo_filter]
        if status_exec_trans != "Todos":
            df_trans_f = df_trans_f[df_trans_f["status_execucao"] == status_exec_trans]

        agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
        st.caption(f"Atualizado às {agora} · Próxima atualização em 5 min")

        render_kpi_cards_transferencia(df_trans_f)
        st.divider()
        render_tabela_transferencia(df_trans_f)
        st.caption("Fonte: BigQuery · Motos Minha Mottu com prazo de transferência vencido")
