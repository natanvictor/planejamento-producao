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


def render_progress_bar(total: int, em_andamento: int, finalizados: int) -> None:
    if total == 0:
        return
    pct_fin = finalizados / total * 100
    pct_and = em_andamento / total * 100
    pct_cin = max(0.0, 100 - pct_fin - pct_and)
    nao_dir = total - em_andamento - finalizados

    st.markdown(
        f"""
        <div style="display:flex;width:100%;height:18px;border-radius:6px;
                    overflow:hidden;background:#AAAAAA;margin:10px 0 4px 0;">
            <div style="width:{pct_fin:.2f}%;background:#1E8449;"
                 title="Finalizadas: {finalizados}"></div>
            <div style="width:{pct_and:.2f}%;background:#D4AC0D;"
                 title="Em andamento: {em_andamento}"></div>
        </div>
        <div style="display:flex;gap:20px;font-size:0.78em;color:#888;margin-bottom:4px;">
            <span>🟢 Finalizadas: <b>{finalizados}</b> ({pct_fin:.0f}%)</span>
            <span>🟡 Em andamento: <b>{em_andamento}</b> ({pct_and:.0f}%)</span>
            <span>⬜ Aguardando: <b>{nao_dir}</b> ({pct_cin:.0f}%)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
