import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ_BR = ZoneInfo("America/Sao_Paulo")

_EM_ANDAMENTO = {
    "Em Execução", "Em Triagem", "Aguardando Peça", "Em Qualidade",
    "Em Manutenção", "Aguardando Aprovação", "Orçamento Enviado",
    "Aguardando Aprovação do Orçamento", "Em Análise", "Retornada para fila",
}
_FINALIZADO = {"Finalizada", "Concluída", "Finalizado"}


# ── Pagination ─────────────────────────────────────────────────────────────────

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


# ── Status mapping ─────────────────────────────────────────────────────────────

def get_status_execucao(situacao) -> str:
    if pd.isna(situacao) or str(situacao).strip() == "":
        return "🔴 Aguardando Manutenção"
    if situacao in _FINALIZADO:
        return "🟢 Finalizado"
    if situacao in _EM_ANDAMENTO:
        return "🟡 Em Andamento"
    return "🔴 Aguardando Manutenção"


def ensure_status_execucao(df: pd.DataFrame) -> pd.DataFrame:
    if "status_execucao" not in df.columns:
        df["status_execucao"] = df["situacao_manutencao"].apply(get_status_execucao)
    return df


# ── Progress bar ───────────────────────────────────────────────────────────────

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


def render_status_execucao_progress(df: pd.DataFrame) -> None:
    total = len(df)
    if "status_execucao" not in df.columns or total == 0:
        return
    finalizados = int((df["status_execucao"] == "🟢 Finalizado").sum())
    em_andamento = int((df["status_execucao"] == "🟡 Em Andamento").sum())
    render_progress_bar(total, em_andamento, finalizados)


# ── Datetime formatting ───────────────────────────────────────────────────────

def format_datetime_col(
    series: pd.Series,
    fmt: str = "%d/%m/%Y %H:%M",
    assume_utc: bool = True,
) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce", utc=assume_utc)
    if assume_utc:
        ts = ts.dt.tz_convert("America/Sao_Paulo")
    return ts.dt.strftime(fmt).fillna("—")


def prepare_anomalia_dates(df: pd.DataFrame) -> pd.DataFrame:
    if "data_finalizacao" in df.columns:
        df["Saída"] = format_datetime_col(df["data_finalizacao"])
    else:
        df["Saída"] = "—"

    if "data_entrada_manutencao" in df.columns:
        df["data_entrada_manutencao"] = format_datetime_col(df["data_entrada_manutencao"])
    else:
        df["data_entrada_manutencao"] = "—"

    return df


# ── Timestamp caption ─────────────────────────────────────────────────────────

def render_updated_caption(extra: str = "") -> None:
    agora = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M:%S")
    parts = [f"Atualizado às {agora}", "Próxima atualização em 5 min"]
    if extra:
        parts.insert(0, extra)
    st.caption(" · ".join(parts))


# ── DataFrame filtering ───────────────────────────────────────────────────────

def apply_filters(
    df: pd.DataFrame,
    filters: dict[str, str],
    all_value: str = "Todos",
) -> pd.DataFrame:
    result = df.copy()
    for col, value in filters.items():
        if value not in (all_value, "Todas"):
            result = result[result[col] == value]
    return result
