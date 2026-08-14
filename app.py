import re
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from data import plano_queries as q
from data import rampas_ativas as ra
from data import rampas_historico as rh
from data.realtime_manutencao import enriquecer
from components.aba_tabela import render_aba
from components.rampas_filial import render_rampas_colunas, altura_paineis

st.set_page_config(page_title="Gestão do Plano de Produção e Anomalias", layout="wide")
st.title("Gestão do Plano de Produção e Anomalias")
st.caption("Motos: BigQuery · Estado de manutenção (situação, evento, horários): **API em tempo real**")


@st.cache_data(ttl=300, show_spinner=False)
def _hora_atualizacao(_bucket: str) -> str:
    """Horário em que o cache de dados (5 min) foi preenchido — reflete a frescura
    real dos dados. Recalcula quando o cache expira (a cada ~5 min)."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")


st.info(
    f"Última atualização dos dados: **{_hora_atualizacao('dados')}** · "
    "atualiza ao recarregar a página — **cache de 5 min** (não é automático nem de hora em hora).",
    icon="🕒",
)


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_bq(aba: str) -> pd.DataFrame:
    return {
        "aba1": q.get_aba1_planejamento,
        "aba2": q.get_aba2_consultor,
        "aba3": q.get_aba3_conquiste,
        "aba4": q.get_aba4_transferencia,
    }[aba]()


@st.cache_data(ttl=300, show_spinner=False)
def _enriquecer(vid_placa_items: tuple) -> dict:
    return enriquecer(dict(vid_placa_items))


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_paineis(filiais: tuple) -> dict:
    return rh.montar_paineis(filiais)


def _norm_placa(s: object) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()


def _com_manutencao(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de manutencao em tempo real a partir do veiculoId.

    Passa veiculoId->placa: a placa e usada como fallback para buscar a ultima
    manutencao (inclui finalizada) das motos sem manutencao aberta.
    """
    df = df.copy()
    vp = {int(r.veiculoId): r.Placa
          for r in df[["veiculoId", "Placa"]].dropna(subset=["veiculoId"]).itertuples()}
    est = _enriquecer(tuple(sorted(vp.items())))

    def get(vid, campo):
        if pd.isna(vid):
            return "" if campo != "situacao_id" else None
        return est.get(int(vid), {}).get(campo, "" if campo != "situacao_id" else None)

    df["Situação da Manutenção"] = df["veiculoId"].map(lambda v: get(v, "situacao"))
    df["_sid"] = df["veiculoId"].map(lambda v: get(v, "situacao_id"))
    df["Evento"] = df["veiculoId"].map(lambda v: get(v, "evento"))
    df["Entrou na Manutenção"] = df["veiculoId"].map(lambda v: get(v, "entrada"))
    df["Finalizada"] = df["veiculoId"].map(lambda v: get(v, "finalizada"))
    # horarios da triagem (usados na aba 2 do Consultor)
    df["_entrada_triagem"] = df["veiculoId"].map(lambda v: get(v, "entrada_triagem"))
    df["_finalizada_triagem"] = df["veiculoId"].map(lambda v: get(v, "finalizada_triagem"))
    return df


