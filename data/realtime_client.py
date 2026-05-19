import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta


_BASE_MAINT_V26 = "https://maintenance-backend.mottu.cloud/api/v2.6/"
_BASE_MAINT_V2  = "https://maintenance-backend.mottu.cloud/api/v2/"
_BASE_EMPLOYEE  = "https://employee-management.mottu.cloud/"
_BASE_BRANCH    = "https://branch-management.mottu.cloud/"
_SSO_URL        = "https://sso.mottu.cloud/realms/Internal/protocol/openid-connect/token"

_TZ_BR = timezone(timedelta(hours=-3))

# Cargos de mecânicos válidos (espelho exato de horus-main/api_employees.py)
_MECHANIC_POSITIONS = {
    'Mecânico rampa geral (Mecânico Junior +)',
    'Mecânico Box Rápido (Mecânico Junior +)',
    'Auxiliar de Mecânico',
    'Mecânico I', 'Mecânico Box Rápido (Mecânico I)', 'Mecânico rampa geral (Mecânico I)',
    'Mecânico rampa geral (Mecânico Junior)', 'Mecânico Box Rápido (Mecânico Junior)',
    'Mecânico rampa geral (Mecânico I Plus)', 'Mecânico Box Rápido (Mecânico I Plus)',
    'Mecânico rampa geral (Mecânico Junior+)', 'Mecânico Box Rápido (Mecânico Junior+)',
    'Mecânico II', 'Mecânico Box Rápido (Mecânico II)', 'Mecânico rampa geral (Mecânico II)',
    'Mecânico rampa geral (Mecânico II Plus)', 'Mecânico Box Rápido (Mecânico II Plus)',
    'Mecânico III', 'Mecânico Motor (Mecânico III)',
    'Mecânico rampa geral (Mecânico III)', 'Mecânico rampa geral (Mecânico III Plus)',
    'Mecânico Motor (Mecânico IV)', 'Mecânico rampa geral (Mecânico IV)',
}


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
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get_branch_guid(token: str, branch_code: str) -> str:
    url = (
        f"{_BASE_BRANCH}branches?codes={branch_code}"
        "&getSetup=false&active=true&getRegion=false&getAddress=false&getDocuments=false"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    return resp.json()["result"][0]["id"]


def _get_mechanic_position_ids(token: str) -> list[str]:
    resp = requests.get(f"{_BASE_EMPLOYEE}positions?Name=mec", headers=_headers(token), timeout=15)
    resp.raise_for_status()
    items = resp.json()["result"]["items"]
    return [item["id"] for item in items if item["name"] in _MECHANIC_POSITIONS]


def _get_mecanicos(token: str, branch_code: str) -> list[dict]:
    branch_guid = _get_branch_guid(token, branch_code)
    position_ids = _get_mechanic_position_ids(token)

    url = f"{_BASE_EMPLOYEE}employees/GetSimplified?BranchId={branch_guid}"
    for pid in position_ids:
        url += f"&PositionId={pid}"

    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()

    return [
        {"fullName": e["fullName"], "code": e["code"]}
        for e in resp.json()["result"]
        if not e.get("isFired", False)
    ]


def _get_manutencoes_hoje(token: str, mec_code: str) -> list[dict]:
    hoje = datetime.now(_TZ_BR).date().isoformat()
    url = (
        f"{_BASE_MAINT_V26}Manutencao/HistoricoPorMecanico"
        f"?mecanicoId={mec_code}&pagina=1&quantidadePorPagina=25"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        return []

    result = []
    for m in resp.json().get("dataResult", {}).get("manutencoes", []):
        if datetime.fromisoformat(m["atualizacaoData"]).date().isoformat() == hoje:
            result.append({"id": m["id"], "placa": m["placa"], "situacao": m["situacao"]})
    return result


def _get_eventos(token: str, maint_id: str) -> dict:
    url = f"{_BASE_MAINT_V2}Manutencao/Detalhes/Eventos/{maint_id}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        return {}

    log = sorted(
        resp.json().get("dataResult", []),
        key=lambda e: e.get("criacaoDataUTC", ""),
    )

    rampa = None
    data_entrada = None
    data_saida = None

    for ev in log:
        if ev.get("deviceName"):
            rampa = ev["deviceName"]
        sid = ev.get("situacaoId")
        ts_str = ev.get("criacaoData", "")
        if not ts_str:
            continue
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(_TZ_BR)
        if sid == 2 and data_entrada is None:
            data_entrada = ts
        if sid == 4:
            data_saida = ts

    return {
        "rampa": rampa or "",
        "data_entrada": data_entrada,
        "data_saida": data_saida,
    }


def get_status_em_tempo_real(branch_code: str) -> pd.DataFrame:
    """
    Retorna DataFrame com colunas:
      placa | mecanico | rampa | data_entrada | data_saida | status_atual
    """
    token = _get_token()
    mecanicos = _get_mecanicos(token, branch_code)

    # Usa dict para garantir uma linha por placa (mantém a mais recente)
    records: dict[str, dict] = {}

    for mec in mecanicos:
        for m in _get_manutencoes_hoje(token, mec["code"]):
            placa = m.get("placa", "")
            if not placa:
                continue

            situacao = m.get("situacao", 0)
            if situacao == 4:
                status = "finalizada"
            elif situacao == 2:
                status = "em andamento"
            else:
                continue

            # Não sobrescreve uma finalizada já encontrada
            if records.get(placa, {}).get("status_atual") == "finalizada":
                continue

            ev = _get_eventos(token, str(m["id"]))
            records[placa] = {
                "placa": placa,
                "mecanico": mec["fullName"],
                "rampa": ev.get("rampa", ""),
                "data_entrada": ev.get("data_entrada"),
                "data_saida": ev.get("data_saida"),
                "status_atual": status,
            }

    if not records:
        return pd.DataFrame(
            columns=["placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"]
        )

    return pd.DataFrame(list(records.values()))
