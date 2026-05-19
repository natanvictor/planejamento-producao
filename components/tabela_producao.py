import streamlit as st
import pandas as pd

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
    "data_saida": "Saída",
}

_COL_ORDER = list(_RENAME.keys())


def render_tabela(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    display = df.copy()
    display["status_col"] = display["status_atual"].map(
        lambda s: f"{_STATUS_ICONS.get(s, '')} {s}"
    )

    for col in ("data_entrada", "data_saida"):
        if col in display.columns:
            display[col] = pd.to_datetime(display[col], errors="coerce").dt.strftime("%H:%M")
            display[col] = display[col].fillna("—")

    cols_present = [c for c in _COL_ORDER if c in display.columns]
    st.dataframe(
        display[cols_present].rename(columns=_RENAME),
        use_container_width=True,
        hide_index=True,
    )
