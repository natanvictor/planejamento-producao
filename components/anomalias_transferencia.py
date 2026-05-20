import streamlit as st
import pandas as pd
from components.utils import get_status_execucao

_PRAZO_CSS = {
    "Passou do Prazo":          "background-color: #C0392B; color: white",
    "Dia de Transferencia":     "background-color: #E67E22; color: white",
    "Atenção Proximo do Prazo": "background-color: #D4AC0D; color: black",
    "No Prazo":                 "background-color: #1E8449; color: white",
}

_COLS_DISPLAY = [
    "placa", "filial", "prazo_fim_transferencia", "data_ate_vencimento",
    "situacao_manutencao", "valida_prazo", "status_execucao",
    "mecanico", "rampa", "Entrada", "Saída",
]

_COLS_RENAME = {
    "placa":                    "Placa",
    "filial":                   "Filial",
    "prazo_fim_transferencia":  "Prazo Fim Transferência",
    "data_ate_vencimento":      "Dias até Vencimento",
    "situacao_manutencao":      "Evento Manutenção",
    "valida_prazo":             "Valida Prazo",
    "status_execucao":          "Status Execução",
    "mecanico":                 "Mecânico",
    "rampa":                    "Rampa",
    "Entrada":                  "Entrada",
    "Saída":                    "Saída",
}


def _color_prazo(val) -> str:
    return _PRAZO_CSS.get(val, "")


def render_kpi_cards_transferencia(df: pd.DataFrame) -> None:
    total        = len(df)
    passou       = int((df["valida_prazo"] == "Passou do Prazo").sum())
    atencao      = int((df["valida_prazo"] == "Atenção Proximo do Prazo").sum())
    dia          = int((df["valida_prazo"] == "Dia de Transferencia").sum())
    no_prazo     = int((df["valida_prazo"] == "No Prazo").sum())

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🔄 Total Anomalias",              total)
    col2.metric("🔴 Passou do Prazo",              passou)
    col3.metric("⚠️ Atenção Próximo do Prazo",    atencao)
    col4.metric("🟠 Dia de Transferência",         dia)
    col5.metric("🟢 No Prazo",                     no_prazo)


def render_tabela_transferencia(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhuma anomalia de transferência encontrada para os filtros selecionados.")
        return

    display = df.copy()

    display["status_execucao"] = display["situacao_manutencao"].apply(get_status_execucao)

    # Colunas que vêm da API (não disponíveis nesta aba)
    display["mecanico"] = "—"
    display["rampa"]    = "—"
    display["Entrada"]  = "—"
    display["Saída"]    = "—"

    cols_present = [c for c in _COLS_DISPLAY if c in display.columns]
    display = display[cols_present].rename(columns=_COLS_RENAME)

    styler = (
        display.style
        .map(_color_prazo, subset=["Valida Prazo"])
    )

    st.dataframe(styler, use_container_width=True, hide_index=True)
