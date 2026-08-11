import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ_BR = ZoneInfo("America/Sao_Paulo")


def _fmt_hora(val) -> str:
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
        return "—"


def _duracao_horas(data_entrada, data_saida) -> float | None:
    """entrada→saída (finalizada) ou entrada→agora (em andamento), em horas."""
    if data_entrada is None or (isinstance(data_entrada, float) and pd.isna(data_entrada)):
        return None
    ent = pd.Timestamp(data_entrada)
    if ent is pd.NaT:
        return None
    if ent.tzinfo is None:
        ent = ent.tz_localize("America/Sao_Paulo")

    if data_saida is not None and not (isinstance(data_saida, float) and pd.isna(data_saida)):
        fim = pd.Timestamp(data_saida)
        if fim is not pd.NaT and fim.tzinfo is None:
            fim = fim.tz_localize("America/Sao_Paulo")
    else:
        fim = pd.Timestamp(datetime.now(_TZ_BR))

    if fim is pd.NaT:
        return None
    return round((fim - ent).total_seconds() / 3600, 1)


# ── Análise comparativa — Planejamento x Internas (fora do plano) ────────────────
def render_analise_comparativa(
    df_plan_bq: pd.DataFrame,
    status_rt: pd.DataFrame,
    df_manut: pd.DataFrame,
    placas_planejamento: set,
) -> None:
    st.subheader("Análise comparativa — Planejamento x Internas (fora do plano)")
    st.caption(
        "Testa a hipótese das bases: as motos do planejamento são mais difíceis "
        "(nível/tempo maiores) do que as internas fora do plano?"
    )

    if status_rt.empty:
        st.info("Sem dados em tempo real para a análise.")
        return

    d = status_rt.copy()
    d["duracao_h"] = d.apply(
        lambda r: _duracao_horas(r.get("data_entrada"), r.get("data_saida")), axis=1
    )

    # Nível e tempo estimado por placa (BQ). df_manut cobre todas as placas da filial;
    # df_plan_bq preenche eventuais faltantes do planejamento.
    nivel_map: dict = {}
    tempo_map: dict = {}
    if not df_manut.empty:
        for _, r in df_manut.iterrows():
            nivel_map[r["placa"]] = r.get("nivel_manutencao")
            tempo_map[r["placa"]] = r.get("tempo_estimado_execucao")
    if not df_plan_bq.empty:
        for _, r in df_plan_bq.iterrows():
            nivel_map.setdefault(r["placa"], r.get("nivel_manutencao"))
            tempo_map.setdefault(r["placa"], r.get("tempo_estimado_execucao"))
    d["nivel"] = d["placa"].map(nivel_map)
    d["tempo_est"] = d["placa"].map(tempo_map)

    grp_plan = d[d["placa"].isin(placas_planejamento)]
    grp_int  = d[(d["tipo_manutencao"] == "Interna") & (~d["placa"].isin(placas_planejamento))]

    def _stats(g: pd.DataFrame) -> dict:
        fin = g[g["status_atual"] == "finalizada"]
        tempo     = fin["duracao_h"].dropna()
        tempo_est = pd.to_numeric(g["tempo_est"], errors="coerce").dropna()
        nivel     = pd.to_numeric(g["nivel"], errors="coerce").dropna()
        return {
            "qtd":           len(g),
            "qtd_fin":       len(fin),
            "tempo_med":     round(float(tempo.mean()), 1)     if len(tempo) else None,
            "tempo_est_med": round(float(tempo_est.mean()), 0) if len(tempo_est) else None,
            "nivel_med":     round(float(nivel.mean()), 2)     if len(nivel) else None,
            "nivel_moda":    int(nivel.mode().iloc[0])         if len(nivel) else None,
        }

    sp = _stats(grp_plan)
    si = _stats(grp_int)

    def _fmt(v) -> str:
        return "—" if v is None else f"{v}"

    tabela = pd.DataFrame({
        "Métrica": [
            "Qtd motos (em execução)",
            "Qtd finalizadas (base do tempo)",
            "Tempo médio das finalizadas (h)",
            "Tempo estimado médio (min)",
            "Nível médio",
            "Nível (moda)",
        ],
        "Planejamento": [
            sp["qtd"], sp["qtd_fin"], _fmt(sp["tempo_med"]),
            _fmt(sp["tempo_est_med"]), _fmt(sp["nivel_med"]), _fmt(sp["nivel_moda"]),
        ],
        "Internas (fora do plano)": [
            si["qtd"], si["qtd_fin"], _fmt(si["tempo_med"]),
            _fmt(si["tempo_est_med"]), _fmt(si["nivel_med"]), _fmt(si["nivel_moda"]),
        ],
    })
    st.dataframe(tabela, use_container_width=True, hide_index=True)

    # ── Veredito automático ──────────────────────────────────────────────────────
    linhas = []
    nivel_plan_maior = tempo_plan_maior = None

    if sp["nivel_med"] is not None and si["nivel_med"] is not None:
        if sp["nivel_med"] > si["nivel_med"]:
            nivel_plan_maior = True
            linhas.append(f"- **Nível médio**: planejamento é MAIOR ({sp['nivel_med']} vs {si['nivel_med']}).")
        elif sp["nivel_med"] < si["nivel_med"]:
            nivel_plan_maior = False
            linhas.append(f"- **Nível médio**: planejamento é MENOR ({sp['nivel_med']} vs {si['nivel_med']}).")
        else:
            linhas.append(f"- **Nível médio**: igual ({sp['nivel_med']}).")

    if sp["tempo_med"] is not None and si["tempo_med"] is not None:
        if sp["tempo_med"] > si["tempo_med"]:
            tempo_plan_maior = True
            linhas.append(f"- **Tempo médio**: planejamento é MAIOR ({sp['tempo_med']}h vs {si['tempo_med']}h).")
        elif sp["tempo_med"] < si["tempo_med"]:
            tempo_plan_maior = False
            linhas.append(f"- **Tempo médio**: planejamento é MENOR ({sp['tempo_med']}h vs {si['tempo_med']}h).")
        else:
            linhas.append(f"- **Tempo médio**: igual ({sp['tempo_med']}h).")

    if linhas:
        st.markdown("\n".join(linhas))

    # Conclusão
    if nivel_plan_maior is None and tempo_plan_maior is None:
        st.info("Dados insuficientes para concluir (faltam motos finalizadas ou nível registrado).")
    else:
        sinais = [x for x in (nivel_plan_maior, tempo_plan_maior) if x is not None]
        if all(sinais):
            st.success("**CONFIRMA a hipótese:** as motos do planejamento estão mais difíceis "
                       "(nível e/ou tempo maiores que as internas fora do plano).")
        elif not any(sinais):
            st.error("**NÃO confirma a hipótese:** as motos do planejamento estão mais fáceis/rápidas "
                     "que as internas fora do plano.")
        else:
            st.warning("**Resultado misto:** um indicador favorece a hipótese e o outro não — veja acima.")


