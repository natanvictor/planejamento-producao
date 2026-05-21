import streamlit as st
import pandas as pd

_EM_ANDAMENTO = {
    "Em Execução", "Em Triagem", "Aguardando Peça", "Em Qualidade",
    "Em Manutenção", "Aguardando Aprovação", "Orçamento Enviado",
    "Aguardando Aprovação do Orçamento", "Em Análise", "Retornada para fila",
}
_FINALIZADO = {"Finalizada", "Concluída", "Finalizado"}


def paginar_dataframe(df: pd.DataFrame, page_size: int = 50, key: str = "page") -> pd.DataFrame:
    total = len(df)
    if total <= page_size:
        return df
    n_pages = (total + page_size - 1) // page_size
    _, col_center, _ = st.columns([2, 3, 2])
    with col_center:
        page = st.number_input(
            f"Página — {total} registros · {n_pages} páginas",
            min_value=1, max_value=n_pages, value=1, step=1, key=key,
        )
    start = (page - 1) * page_size
    return df.iloc[start : start + page_size]


def get_status_execucao(situacao) -> str:
    if pd.isna(situacao) or str(situacao).strip() == "":
        return "🔴 Aguardando Manutenção"
    if situacao in _FINALIZADO:
        return "🟢 Finalizado"
    if situacao in _EM_ANDAMENTO:
        return "🟡 Em Andamento"
    return "🔴 Aguardando Manutenção"
