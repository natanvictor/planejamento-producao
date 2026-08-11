import streamlit as st
import pandas as pd

from data import plano_queries as q
from data.realtime_manutencao import enriquecer
from components.aba_tabela import render_aba

st.set_page_config(page_title="Gestão do Plano de Produção e Anomalias", layout="wide")
st.title("Gestão do Plano de Produção e Anomalias")
st.caption("Motos: BigQuery · Estado de manutenção (situação, evento, horários): **API em tempo real**")


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_bq(aba: str) -> pd.DataFrame:
    return {
        "aba1": q.get_aba1_planejamento,
        "aba2": q.get_aba2_consultor,
        "aba3": q.get_aba3_conquiste,
        "aba4": q.get_aba4_transferencia,
    }[aba]()


@st.cache_data(ttl=300, show_spinner=False)
def _enriquecer(ids: tuple) -> dict:
    return enriquecer(list(ids))


def _com_manutencao(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de manutencao em tempo real a partir do veiculoId."""
    df = df.copy()
    ids = sorted({int(v) for v in df["veiculoId"].dropna().tolist()})
    est = _enriquecer(tuple(ids))

    def get(vid, campo):
        if pd.isna(vid):
            return "" if campo != "situacao_id" else None
        return est.get(int(vid), {}).get(campo, "" if campo != "situacao_id" else None)

    df["Situação da Manutenção"] = df["veiculoId"].map(lambda v: get(v, "situacao"))
    df["_sid"] = df["veiculoId"].map(lambda v: get(v, "situacao_id"))
    df["Evento"] = df["veiculoId"].map(lambda v: get(v, "evento"))
    df["Entrou na Manutenção"] = df["veiculoId"].map(lambda v: get(v, "entrada"))
    df["Finalizada"] = df["veiculoId"].map(lambda v: get(v, "finalizada"))
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

with tab2:
    with st.spinner("Carregando plano do consultor + estado real-time…"):
        df = _carregar_bq("aba2").rename(columns={
            "placa": "Placa", "filial": "Filial", "modelo": "Modelo",
            "categoria": "Categoria", "sla": "SLA"})
        df = _com_manutencao(df)
        df["Status da Triagem"] = df["_sid"].map(
            lambda s: "Não realizado" if (pd.isna(s) or int(s) in (5, 6)) else "Triagem realizada")
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Modelo", "Categoria", "SLA", "Status da Triagem",
        "Entrou na Manutenção", "Finalizada", "_sid", "veiculoId"]), key="aba2")

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
            "Evento": "Evento Manutenção"})
        df = _com_manutencao(df).rename(columns={"Evento": "Evento Manutenção"})
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Evento Manutenção", "Situação da Manutenção", "Status do Prazo",
        "Entrou na Manutenção", "Finalizada", "_sid", "veiculoId"]), key="aba4")
