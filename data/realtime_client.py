import logging

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


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
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Resposta SSO não contém 'access_token'. Chaves: {list(data.keys())}")
    return data["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get_branch_guid(token: str, branch_code: str) -> str:
    url = (
        f"{_BASE_BRANCH}branches?codes={branch_code}"
        "&getSetup=false&active=true&getRegion=false&getAddress=false&getDocuments=false"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    resp.raise_for_status()
    results = resp.json().get("result", [])
    if not results:
        raise ValueError(
            f"Nenhuma filial encontrada para o código '{branch_code}'. "
            "Verifique se o código está correto em filiais.json."
        )
    return results[0]["id"]


def _get_mechanic_position_ids(token: str) -> list[str]:
    resp = requests.get(f"{_BASE_EMPLOYEE}positions?Name=mec", headers=_headers(token), timeout=15)
    resp.raise_for_status()
    raw = resp.json()["result"]
    # A API pode retornar {"items": [...]} ou diretamente [...]
    items = raw["items"] if isinstance(raw, dict) else raw
    matched = [item["id"] for item in items if item.get("name") in _MECHANIC_POSITIONS]
    all_names = [item.get("name") for item in items]
    logger.info("positions total=%d matched=%d", len(all_names), len(matched))
    logger.debug("positions nomes retornados: %s", all_names[:10])
    return matched


def _get_mecanicos(token: str, branch_code: str) -> list[dict]:
    branch_guid = _get_branch_guid(token, branch_code)
    logger.info("branch_code=%s branch_guid=%s", branch_code, branch_guid)

    position_ids = _get_mechanic_position_ids(token)
    if not position_ids:
        logger.warning("Nenhum position_id encontrado — verifique nomes em _MECHANIC_POSITIONS")

    url = f"{_BASE_EMPLOYEE}employees/GetSimplified?BranchId={branch_guid}"
    for pid in position_ids:
        url += f"&PositionId={pid}"

    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()

    data = resp.json()
    employees = data.get("result", [])
    if not employees:
        logger.warning("API retornou lista vazia de funcionários para branch_guid=%s", branch_guid)
        return []
    mecanicos = [
        {"fullName": e["fullName"], "code": e["code"]}
        for e in employees
        if not e.get("isFired", False)
    ]
    logger.info("mecânicos ativos encontrados: %d", len(mecanicos))
    logger.debug("amostra: %s", mecanicos[:3])
    return mecanicos


def _get_manutencoes_hoje(token: str, mec_code: str) -> list[dict]:
    hoje = datetime.now(_TZ_BR).date().isoformat()
    url = (
        f"{_BASE_MAINT_V26}Manutencao/HistoricoPorMecanico"
        f"?mecanicoId={mec_code}&pagina=1&quantidadePorPagina=25"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        logger.warning(
            "Falha ao buscar manutenções do mecânico %s: HTTP %d — %s",
            mec_code, resp.status_code, resp.text[:200],
        )
        return []

    todas = resp.json().get("dataResult", {}).get("manutencoes", [])
    result = []
    for m in todas:
        if datetime.fromisoformat(m["atualizacaoData"]).date().isoformat() == hoje:
            result.append({"id": m["id"], "placa": m["placa"], "situacao": m["situacao"]})

    if result:
        situacoes = [(r["situacao"], type(r["situacao"]).__name__) for r in result]
        logger.debug("mec=%s manut_hoje=%d situacoes=%s", mec_code, len(result), situacoes[:5])
    return result


def _get_eventos(token: str, maint_id: str) -> dict:
    url = f"{_BASE_MAINT_V2}Manutencao/Detalhes/Eventos/{maint_id}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        logger.warning(
            "Falha ao buscar eventos da manutenção %s: HTTP %d — %s",
            maint_id, resp.status_code, resp.text[:200],
        )
        return {}

    # Ordena ASC — iterar do mais antigo para o mais recente e sobrescrever
    # garante que o ÚLTIMO evento de cada tipo vença (sem break)
    log = sorted(
        resp.json().get("dataResult", []),
        key=lambda e: e.get("criacaoDataUTC", ""),
    )

    logger.debug("eventos manut_id=%s total=%d", maint_id, len(log))

    rampa = None
    data_entrada = None
    data_saida = None

    for ev in log:
        if ev.get("deviceName"):
            rampa = ev["deviceName"]

        sid    = ev.get("situacaoId")
        tipo   = ev.get("eventoTipoId")
        ts_str = ev.get("criacaoData", "")
        if not ts_str:
            continue

        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(_TZ_BR)

        logger.debug(
            "  evento ts=%s sid=%s tipo=%s device=%s",
            ts.strftime("%d/%m/%Y %H:%M:%S"), sid, tipo, ev.get("deviceName"),
        )

        # Entrada = ÚLTIMO evento que iniciou manutenção (sid==2, sem break = sobrescreve)
        if sid == 2:
            data_entrada = ts

        # Saída = ÚLTIMO evento de finalização
        if sid == 4:
            data_saida = ts

    logger.debug("eventos resultado: entrada=%s saída=%s rampa=%s", data_entrada, data_saida, rampa)

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
    logger.info("get_status_em_tempo_real branch=%s", branch_code)
    token = _get_token()
    logger.info("Token SSO obtido com sucesso")

    mecanicos = _get_mecanicos(token, branch_code)

    if not mecanicos:
        logger.warning("Lista de mecânicos vazia para branch=%s — retornando DataFrame vazio", branch_code)
        return pd.DataFrame(
            columns=["placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"]
        )

    records: dict[str, dict] = {}
    situacoes_vistas = set()

    for mec in mecanicos:
        for m in _get_manutencoes_hoje(token, mec["code"]):
            placa = m.get("placa", "")
            if not placa:
                continue

            situacao = m.get("situacao", 0)
            situacoes_vistas.add((situacao, type(situacao).__name__))

            # Normaliza para int para comparação segura
            try:
                situacao_int = int(situacao)
            except (TypeError, ValueError):
                situacao_int = -1

            if situacao_int == 4:
                status = "finalizada"
            elif situacao_int == 2:
                status = "em andamento"
            else:
                continue

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

    logger.info("situações vistas: %s", situacoes_vistas)
    logger.info("total placas com status real: %d", len(records))
    if records:
        logger.debug("amostra records: %s", list(records.values())[:3])

    if not records:
        logger.warning("Nenhuma placa com situação 2 ou 4 hoje para branch=%s", branch_code)
        return pd.DataFrame(
            columns=["placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"]
        )

    df = pd.DataFrame(list(records.values()))
    logger.info("DataFrame final: %s colunas=%s", df.shape, list(df.columns))
    return df
