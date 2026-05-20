import streamlit as st
import pandas as pd

# ── Cores por estágio kanban ────────────────────────────────────────────────────
_KANBAN_CSS = {
    "Realizar triagem e Enviar orçamento": "background-color: #C0392B; color: white",
    "Enviar orçamento":                    "background-color: #E67E22; color: white",
    "4. Orçamento Enviado":                "background-color: #D4AC0D; color: black",
    "Realizar manutenção":                 "background-color: #2980B9; color: white",
    "6. Em Qualidade":                     "background-color: #7D3C98; color: white",
    "7. Concluída":                        "background-color: #1E8449; color: white",
}

_COLS_DISPLAY = [
    "placa", "Filial", "modelo", "produto_categoria", "diasSituacao",
    "ultimo_evento_fluxo", "kanban_coluna", "mecanico", "rampa", "Entrada", "Saída",
]

_COLS_RENAME = {
    "placa":               "Placa",
    "Filial":              "Filial",
    "modelo":              "Modelo",
    "produto_categoria":   "Produto Categoria",
    "diasSituacao":        "Dias na Situação",
    "ultimo_evento_fluxo": "Evento Manutenção",
    "kanban_coluna":       "Status",
    "mecanico":            "Mecânico",
    "rampa":               "Rampa",
    "Entrada":             "Entrada",
    "Saída":               "Saída",
}


def _color_dias(val) -> str:
    try:
        v = int(val)
        if v > 60: return "background-color: #7B241C; color: white"
        if v > 30: return "background-color: #C0392B; color: white"
        if v > 13: return "background-color: #E67E22; color: white"
        return "background-color: #D4AC0D; color: black"
    except Exception:
        return ""


def _color_kanban(val) -> str:
    return _KANBAN_CSS.get(val, "")


def render_kpi_cards_conquiste(df: pd.DataFrame) -> None:
    total        = len(df)
    cobrar       = int((df["cobranca"] == "Cobrar").sum())
    nao_cobrar   = int((df["cobranca"] == "Não Cobrar").sum())
    sem_just     = int((df["justificativa"] == "Não justificou").sum())
    orc_pend     = int((df["orcamento_pendente"] == "Sim").sum())

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🚨 Total Anomalias",      total)
    col2.metric("🔴 Cobrar",               cobrar)
    col3.metric("🟢 Não Cobrar",           nao_cobrar)
    col4.metric("⚠️ Sem Justificativa",    sem_just)
    col5.metric("⏳ Orçamento Pendente",   orc_pend)


def render_tabela_conquiste(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhuma anomalia encontrada para os filtros selecionados.")
        return

    display = df.copy()

    # Colunas que vêm da API (não disponíveis nesta aba — exibir vazio)
    display["rampa"]   = "—"
    display["Entrada"] = "—"
    display["Saída"]   = "—"

    cols_present = [c for c in _COLS_DISPLAY if c in display.columns]
    display = display[cols_present].rename(columns=_COLS_RENAME)

    styler = (
        display.style
        .map(_color_dias,   subset=["Dias na Situação"])
        .map(_color_kanban, subset=["Status"])
    )

    st.dataframe(styler, use_container_width=True, hide_index=True)
