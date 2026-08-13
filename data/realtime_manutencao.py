"""Enriquecimento de estado de manutencao EM TEMPO REAL via API Mottu.

O BigQuery define QUAIS motos (plano/consultor/conquiste/transferencia) e os
atributos nao-manutencao. Todo o estado de manutencao (situacao, evento,
horario que entrou, horario finalizada) vem da API em tempo real:

  1) POST /api/v3/Maintenance/info-by-vehicle-ids  -> maintenanceId por veiculo (lote)
  2) GET  /api/v2/Manutencao/Detalhes/Eventos/{id} -> timeline (situacao/evento/horarios)
"""
import requests
import streamlit as st
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter

_BASE_V3 = "https://maintenance-backend.mottu.cloud/api/v3/"
_BASE_V2 = "https://maintenance-backend.mottu.cloud/api/v2/"
_SSO_URL = "https://sso.mottu.cloud/realms/Internal/protocol/openid-connect/token"
_TZ_BR = timezone(timedelta(hours=-3))

_CHUNK = 300
_MAX_WORKERS = 24


def _session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=_MAX_WORKERS, pool_maxsize=_MAX_WORKERS)
    s.mount("https://", adapter)
    return s


def _get_token() -> str:
    resp = requests.post(
        _SSO_URL,
        data={
            "username": st.secrets["username"],
            "password": st.secrets["password"],
            "grant_type": "password",
            "client_id": "admin-v3-frontend-client",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _info_by_vehicle_ids(sess: requests.Session, token: str, vehicle_ids: list[int]) -> dict[int, int]:
    """Retorna {vehicleId: maintenanceId} para os veiculos que tem manutencao."""
    out: dict[int, int] = {}
    for i in range(0, len(vehicle_ids), _CHUNK):
        chunk = vehicle_ids[i:i + _CHUNK]
        resp = sess.post(
            f"{_BASE_V3}Maintenance/info-by-vehicle-ids",
            headers=_headers(token), json={"vehicleIds": chunk}, timeout=60,
        )
        if resp.status_code != 200:
            continue
        for item in resp.json().get("result", []) or []:
            vid = item.get("vehicleId")
            mid = item.get("maintenanceId")
            if vid is not None and mid:
                out[int(vid)] = int(mid)
    return out


def _fmt(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts[:19]).strftime("%d/%m %H:%M")
    except ValueError:
        return ""


def _derivar(eventos: list[dict], hoje: str) -> dict:
    """Deriva estado atual + horarios do dia a partir da timeline de eventos."""
    ev = sorted(eventos, key=lambda e: e.get("criacaoDataUTC") or e.get("criacaoData") or "")
    if not ev:
        return {}
    ultimo = ev[-1]
    entrada = None            # primeira vez que iniciou manutencao (situacaoId==2) NO DIA
    finalizada = None         # ultima finalizacao (situacaoId==4) NO DIA
    entrada_triagem = None    # inicio da triagem NO DIA (evento "Iniciada Triagem" ou situacaoId==6)
    finalizada_triagem = None # fim da triagem NO DIA (evento "Finalizada Triagem")
    rampa = None
    for e in ev:
        if e.get("deviceName"):
            rampa = e["deviceName"]
        ts = e.get("criacaoData")
        if not ts:
            continue
        no_dia = ts[:10] == hoje
        sid = e.get("situacaoId")
        desc = e.get("eventoTipoDescricao") or ""
        if no_dia and sid == 2 and entrada is None:
            entrada = ts
        if no_dia and sid == 4:
            finalizada = ts
        # triagem (aba do Consultor): so o planejamento -> horarios da triagem
        if no_dia and ("Iniciada Triagem" in desc or sid == 6) and entrada_triagem is None:
            entrada_triagem = ts
        if no_dia and "Finalizada Triagem" in desc:
            finalizada_triagem = ts
    return {
        "situacao": ultimo.get("situacaoDescricao") or "",
        "situacao_id": ultimo.get("situacaoId"),
        "evento": ultimo.get("eventoTipoDescricao") or "",
        "entrada": _fmt(entrada),
        "finalizada": _fmt(finalizada),
        "entrada_triagem": _fmt(entrada_triagem),
        "finalizada_triagem": _fmt(finalizada_triagem),
        "rampa": rampa or "",
    }


def _eventos(sess: requests.Session, token: str, mid: int, hoje: str) -> dict:
    try:
        resp = sess.get(
            f"{_BASE_V2}Manutencao/Detalhes/Eventos/{mid}",
            headers=_headers(token), timeout=25,
        )
        if resp.status_code != 200:
            return {}
        return _derivar(resp.json().get("dataResult", []) or [], hoje)
    except requests.RequestException:
        return {}


def _ultimo_mid_por_placa(placas: tuple) -> dict:
    """Ultima manutencao (inclui FINALIZADA) por placa, via BQ. So o ID -> o estado
    ainda vem da API ao vivo. import lazy para nao acoplar este modulo ao BQ."""
    if not placas:
        return {}
    from data import plano_queries
    return plano_queries.get_ultimo_mid_por_placa(placas)


def enriquecer(vid_placa: dict) -> dict[int, dict]:
    """Retorna {vehicleId: {situacao, evento, entrada, finalizada, dias_situacao, rampa}}.

    info-by-vehicle-ids so devolve a manutencao ABERTA. Motos finalizadas voltam
    com maintenanceId=null e ficariam vazias -> para essas, busca o id da ultima
    manutencao no BQ (por placa) e enriquece pelo MESMO endpoint de eventos ao vivo.
    """
    vid_placa = {int(v): p for v, p in vid_placa.items() if v is not None}
    if not vid_placa:
        return {}
    vehicle_ids = sorted(vid_placa)

    sess = _session()
    token = _get_token()
    hoje = datetime.now(_TZ_BR).date().isoformat()

    vid_to_mid = _info_by_vehicle_ids(sess, token, vehicle_ids)

    # fallback: veiculos sem manutencao aberta -> ultima manutencao (inclui finalizada)
    sem_aberta = [v for v in vehicle_ids if v not in vid_to_mid]
    if sem_aberta:
        placas = tuple(sorted({vid_placa[v] for v in sem_aberta if vid_placa.get(v)}))
        placa_mid = _ultimo_mid_por_placa(placas)
        for v in sem_aberta:
            mid = placa_mid.get(vid_placa.get(v))
            if mid:
                vid_to_mid[v] = int(mid)

    if not vid_to_mid:
        return {}

    resultado: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_eventos, sess, token, mid, hoje): vid
                   for vid, mid in vid_to_mid.items()}
        for fut in futures:
            vid = futures[fut]
            try:
                estado = fut.result()
            except Exception:
                estado = {}
            if estado:
                resultado[vid] = estado
    return resultado
