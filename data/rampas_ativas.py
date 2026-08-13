"""Rampas ativas por filial em TEMPO REAL via API Mottu.

Endpoint `GET /api/v2.6/Ativas/{lugar}/Ativas?...&Situacoes=2` -> manutencoes em
curso (situacao 2 = Em Manutencao), 1 moto por `plataforma` (a rampa). O `tipo`
da manutencao separa Interna x Cliente. O `lugar_id` vem de `filiais.json`
(campo `api_codigo`), casado pelo nome que aparece no BigQuery (`bq_filial`).

Reaproveita o token SSO / sessao HTTP de `data.realtime_manutencao`.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from data.realtime_manutencao import _get_token, _headers, _session, _MAX_WORKERS

_BASE_V26 = "https://maintenance-backend.mottu.cloud/api/v2.6/"
_TIPOS_QS = "&".join(f"Tipos={t}" for t in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15))
_FILIAIS_JSON = Path(__file__).resolve().parent.parent / "filiais.json"

# Classificacao Interna x Cliente por `tipo` de manutencao (fonte: painel de producao).
TIPOS_INTERNA = frozenset({3, 4, 6, 9, 15})
TIPOS_CLIENTE = frozenset({1, 2, 5, 7, 10, 11, 12, 13})

_COLS = ["filial", "rampa", "moto_id", "tipo", "mecanico"]


def _mapa_lugar() -> dict[str, str]:
    """{nome_bq_filial: api_codigo} a partir de filiais.json (arquivo com BOM)."""
    dados = json.loads(_FILIAIS_JSON.read_text(encoding="utf-8-sig"))
    mapa: dict[str, str] = {}
    for info in dados.values():
        bq = info.get("bq_filial") or info.get("nome")
        cod = info.get("api_codigo")
        if bq and cod is not None:
            mapa[str(bq)] = str(cod)
    return mapa


def _rampas_de_lugar(sess: requests.Session, token: str, filial: str, lugar_id: str) -> list[dict]:
    """Rampas ativas (Situacoes=2) de um lugar. Descarta plataformas de alinhamento/iot."""
    url = (f"{_BASE_V26}Ativas/{lugar_id}/Ativas?{_TIPOS_QS}"
           "&Situacoes=2&Pagina=1&QuantidadePorPagina=60")
    try:
        r = sess.get(url, headers=_headers(token), timeout=25)
        if r.status_code != 200:
            return []
        manutencoes = r.json().get("dataResult", {}).get("manutencoes", []) or []
    except (requests.RequestException, ValueError):
        return []

    linhas: list[dict] = []
    for m in manutencoes:
        plataforma = m.get("plataforma") or ""
        pl = plataforma.lower()
        if "alinh" in pl or "iot" in pl:  # alinhamento / IoT nao sao rampas de producao
            continue
        linhas.append({
            "filial": filial,
            "rampa": plataforma or "—",
            "moto_id": m.get("placa") or "—",
            "tipo": m.get("tipo"),
            "mecanico": m.get("ultimoMecanicoNome") or "—",
        })
    return linhas


def buscar_rampas_ativas(filiais_bq: tuple[str, ...]) -> pd.DataFrame:
    """Rampas ativas das filiais informadas (nomes como no BigQuery).

    Parametros
    ----------
    filiais_bq:
        Tupla de nomes de filial (coluna `filial` do plano) — hashavel para caching.

    Retorna
    -------
    pd.DataFrame
        Colunas ``filial, rampa, moto_id, tipo, mecanico`` (uma linha por rampa ativa).
        A classificacao em categoria (planejamento/nao_planejamento/cliente) e feita
        a jusante, cruzando `moto_id` com as placas do plano do dia.
    """
    mapa = _mapa_lugar()
    alvos = [(f, mapa[f]) for f in dict.fromkeys(filiais_bq) if f in mapa]
    if not alvos:
        return pd.DataFrame(columns=_COLS)

    sess = _session()
    token = _get_token()
    linhas: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futs = [pool.submit(_rampas_de_lugar, sess, token, f, lid) for f, lid in alvos]
        for fut in futs:
            try:
                linhas.extend(fut.result())
            except Exception:
                continue
    return pd.DataFrame(linhas, columns=_COLS)