# ── Percentuais em execução (internas x planejamento) ────────────────────────────
def render_percentuais(df_plan_bq: pd.DataFrame, status_rt: pd.DataFrame) -> None:
    st.subheader("Percentual em execução")

    def _pct(n: int, d: int) -> str:
        return f"{(n / d * 100):.1f}%" if d else "—"

    # Planejamento: status vem do cruzamento com o tempo real
    total_plan = len(df_plan_bq)
    if total_plan and not status_rt.empty:
        merged = df_plan_bq[["placa"]].merge(
            status_rt[["placa", "status_atual"]], on="placa", how="left"
        )
        st_plan = merged["status_atual"].fillna("não direcionada")
    elif total_plan:
        st_plan = pd.Series(["não direcionada"] * total_plan)
    else:
        st_plan = pd.Series(dtype="object")
    and_plan = int((st_plan == "em andamento").sum())
    fin_plan = int((st_plan == "finalizada").sum())

    # Internas: apenas as motos internas do tempo real
    if not status_rt.empty:
        internas = status_rt[status_rt["tipo_manutencao"] == "Interna"]
    else:
        internas = status_rt
    total_int = len(internas)
    and_int = int((internas["status_atual"] == "em andamento").sum()) if total_int else 0
    fin_int = int((internas["status_atual"] == "finalizada").sum()) if total_int else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Planejamento em andamento", _pct(and_plan, total_plan), f"{and_plan}/{total_plan}")
    c2.metric("Planejamento finalizado",   _pct(fin_plan, total_plan), f"{fin_plan}/{total_plan}")
    c3.metric("Internas em andamento",     _pct(and_int, total_int),   f"{and_int}/{total_int}")
    c4.metric("Internas finalizado",       _pct(fin_int, total_int),   f"{fin_int}/{total_int}")


