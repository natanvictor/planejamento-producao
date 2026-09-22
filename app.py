import re
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from data import plano_queries as q
from data import rampas_ativas as ra
from data import rampas_historico as rh
from data.realtime_manutencao import enriquecer
from components.aba_tabela import render_aba
from components.rampas_filial import render_rampas_colunas, altura_paineis
from components.anomalia_geral import render_aba5

st.set_page_config(page_title="Gestão do Plano de Produção e Anomalias", layout="wide")
st.title("Gestão do Plano de Produção e Anomalias")
st.caption("Motos: BigQuery · Estado de manutenção (situação, evento, horários): **API em tempo real**")


@st.cache_data(ttl=300, show_spinner=False)
def _hora_atualizacao(_bucket: str) -> str:
    """Horário em que o cache de dados (5 min) foi preenchido — reflete a frescura
    real dos dados. Recalcula quando o cache expira (a cada ~5 min)."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")


st.info(
    f"Última atualização dos dados: **{_hora_atualizacao('dados')}** · "
    "atualiza ao recarregar a página — **cache de 5 min** (não é automático nem de hora em hora).",
    icon="🕒",
)


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_bq(aba: str) -> pd.DataFrame:
    return {
        "aba1": q.get_aba1_planejamento,
        "aba2": q.get_aba2_consultor,
        "aba3": q.get_aba3_conquiste,
        "aba4": q.get_aba4_transferencia,
    }[aba]()


@st.cache_data(ttl=300, show_spinner=False)
def _enriquecer(vid_placa_items: tuple) -> dict:
    return enriquecer(dict(vid_placa_items))


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_paineis(filiais: tuple) -> dict:
    return rh.montar_paineis(filiais)


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_regionais() -> dict:
    """{filial_normalizada: gerente_regional}. Tabela mensal (divisao_filiais) ->
    TTL 1h. Filial sem regional (ex.: franquias/MX) -> 'Sem regional'."""
    df = q.get_divisao_filiais()
    return {_norm_filial(r.filial): (r.gerente_regional or "Sem regional")
            for r in df.itertuples() if pd.notna(r.filial)}


@st.cache_data(ttl=3600, show_spinner=False)
def _carregar_cms() -> dict:
    """{filial_normalizada: city_manager} da mesma tabela divisao_filiais."""
    df = q.get_divisao_filiais()
    return {_norm_filial(r.filial): (r.cm_nome or "—")
            for r in df.itertuples() if pd.notna(r.filial)}


def _norm_placa(s: object) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()


def _norm_filial(s: object) -> str:
    """Normaliza nome de filial p/ casar com divisao_filiais (lower + espacos
    colapsados), mesma logica de chave usada na tabela de origem."""
    return re.sub(r"\s+", " ", str(s).strip()).lower()


def _com_regional(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona a coluna 'Gerente Regional' mapeando pela Filial (nome normalizado)."""
    df = df.copy()
    if "Filial" in df.columns:
        mapa = _carregar_regionais()
        df["Gerente Regional"] = df["Filial"].map(
            lambda f: mapa.get(_norm_filial(f), "Sem regional"))
    return df


