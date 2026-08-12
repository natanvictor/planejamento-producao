import streamlit as st
import pandas as pd

# Cores por situacaoId (robusto — a API pode variar o texto da descricao)
_VERMELHO = "#F5A9A9"   # 1 Aguardando Manutencao, 5 Aguardando Triagem, 6 Em Triagem
_AMARELO = "#FCE38A"    # 2 Manutencao, 3 Qualidade
_VERDE = "#A9DFBF"      # 4 Finalizada
_COR_SID = {1: _VERMELHO, 5: _VERMELHO, 6: _VERMELHO, 2: _AMARELO, 3: _AMARELO, 4: _VERDE}

_COR_PRAZO = {
    "Passou do Prazo": "#F5A9A9",
    "Dia de Transferencia": "#F5B971",
    "Atenção Proximo do Prazo": "#FCE38A",
    "No Prazo": "#A9DFBF",
}


def _bg(cor: str) -> str:
    return f"background-color:{cor}; color:#111" if cor else ""


def render_aba(df: pd.DataFrame, key: str) -> None:
    """Filtros (filial + placa, multiselect com busca) na tela + tabela colorida."""
    c1, c2 = st.columns(2)
    with c1:
        filiais = sorted(df["Filial"].dropna().unique().tolist())
        sel_f = st.multiselect("Filial", filiais, key=f"{key}_f", placeholder="Todas as filiais")
    with c2:
        placas = sorted(df["Placa"].dropna().unique().tolist())
        sel_p = st.multiselect("Placa", placas, key=f"{key}_p", placeholder="Todas as placas")

    d = df
    if sel_f:
        d = d[d["Filial"].isin(sel_f)]
    if sel_p:
        d = d[d["Placa"].isin(sel_p)]

    sid = d["_sid"] if "_sid" in d.columns else pd.Series(dtype="float64")

    # cartoes (KPIs) — refletem o filtro atual
    total = int(d["Placa"].nunique()) if "Placa" in d.columns else len(d)
    finalizadas = int((sid == 4).sum())
    entrou = d["Entrou na Manutenção"] if "Entrou na Manutenção" in d.columns else pd.Series(dtype=object)
    iniciou = int(entrou.replace("", pd.NA).notna().sum())
    k1, k2, k3 = st.columns(3)
    k1.metric("Motos (placas)", total)
    k2.metric("Finalizadas", finalizadas)
    k3.metric("Iniciou manutenção", iniciou)

    st.caption(f"**{len(d)}** registros")
    disp = d.drop(columns=[c for c in ("_sid", "veiculoId") if c in d.columns])

    # horarios vazios -> travessao
    for col in ("Entrou na Manutenção", "Finalizada"):
        if col in disp.columns:
            disp[col] = disp[col].replace("", "—").fillna("—")

    def _style(row: pd.Series) -> pd.Series:
        s = pd.Series("", index=row.index)
        if "Situação da Manutenção" in row.index:
            s["Situação da Manutenção"] = _bg(_COR_SID.get(sid.get(row.name), ""))
        if "Status da Triagem" in row.index:
            s["Status da Triagem"] = _bg(_VERDE if row["Status da Triagem"] == "Triagem realizada" else _VERMELHO)
        if "Justificada?" in row.index:
            s["Justificada?"] = _bg(_VERDE if row["Justificada?"] == "Justificada" else _VERMELHO)
        if "Status do Prazo" in row.index:
            s["Status do Prazo"] = _bg(_COR_PRAZO.get(row["Status do Prazo"], ""))
        return s

    styler = disp.style.apply(_style, axis=1)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=620)
