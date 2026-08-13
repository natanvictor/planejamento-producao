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
def _enriquecer(vid_placa_items: tuple) -> dict:
    return enriquecer(dict(vid_placa_items))


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