def _com_manutencao(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona colunas de manutencao em tempo real a partir do veiculoId.

    Passa veiculoId->placa: a placa e usada como fallback para buscar a ultima
    manutencao (inclui finalizada) das motos sem manutencao aberta.
    """
    df = df.copy()
    vp = {int(r.veiculoId): r.Placa
          for r in df[["veiculoId", "Placa"]].dropna(subset=["veiculoId"]).itertuples()}
    est = _enriquecer(tuple(sorted(vp.items())))

    def get(vid, campo):
        if pd.isna(vid):
            return "" if campo != "situacao_id" else None
        return est.get(int(vid), {}).get(campo, "" if campo != "situacao_id" else None)

    df["Situação da Manutenção"] = df["veiculoId"].map(lambda v: get(v, "situacao"))
    df["_sid"] = df["veiculoId"].map(lambda v: get(v, "situacao_id"))
    df["Evento"] = df["veiculoId"].map(lambda v: get(v, "evento"))
    df["Entrou na Manutenção"] = df["veiculoId"].map(lambda v: get(v, "entrada"))
    df["Finalizada"] = df["veiculoId"].map(lambda v: get(v, "finalizada"))
    # horarios da triagem (usados na aba 2 do Consultor)
    df["_entrada_triagem"] = df["veiculoId"].map(lambda v: get(v, "entrada_triagem"))
    df["_finalizada_triagem"] = df["veiculoId"].map(lambda v: get(v, "finalizada_triagem"))
    # orcamento enviado (usado na aba 5 para "Conquiste sem orcamento")
    df["_orcamento_enviado"] = df["veiculoId"].map(lambda v: bool(get(v, "orcamento_enviado")))
    return df


def _ordenar(df: pd.DataFrame, colunas: list) -> pd.DataFrame:
    return df[[c for c in colunas if c in df.columns]]


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1 · Planejamento de Produção",
    "2 · Planejamento do Consultor",
    "3 · Anomalias de Conquiste",
    "4 · Anomalias de Titular Fim do Plano",
    "5 · Anomalia Geral (Desvio de Capacidade)",
])

with tab1:
    with st.spinner("Carregando plano + estado real-time…"):
        df = _carregar_bq("aba1").rename(columns={
            "placa": "Placa", "filial": "Filial", "categoria": "Categoria", "ordem": "Ordem"})
        df = _com_manutencao(df)
        df = _com_regional(df)
        # Ordem (ordem_prioridade 1-7) ordena as categorias do plano.
        # Defensivo: st.cache_data pode servir um df antigo (sem "Ordem") logo após
        # deploy, pois o cache não vê mudança em plano_queries -> ordena só o que existe.
        _sort = [c for c in ["Ordem", "Categoria", "Placa"] if c in df.columns]
        if _sort:
            df = df.sort_values(_sort, kind="stable")
    render_aba(_ordenar(df, [
        "Ordem", "Placa", "Filial", "Gerente Regional", "Categoria", "Situação da Manutenção",
        "Entrou na Manutenção", "Finalizada", "_sid", "veiculoId"]), key="aba1")

    # --- Rampas ativas por filial (ao vivo): coluna por rampa + histórico do dia ---
    # Responde aos MESMOS filtros da tabela acima (Gerente Regional + Filial), lidos do
    # session_state das keys do render_aba. Filtrar reduz a busca (so essas filiais).
    st.divider()
    st.markdown("#### Rampas ativas por filial")
    st.caption("Ao vivo (API). Coluna = 1 rampa. Topo = rampa atual + mecânico; abaixo = "
               "placas do dia [hora · placa · cor · nível · ✓/✗]. 🟢 plano · 🔴 fora do plano · 🔵 cliente.")

    sel_regional = st.session_state.get("aba1_r", [])
    sel_filial = st.session_state.get("aba1_f", [])
    # Aplica os mesmos filtros da tabela p/ decidir QUAIS filiais mostrar as rampas.
    _base = df
    if sel_regional and "Gerente Regional" in _base.columns:
        _base = _base[_base["Gerente Regional"].isin(sel_regional)]
    if sel_filial:
        _base = _base[_base["Filial"].isin(sel_filial)]
    filiais_plano = sorted(_base["Filial"].dropna().astype(str).unique())
    placas_plano = {_norm_placa(p) for p in df["Placa"].dropna()}

    # O histórico faz muitas chamadas (eventos por manutenção). SEM nenhum filtro,
    # limita p/ nao varrer o Brasil inteiro. Com Regional ou Filial selecionada,
    # mostra TODAS as filiais do filtro (a regional traz todas as suas filiais).
    _CAP = 6
    if not sel_regional and not sel_filial and len(filiais_plano) > _CAP:
        st.caption(f"⚠️ Mostrando as {_CAP} primeiras de {len(filiais_plano)} filiais. "
                   "Filtre por **Gerente Regional** ou **Filial** acima para ver as demais.")
        filiais_plano = filiais_plano[:_CAP]
    elif sel_regional:
        st.caption(f"Mostrando **{len(filiais_plano)} filiais** da regional selecionada "
                   "(rampas ao vivo — pode levar alguns segundos).")

    with st.spinner("Carregando rampas + histórico do dia…"):
        paineis = _carregar_paineis(tuple(filiais_plano))

    def _categoria(tipo: object, placa: object) -> str:
        # Plano PRIMEIRO: se está no plano do dia -> planejamento, seja qual for o tipo.
        # (Conquiste/Suprir Agendamento têm tipoEnum na faixa "cliente" do maintenance-backend,
        #  mas são categorias do plano interno — não podem cair em "cliente".)
        if _norm_placa(placa) in placas_plano:
            return "planejamento"
        if tipo is not None and int(tipo) in ra.TIPOS_CLIENTE:
            return "cliente"
        return "nao_planejamento"

    if not paineis:
        st.caption("Nenhuma rampa ativa para o filtro atual.")
    else:
        components.html(
            render_rampas_colunas(paineis, _categoria),
            height=altura_paineis(paineis), scrolling=True)

with tab2:
    with st.spinner("Carregando plano do consultor + estado real-time…"):
        df = _carregar_bq("aba2").rename(columns={
            "placa": "Placa", "filial": "Filial", "modelo": "Modelo",
            "categoria": "Categoria", "sla": "SLA"})
        df = _com_manutencao(df)
        df = _com_regional(df)
        df["Status da Triagem"] = df["_sid"].map(
            lambda s: "Não realizado" if (pd.isna(s) or int(s) in (5, 6)) else "Triagem realizada")
        # aba 2 e so o planejamento (triagem) -> horarios sao os da TRIAGEM
        df["Iniciou Triagem"] = df["_entrada_triagem"]
        df["Finalizou Triagem"] = df["_finalizada_triagem"]
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Gerente Regional", "Modelo", "Categoria", "SLA", "Status da Triagem",
        "Situação da Manutenção", "Iniciou Triagem", "Finalizou Triagem",
        "_sid", "veiculoId"]), key="aba2")

with tab3:
    with st.spinner("Carregando anomalias Conquiste + estado real-time…"):
        df = _carregar_bq("aba3").rename(columns={
            "placa": "Placa", "filial": "Filial", "diasSituacao": "Dias na Situação",
            "categoria": "Categoria", "justificativa": "Justificativa", "justificada": "Justificada?"})
        df = _com_manutencao(df)
        df = _com_regional(df)
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Gerente Regional", "Dias na Situação", "Evento", "Situação da Manutenção",
        "Entrou na Manutenção", "Finalizada", "Justificativa", "Justificada?",
        "_sid", "veiculoId"]), key="aba3")

with tab4:
    with st.spinner("Carregando transferência fim do plano + estado real-time…"):
        df = _carregar_bq("aba4").rename(columns={
            "placa": "Placa", "filial": "Filial", "status_prazo": "Status do Prazo",
            "justificativa": "Justificativa", "Evento": "Evento Manutenção"})
        _venc = pd.to_datetime(df["prazo_fim_transferencia"], errors="coerce")
        df["Data de Vencimento"] = _venc.dt.strftime("%d/%m/%Y").fillna("—")
        # DATE_DIFF(prazo_fim_transferencia, hoje) -> dias ate o vencimento
        _hoje = pd.Timestamp.now(tz="America/Sao_Paulo").normalize().tz_localize(None)
        _dias = (_venc.dt.normalize() - _hoje).dt.days
        df["Dias até o Vencimento"] = _dias.apply(lambda x: "—" if pd.isna(x) else str(int(x)))
        df = _com_manutencao(df).rename(columns={"Evento": "Evento Manutenção"})
        df = _com_regional(df)
    render_aba(_ordenar(df, [
        "Placa", "Filial", "Gerente Regional", "Evento Manutenção", "Situação da Manutenção",
        "Data de Vencimento", "Dias até o Vencimento", "Status do Prazo",
        "Justificativa", "Entrou na Manutenção", "Finalizada",
        "_sid", "veiculoId"]), key="aba4")


def _classificar_rampa(tipo: object, placa: object, placas_plano: set) -> str:
    """Mesma regra da aba 1: no plano -> planejamento; senão tipo cliente -> cliente;
    o resto -> nao_planejamento (moto fora do plano = desvio de capacidade)."""
    if _norm_placa(placa) in placas_plano:
        return "planejamento"
    if tipo is not None and int(tipo) in ra.TIPOS_CLIENTE:
        return "cliente"
    return "nao_planejamento"


def _backlog_titular(df4: pd.DataFrame) -> dict:
    """{filial: [ {placa, prazo, urg, st, _ord} ]} do titular fim do plano (não finalizado)."""
    if df4.empty:
        return {}
    _venc = pd.to_datetime(df4["prazo_fim_transferencia"], errors="coerce")
    _hoje = pd.Timestamp.now(tz="America/Sao_Paulo").normalize().tz_localize(None)
    df4 = df4.copy()
    df4["_dias"] = (_venc.dt.normalize() - _hoje).dt.days
    out: dict = {}
    for row in df4.to_dict("records"):
        if row.get("_sid") == 4:  # já finalizada -> não é backlog
            continue
        d = row.get("_dias")
        if pd.isna(d):
            prazo, urg, ordv = "sem prazo", "mut", 9999
        else:
            d = int(d)
            ordv = d
            if d < 0:
                prazo, urg = f"vencido {d}d", "red"
            elif d == 0:
                prazo, urg = "vence hoje", "red"
            elif d == 1:
                prazo, urg = "vence amanhã", "red"
            elif d <= 7:
                prazo, urg = f"vence em {d}d", "amber"
            else:
                prazo, urg = f"vence em {d}d", "mut"
        out.setdefault(row["Filial"], []).append({
            "placa": row["Placa"], "prazo": prazo, "urg": urg,
            "st": row.get("Situação da Manutenção") or "—", "_ord": ordv})
    for lst in out.values():
        lst.sort(key=lambda m: m["_ord"])
    return out


def _backlog_conquiste(df3: pd.DataFrame) -> dict:
    """{filial: [ {placa, prazo, urg, st, _ord} ]} de Conquiste >13d SEM orçamento (não finalizado)."""
    if df3.empty:
        return {}
    out: dict = {}
    for row in df3.to_dict("records"):
        if row.get("_orcamento_enviado", False):   # já tem orçamento -> fora do recorte
            continue
        if row.get("_sid") == 4:                    # já finalizada -> não é backlog
            continue
        d = row.get("_dias")
        dias = int(d) if pd.notna(d) else 0
        out.setdefault(row["Filial"], []).append({
            "placa": row["Placa"], "prazo": f"{dias} dias",
            "urg": "red" if dias >= 30 else "amber",
            "st": row.get("Situação da Manutenção") or "—", "_ord": dias})
    for lst in out.values():
        lst.sort(key=lambda m: -m["_ord"])
    return out


with tab5:
    st.markdown("#### Anomalia Geral — Desvio de Capacidade")
    st.caption("Filiais com **titular fim do plano** E **Conquiste >13d sem orçamento enviado** "
               "que estão com **moto não planejada na rampa agora**. Bata o olho e ligue para o CM.")

    with st.spinner("Cruzando backlog crítico (titular + Conquiste s/ orçamento)…"):
        placas_plano = {_norm_placa(p) for p in _carregar_bq("aba1")["placa"].dropna()}

        df3 = _carregar_bq("aba3").rename(columns={"placa": "Placa", "filial": "Filial"})
        df3 = _com_manutencao(df3).rename(columns={"diasSituacao": "_dias"})
        conq = _backlog_conquiste(df3)

        df4 = _carregar_bq("aba4").rename(columns={"placa": "Placa", "filial": "Filial"})
        df4 = _com_manutencao(df4)
        titu = _backlog_titular(df4)

        reg_map, cm_map = _carregar_regionais(), _carregar_cms()
        filiais_both = sorted(set(conq) & set(titu))

    if not filiais_both:
        st.success("Nenhuma filial acumula titular fim do plano E Conquiste >13d sem orçamento agora. 🎉")
        st.stop()

    # filtros (opções = só as filiais do recorte); reduzem o custo das rampas ao vivo
    regionais_opt = sorted({reg_map.get(_norm_filial(f), "Sem regional") for f in filiais_both})
    fc1, fc2, fc3 = st.columns([2, 2, 1.2])
    sel_reg = fc1.multiselect("Gerente Regional", regionais_opt, key="aba5_r")
    _pool = [f for f in filiais_both
             if not sel_reg or reg_map.get(_norm_filial(f), "Sem regional") in sel_reg]
    sel_fil = fc2.multiselect("Filial", _pool, key="aba5_f")
    mostrar_ok = fc3.toggle("Mostrar sem desvio", value=False, key="aba5_ok",
                            help="Filiais com backlog mas rampa no plano")
    alvos = [f for f in _pool if not sel_fil or f in sel_fil]

    with st.spinner(f"Lendo rampas ao vivo de {len(alvos)} filial(is)…"):
        paineis = _carregar_paineis(tuple(alvos))

    acionar, ok = [], []
    for f in alvos:
        cols = paineis.get(f, [])
        fora = []
        for c in cols:
            if _classificar_rampa(c.get("tipo"), c.get("placa"), placas_plano) != "nao_planejamento":
                continue
            hora = next((h.get("hora") for h in c.get("historico", []) if h.get("atual")), "")
            fora.append({"placa": c.get("placa") or "—", "rampa": c.get("rampa") or "—",
                         "mec": c.get("mecanico") or "—", "nivel": c.get("nivel") or "—",
                         "hora": hora or ""})
        t_all, q_all = titu.get(f, []), conq.get(f, [])
        backlog_n = len(t_all) + len(q_all)
        base = {"filial": f, "regional": reg_map.get(_norm_filial(f), "Sem regional"),
                "cm": cm_map.get(_norm_filial(f), "—")}
        if fora:
            t_show, q_show = t_all[:4], q_all[:4]
            acionar.append({**base, "fora": sorted(fora, key=lambda m: m["hora"]),
                            "titular": t_show, "conquiste": q_show,
                            "extra": (len(t_all) - len(t_show)) + (len(q_all) - len(q_show)),
                            "_n": len(fora), "_bl": backlog_n})
        else:
            ok.append({**base, "rampas": len(cols), "backlog": backlog_n})

    acionar.sort(key=lambda x: (-x["_n"], -x["_bl"]))
    dados = {
        "kpis": {"acionar": len(acionar),
                 "nao_plan": sum(x["_n"] for x in acionar),
                 "backlog": sum(len(titu.get(f, [])) + len(conq.get(f, [])) for f in alvos),
                 "so_backlog": len(ok)},
        "acionar": acionar, "ok": ok}
    render_aba5(dados, mostrar_ok)