def _ordenar(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    return df[[c for c in colunas if c in df.columns]]


tab1, tab2, tab3, tab4 = st.tabs([
    "1 · Planejamento de Produção",
    "2 · Planejamento do Consultor",
    "3 · Anomalias de Conquiste",
    "4 · Anomalias de Titular Fim do Plano",
])

with tab1:
    with st.spinner("Carregando plano + estado real-time…"):
        df = _carregar_bq("aba1").rename(columns={
            "placa": "Placa", "filial": "Filial", "categoria": "Categoria"})
        df = _com_manutencao(df)
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Categoria", "Situação da Manutenção",
        "Entrou na Manutenção", "Finalizada", "_sid", "veiculoId"]), key="aba1")

    # --- Rampas ativas por filial (ao vivo): coluna por rampa + histórico do dia ---
    # Responde aos MESMOS filtros da tabela acima (Filial), lido do session_state da
    # key do render_aba. Filtrar por filial reduz a busca (so essas filiais).
    st.divider()
    st.markdown("#### Rampas ativas por filial")
    st.caption("Ao vivo (API). Coluna = 1 rampa. Topo = rampa atual + mecânico; abaixo = "
               "placas do dia [hora · placa · cor · nível · ✓/✗]. 🟢 plano · 🔴 fora do plano · 🔵 cliente.")

    sel_filial = st.session_state.get("aba1_f", [])
    filiais_plano = [f for f in sorted(df["Filial"].dropna().astype(str).unique())
                     if not sel_filial or f in sel_filial]
    placas_plano = {_norm_placa(p) for p in df["Placa"].dropna()}

    # O histórico faz muitas chamadas (eventos por manutenção). Sem filtro de filial,
    # limita p/ nao varrer o Brasil inteiro; peça p/ filtrar por filial p/ ver todas.
    _CAP = 6
    if not sel_filial and len(filiais_plano) > _CAP:
        st.caption(f"⚠️ Mostrando as {_CAP} primeiras de {len(filiais_plano)} filiais. "
                   "Filtre por **Filial** acima para ver as demais (e carregar mais rápido).")
        filiais_plano = filiais_plano[:_CAP]

    with st.spinner("Carregando rampas + histórico do dia…"):
        paineis = _carregar_paineis(tuple(filiais_plano))

    def _categoria(tipo: object, placa: object) -> str:
        if tipo is not None and int(tipo) in ra.TIPOS_CLIENTE:
            return "cliente"
        return "planejamento" if _norm_placa(placa) in placas_plano else "nao_planejamento"

    if not paineis:
        st.caption("Nenhuma rampa ativa para o filtro atual.")
    else:
        components.html(
            render_rampas_colunas(paineis, _categoria),
            height=altura_paineis(paineis), scrolling=True)

with tab2:
    with st.spinner("Carregando plano do consultor + estado real-time…"):
        df = _carregar_bq("aba2").rename(columns={
            "placa": "Placa", "filial": "Filial", "modelo": "Modelo",
            "categoria": "Categoria", "sla": "SLA"})
        df = _com_manutencao(df)
        df["Status da Triagem"] = df["_sid"].map(
            lambda s: "Não realizado" if (pd.isna(s) or int(s) in (5, 6)) else "Triagem realizada")
        # aba 2 e so o planejamento (triagem) -> horarios sao os da TRIAGEM
        df["Iniciou Triagem"] = df["_entrada_triagem"]
        df["Finalizou Triagem"] = df["_finalizada_triagem"]
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Modelo", "Categoria", "SLA", "Status da Triagem",
        "Situação da Manutenção", "Iniciou Triagem", "Finalizou Triagem",
        "_sid", "veiculoId"]), key="aba2")

with tab3:
    with st.spinner("Carregando anomalias Conquiste + estado real-time…"):
        df = _carregar_bq("aba3").rename(columns={
            "placa": "Placa", "filial": "Filial", "diasSituacao": "Dias na Situação",
            "categoria": "Categoria", "justificativa": "Justificativa", "justificada": "Justificada?"})
        df = _com_manutencao(df)
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Dias na Situação", "Evento", "Situação da Manutenção",
        "Entrou na Manutenção", "Finalizada", "Justificativa", "Justificada?",
        "_sid", "veiculoId"]), key="aba3")

with tab4:
    with st.spinner("Carregando transferência fim do plano + estado real-time…"):
        df = _carregar_bq("aba4").rename(columns={
            "placa": "Placa", "filial": "Filial", "status_prazo": "Status do Prazo",
            "justificativa": "Justificativa", "Evento": "Evento Manutenção"})
        _venc = pd.to_datetime(df["prazo_fim_transferencia"], errors="coerce")
        df["Data de Vencimento"] = _venc.dt.strftime("%d/%m/%Y").fillna("—")
        # DATE_DIFF(prazo_fim_transferencia, hoje) -> dias ate o vencimento
        _hoje = pd.Timestamp.now(tz="America/Sao_Paulo").normalize().tz_localize(None)
        _dias = (_venc.dt.normalize() - _hoje).dt.days
        df["Dias até o Vencimento"] = _dias.apply(lambda x: "—" if pd.isna(x) else str(int(x)))
        df = _com_manutencao(df).rename(columns={"Evento": "Evento Manutenção"})
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Evento Manutenção", "Situação da Manutenção",
        "Data de Vencimento", "Dias até o Vencimento", "Status do Prazo",
        "Justificativa", "Entrou na Manutenção", "Finalizada",
        "_sid", "veiculoId"]), key="aba4")
