"""Painel de rampas com histórico do dia (por rampa/mecânico) em TEMPO REAL.

Para cada filial, monta uma coluna por rampa ativa (Situacoes=2). Cada coluna:
  - topo: rampa atual + moto + nível (descricaoFila) + mecânico logado (ultimoMecanicoNome);
  - histórico do dia do MECÂNICO daquela rampa: placas que ele trabalhou hoje, em
    ordem cronológica, com hora de início, cor (categoria via tipo), nível e finalizada.

Fontes (API maintenance-backend, reaproveita token/sessão de realtime_manutencao):
  - GET /api/v2.6/Ativas/{lugar}/Ativas?...&Situacoes=2   -> rampas ativas + mecânico
  - GET /api/v2.6/Manutencao/HistoricoPorMecanico?...      -> manutenções recentes do mec
  - GET /api/v2/Manutencao/Detalhes/Eventos/{id}           -> timeline (início/finalizada do dia)

Hora de início = 1º evento situacaoId==2 no dia; finalizada = existe evento situacaoId==4 no dia.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import requests

from data.realtime_manutencao import _get_token, _headers, _session
from data.rampas_ativas import _mapa_lugar, TIPOS_CLIENTE, TIPOS_INTERNA  # noqa: F401

_BASE_V26 = "https://maintenance-backend.mottu.cloud/api/v2.6/"
_BASE_V2 = "https://maintenance-backend.mottu.cloud/api/v2/"
_TZ_BR = timezone(timedelta(hours=-3))
_TIPOS_QS = "&".join(f"Tipos={t}" for t in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15))
_EV_WORKERS = 16

# fallback de nível quando filaDescricao vem null (mapeado dos ids observados na API)
_NIVEL_POR_FILA_ID = {
    18: "Nível 1", 29: "Nível 2+", 20: "Nível 3", 28: "Nível 3+", 21: "Nível 4",
    31: "Box Rápido", 1: "Revisão / Mecânica Básica", 2: "Alinhamento", 3: "IoT",
}


def _nivel(fila_desc: str | None, fila_id: int | None) -> str:
    if fila_desc:
        return fila_desc
    if fila_id is not None and int(fila_id) in _NIVEL_POR_FILA_ID:
        return _NIVEL_POR_FILA_ID[int(fila_id)]
    return "—"


def _rampas_ativas(sess: requests.Session, token: str, lugar_id: str) -> list[dict]:
    url = (f"{_BASE_V26}Ativas/{lugar_id}/Ativas?{_TIPOS_QS}"
           "&Situacoes=2&Pagina=1&QuantidadePorPagina=60")
    try:
        r = sess.get(url, headers=_headers(token), timeout=25)
        if r.status_code != 200:
            return []
        return r.json().get("dataResult", {}).get("manutencoes", []) or []
    except (requests.RequestException, ValueError):
        return []


def _historico_mecanico(sess: requests.Session, token: str, mec_id: int) -> list[dict]:
    """Manutenções recentes do mecânico, deduplicadas por manutencaoId."""
    url = (f"{_BASE_V26}Manutencao/HistoricoPorMecanico"
           f"?mecanicoId={mec_id}&pagina=1&quantidadePorPagina=30")
    try:
        r = sess.get(url, headers=_headers(token), timeout=25)
        if r.status_code != 200:
            return []
        mans = r.json().get("dataResult", {}).get("manutencoes", []) or []
    except (requests.RequestException, ValueError):
        return []
    vistos: dict[int, dict] = {}
    for m in mans:
        mid = m.get("id")
        if mid is not None and mid not in vistos:
            vistos[int(mid)] = m
    return list(vistos.values())


def _eventos_dia(sess: requests.Session, token: str, mid: int, hoje: str) -> dict:
    """A partir da timeline, extrai do DIA: {inicio, fim, ultimo_evento}.
    - inicio = 1º evento situacaoId==2 no dia (HH:MM) — marca que trabalhou hoje.
    - fim = último evento situacaoId==4 no dia (HH:MM) ou None.
    - ultimo_evento = descrição do último evento do dia (explica por que não finalizou)."""
    vazio = {"inicio": None, "fim": None, "ultimo_evento": ""}
    try:
        r = sess.get(f"{_BASE_V2}Manutencao/Detalhes/Eventos/{mid}", headers=_headers(token), timeout=25)
        if r.status_code != 200:
            return vazio
        ev = r.json().get("dataResult", []) or []
    except (requests.RequestException, ValueError):
        return vazio
    ev = sorted(ev, key=lambda e: e.get("criacaoData") or "")
    inicio = fim = None
    ultimo_evento = ""
    for e in ev:
        ts = e.get("criacaoData")
        if not ts or ts[:10] != hoje:
            continue
        sid = e.get("situacaoId")
        if sid == 2 and inicio is None:
            inicio = ts
        if sid == 4:
            fim = ts
        ultimo_evento = e.get("eventoTipoDescricao") or ultimo_evento
    return {"inicio": inicio[11:16] if inicio else None,
            "fim": fim[11:16] if fim else None,
            "ultimo_evento": ultimo_evento}


def _map_paralelo(func, chaves, *args, workers: int = _EV_WORKERS) -> dict:
    """Executa func(sess, token, chave, *args) em paralelo -> {chave: resultado}."""
    out: dict = {}
    chaves = list(chaves)
    if not chaves:
        return out
    with ThreadPoolExecutor(max_workers=min(workers, len(chaves))) as pool:
        fut = {pool.submit(func, *args, k): k for k in chaves}
        for f in fut:
            try:
                out[fut[f]] = f.result()
            except Exception:
                out[fut[f]] = None
    return out


def montar_paineis(filiais_bq: tuple[str, ...]) -> dict[str, list[dict]]:
    """{filial: [coluna_por_rampa]} para as filiais informadas (nomes BQ).

    Cada coluna: {filial, rampa, placa, tipo, mecanico, nivel, historico:[{hora, placa,
    tipo, nivel, finalizada}]}. A categoria (cor) é derivada a jusante (precisa das
    placas do plano). Estrutura JSON-serializável (cacheável).

    Concorrência GLOBAL em 3 fases (não por filial em série): Ativas → históricos dos
    mecânicos → eventos (início) das manutenções tocadas hoje. `finalizada` sai do
    histórico (situacao==4), sem custo de evento.
    """
    mapa = _mapa_lugar()
    alvos = [(f, mapa[f]) for f in dict.fromkeys(filiais_bq) if f in mapa]
    if not alvos:
        return {}
    sess = _session()
    token = _get_token()
    hoje = datetime.now(_TZ_BR).date().isoformat()

    # Fase 1 — rampas ativas por filial (paralelo); descarta alinhamento/iot
    rampas_por_filial: dict[str, list[dict]] = {}
    res = _map_paralelo(lambda s, t, lid: _rampas_ativas(s, t, lid),
                        [lid for _, lid in alvos], sess, token)
    for filial, lugar_id in alvos:
        rs = [m for m in (res.get(lugar_id) or [])
              if not any(x in (m.get("plataforma") or "").lower() for x in ("alinh", "iot"))]
        if rs:
            rampas_por_filial[filial] = rs
    if not rampas_por_filial:
        return {}

    # Fase 2 — histórico dos mecânicos (global, paralelo), filtrado ao que tocaram hoje
    mec_ids = {int(m["ultimoMecanicoId"]) for rs in rampas_por_filial.values()
               for m in rs if m.get("ultimoMecanicoId")}
    hist_raw = _map_paralelo(lambda s, t, mid: _historico_mecanico(s, t, mid), mec_ids, sess, token)
    hist_por_mec = {mid: [x for x in (lst or []) if (x.get("atualizacaoData") or "")[:10] == hoje]
                    for mid, lst in hist_raw.items()}

    # Fase 3 — eventos do dia (início/fim/último evento) das manutenções tocadas hoje
    ids = {int(x["id"]) for lst in hist_por_mec.values() for x in lst if x.get("id")}
    eventos_por_id = _map_paralelo(lambda s, t, i: _eventos_dia(s, t, i, hoje), ids, sess, token,
                                   workers=32)

    # Fase 4 — montar colunas
    paineis: dict[str, list[dict]] = {}
    for filial, rs in rampas_por_filial.items():
        colunas: list[dict] = []
        for m in rs:
            mec_id = int(m["ultimoMecanicoId"]) if m.get("ultimoMecanicoId") else None
            mid_atual = m.get("manutencaoId")  # manutenção que está NA rampa agora
            hist: list[dict] = []
            for x in hist_por_mec.get(mec_id, []):
                mid = int(x["id"])
                ev = eventos_por_id.get(mid) or {}
                if not ev.get("inicio"):  # só o que ele iniciou hoje
                    continue
                hist.append({
                    "mid": mid,
                    "hora": ev["inicio"],
                    "fim": ev.get("fim"),
                    "placa": x.get("placa") or "—",
                    "tipo": x.get("tipo"),
                    "nivel": _nivel(x.get("filaDescricao"), x.get("filaId")),
                    "situacao": x.get("situacaoDescricao") or "",
                    "motivo": ev.get("ultimo_evento") or "",
                    "finalizada": x.get("situacao") == 4,  # direto do histórico
                    "atual": mid_atual is not None and mid == int(mid_atual),
                })
            hist.sort(key=lambda h: h["hora"])
            colunas.append({
                "filial": filial,
                "rampa": m.get("plataforma") or "—",
                "placa": m.get("placa") or "—",
                "tipo": m.get("tipo"),
                "mecanico": m.get("ultimoMecanicoNome") or "—",
                "nivel": _nivel(m.get("descricaoFila"), m.get("filaId")),
                "mid_atual": int(mid_atual) if mid_atual is not None else None,
                "historico": hist,
            })
        if colunas:
            paineis[filial] = colunas
    return paineis