# ── Tabela 2 — Planejamento: nível & tempo estimado ──────────────────────────────
def render_tabela2(df_plan_bq: pd.DataFrame) -> None:
    st.subheader("Planejamento — Nível & Tempo estimado")
    if df_plan_bq.empty:
        st.info("Sem planejamento para esta filial hoje.")
        return

    cols = {
        "placa":                    "Placa",
        "filial":                   "Filial",
        "ordem_prioridade":         "Prioridade",
        "nivel_manutencao":         "Nível",
        "tempo_estimado_execucao":  "Tempo Estimado (min)",
    }
    present = [c for c in cols if c in df_plan_bq.columns]
    st.dataframe(
        df_plan_bq[present].rename(columns=cols),
        use_container_width=True,
        hide_index=True,
    )


# ── Tabela 3 — Em manutenção agora: rampa & mecânico ─────────────────────────────
def render_tabela3(status_rt: pd.DataFrame) -> None:
    st.subheader("Em manutenção — Rampa & Mecânico")
    if status_rt.empty:
        st.info("Nenhuma moto com status em tempo real.")
        return

    d = status_rt.copy()
    d["Entrada"] = d["data_entrada"].apply(_fmt_hora)
    d["Saída"]   = d["data_saida"].apply(_fmt_hora)
    d = d.rename(columns={"placa": "Placa", "rampa": "Rampa", "mecanico": "Mecânico"})

    cols = [c for c in ["Placa", "Rampa", "Mecânico", "Entrada", "Saída"] if c in d.columns]
    st.dataframe(d[cols], use_container_width=True, hide_index=True)


# ── Gráfico — Motos internas x planejamento: tempo em manutenção ─────────────────
# Cor por origem
_COR_PLANEJAMENTO = "#1ABC9C"   # verde turquesa — planejamento
_COR_INTERNA      = "#E84B6B"   # vermelho — internas (fora do plano)


def _grafico_tempo_status(d: pd.DataFrame, titulo: str) -> None:
    """Desenha UM gráfico de barras (tempo em manutenção) para um subconjunto já
    filtrado por status. `d` precisa ter as colunas origem, duracao_h, Entrada."""
    st.markdown(f"**{titulo}**")

    if d.empty:
        st.info("Nenhuma moto neste status.")
        return

    # Motos sem hora de entrada não têm duração calculável — não some com elas em silêncio
    sem_tempo = d[d["duracao_h"].isna()].copy()
    d = d.dropna(subset=["duracao_h"])

    if d.empty:
        st.info("Nenhuma moto com hora de entrada registrada para calcular o tempo.")
    else:
        _cor = alt.Color(
            "origem:N",
            scale=alt.Scale(
                domain=["Planejamento", "Interna"],
                range=[_COR_PLANEJAMENTO, _COR_INTERNA],
            ),
            title="Origem",
        )
        _tooltip = [
            alt.Tooltip("placa:N", title="Placa"),
            alt.Tooltip("origem:N", title="Origem"),
            alt.Tooltip("duracao_h:Q", title="Duração (h)"),
            alt.Tooltip("mecanico:N", title="Mecânico"),
            alt.Tooltip("Entrada:N", title="Entrada"),
        ]

        barras = alt.Chart(d).mark_bar().encode(
            x=alt.X("duracao_h:Q", title="Tempo em manutenção (h)"),
            y=alt.Y("placa:N", sort="-x", title="Placa"),
            color=_cor,
            tooltip=_tooltip,
        )
        st.altair_chart(barras, use_container_width=True)

    if not sem_tempo.empty:
        placas_sem = ", ".join(sorted(sem_tempo["placa"].astype(str).unique()))
        st.caption(
            f"⚠️ {len(sem_tempo)} moto(s) sem hora de entrada registrada na API — "
            f"não exibidas no gráfico: {placas_sem}"
        )


