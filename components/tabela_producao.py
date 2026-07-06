import logging

import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)

_STATUS_ICONS = {
    "finalizada": "🟢",
    "em andamento": "🟡",
    "não direcionada": "🔴",
}

_RENAME = {
    "placa": "Placa",
    "modelo": "Modelo",
    "filial": "Filial",
    "ordem_prioridade": "Prioridade",
    "necessidade": "Necessidade",
    "status_col": "Status",
    "mecanico": "Mecânico",
    "rampa": "Rampa",
    "data_entrada": "Entrada",
    "saida_display": "Saída",
}

_COL_ORDER = list(_RENAME.keys())


def _fmt_ts(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        ts = pd.Timestamp(val)
        if ts is pd.NaT:
            return "—"
        if ts.tzinfo is not None:
            ts = ts.tz_convert("America/Sao_Paulo")
        return ts.strftime("%d/%m/%Y %H:%M")
    except Exception:
        logger.warning("Falha ao formatar timestamp: %r", val, exc_info=True)
        return "—"


def render_tabela(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    display = df.copy()
    display["status_col"] = display["status_atual"].map(
        lambda s: f"{_STATUS_ICONS.get(s, '')} {s}"
    )

    if "data_entrada" in display.columns:
        display["data_entrada"] = (
            pd.to_datetime(display["data_entrada"], errors="coerce")
            .dt.strftime("%d/%m/%Y %H:%M:%S")
        )
        display["data_entrada"] = display["data_entrada"].fillna("—")

    # Saída: preferência para data_saida (RT), fallback para data_finalizacao (BQ)
    saida_rt = pd.to_datetime(display.get("data_saida"), errors="coerce") if "data_saida" in display.columns else pd.Series(pd.NaT, index=display.index)
    saida_bq = pd.to_datetime(display.get("data_finalizacao"), errors="coerce") if "data_finalizacao" in display.columns else pd.Series(pd.NaT, index=display.index)
    saida = saida_rt.fillna(saida_bq)
    display["saida_display"] = saida.apply(_fmt_ts)

    cols_present = [c for c in _COL_ORDER if c in display.columns]
    st.dataframe(
        display[cols_present].rename(columns=_RENAME),
        use_container_width=True,
        hide_index=True,
    )
