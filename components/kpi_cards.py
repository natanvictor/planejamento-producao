import streamlit as st
import pandas as pd


def render_kpi_cards(df: pd.DataFrame) -> None:
    total = len(df)
    concluidas = int((df["status_atual"] == "finalizada").sum())
    em_andamento = int((df["status_atual"] == "em andamento").sum())
    nao_direcionadas = int((df["status_atual"] == "não direcionada").sum())
    pct = (concluidas / total * 100) if total > 0 else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Planejado", total)
    col2.metric("Concluídas", concluidas)
    col3.metric("Em Andamento", em_andamento)
    col4.metric("Não Direcionadas", nao_direcionadas)
    col5.metric("% Conclusão", f"{pct:.1f}%")