def render_grafico_internas(status_rt: pd.DataFrame, placas_planejamento: set) -> None:
    st.subheader("Motos internas x planejamento — tempo em manutenção")
    st.caption(
        "Compara o tempo das motos do planejamento (verde turquesa) x internas fora do plano "
        "(vermelho). Quanto mais à direita, mais tempo parada. Um gráfico para o que está "
        "**em andamento** e outro para o que **finalizou hoje**."
    )
    if status_rt.empty:
        st.info("Sem dados em tempo real para o gráfico.")
        return

    # Em andamento + finalizadas. NÃO filtra por tipo_manutencao: esse campo vem da
    # API e costuma vir nulo, o que descartava motos que estão de fato em manutenção.
    # Como todas vêm dos mecânicos da filial, são trabalho interno do galpão.
    d = status_rt[status_rt["status_atual"].isin(["em andamento", "finalizada"])].copy()
    if d.empty:
        st.info("Nenhuma moto em andamento ou finalizada.")
        return

    d["origem"] = d["placa"].apply(
        lambda p: "Planejamento" if p in placas_planejamento else "Interna"
    )
    d["duracao_h"] = d.apply(
        lambda r: _duracao_horas(r.get("data_entrada"), r.get("data_saida")), axis=1
    )
    d["Entrada"] = d["data_entrada"].apply(_fmt_hora)

    _grafico_tempo_status(
        d[d["status_atual"] == "em andamento"].copy(),
        "Em andamento (entrada → agora)",
    )
    st.divider()
    _grafico_tempo_status(
        d[d["status_atual"] == "finalizada"].copy(),
        "Finalizadas hoje (entrada → saída)",
    )


# ── Tabela 4 — Em andamento e finalizadas ────────────────────────────────────────
def render_tabela4(
    status_rt: pd.DataFrame,
    df_manut: pd.DataFrame,
    placas_planejamento: set,
    bq_filial: str,
) -> None:
    st.subheader("Motos internas em andamento e finalizadas")
    if status_rt.empty:
        st.info("Sem dados em tempo real.")
        return

    d = status_rt[
        status_rt["status_atual"].isin(["em andamento", "finalizada"])
        & (status_rt["tipo_manutencao"] == "Interna")
    ].copy()
    if d.empty:
        st.info("Nenhuma moto interna em andamento ou finalizada.")
        return

    if not df_manut.empty:
        d = d.merge(
            df_manut[["placa", "nivel_manutencao", "tempo_estimado_execucao"]],
            on="placa", how="left",
        )
    else:
        d["nivel_manutencao"] = pd.NA
        d["tempo_estimado_execucao"] = pd.NA

    d["Status"]  = d["placa"].apply(
        lambda p: "Planejamento" if p in placas_planejamento else "Não planejamento"
    )
    d["Filial"]  = bq_filial
    d["Entrada"] = d["data_entrada"].apply(_fmt_hora)
    d["Saída"]   = d["data_saida"].apply(_fmt_hora)
    d = d.rename(columns={
        "placa":                    "Placa",
        "rampa":                    "Rampa",
        "nivel_manutencao":         "Nível",
        "tempo_estimado_execucao":  "Tempo Estimado (min)",
    })

    cols = [
        "Placa", "Filial", "Status", "Tempo Estimado (min)",
        "Nível", "Rampa", "Entrada", "Saída",
    ]
    cols = [c for c in cols if c in d.columns]
    st.dataframe(d[cols], use_container_width=True, hide_index=True)
