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
    raw = resp.json()["result"]
    # A API pode retornar {"items": [...]} ou diretamente [...]
    items = raw["items"] if isinstance(raw, dict) else raw
    matched = [item["id"] for item in items if item.get("name") in _MECHANIC_POSITIONS]
    all_names = [item.get("name") for item in items]
    print(f"[RT] positions total={len(all_names)} matched={len(matched)}")
    print(f"[RT] positions nomes retornados: {all_names[:10]}")
    return matched


def _get_mecanicos(token: str, branch_code: str) -> list[dict]:
    branch_guid = _get_branch_guid(token, branch_code)
    print(f"[RT] branch_code={branch_code} branch_guid={branch_guid}")

    position_ids = _get_mechanic_position_ids(token)
    if not position_ids:
        print("[RT] AVISO: nenhum position_id encontrado — verifique nomes em _MECHANIC_POSITIONS")

    url = f"{_BASE_EMPLOYEE}employees/GetSimplified?BranchId={branch_guid}"
    for pid in position_ids:
        url += f"&PositionId={pid}"

    resp = requests.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()

    mecanicos = [
        {"fullName": e["fullName"], "code": e["code"]}
        for e in resp.json()["result"]
        if not e.get("isFired", False)
    ]
    print(f"[RT] mecânicos ativos encontrados: {len(mecanicos)}")
    if mecanicos:
        print(f"[RT] amostra: {mecanicos[:3]}")
    return mecanicos


def _get_manutencoes_hoje(token: str, mec_code: str) -> list[dict]:
    hoje = datetime.now(_TZ_BR).date().isoformat()
    url = (
        f"{_BASE_MAINT_V26}Manutencao/HistoricoPorMecanico"
        f"?mecanicoId={mec_code}&pagina=1&quantidadePorPagina=25"
    )
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        print(f"[RT] mec={mec_code} HTTP {resp.status_code}")
        return []

    todas = resp.json().get("dataResult", {}).get("manutencoes", [])
    result = []
    for m in todas:
        if datetime.fromisoformat(m["atualizacaoData"]).date().isoformat() == hoje:
            result.append({"id": m["id"], "placa": m["placa"], "situacao": m["situacao"]})

    if result:
        # Mostra tipos e valores de situacao para diagnosticar int vs string
        situacoes = [(r["situacao"], type(r["situacao"]).__name__) for r in result]
        print(f"[RT] mec={mec_code} manut_hoje={len(result)} situacoes={situacoes[:5]}")
    return result


def _get_eventos(token: str, maint_id: str) -> dict:
    url = f"{_BASE_MAINT_V2}Manutencao/Detalhes/Eventos/{maint_id}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    if resp.status_code != 200:
        return {}

    # Ordena ASC — iterar do mais antigo para o mais recente e sobrescrever
    # garante que o ÚLTIMO evento de cada tipo vença (sem break)
    log = sorted(
        resp.json().get("dataResult", []),
        key=lambda e: e.get("criacaoDataUTC", ""),
    )

    print(f"[RT:eventos] manut_id={maint_id} total_eventos={len(log)}")

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

        print(f"[RT:eventos]   ts={ts.strftime('%d/%m/%Y %H:%M:%S')} sid={sid} tipo={tipo} device={ev.get('deviceName')}")

        # Entrada = ÚLTIMO evento que iniciou manutenção (sid==2, sem break = sobrescreve)
        if sid == 2:
            data_entrada = ts

        # Saída = ÚLTIMO evento de finalização
        if sid == 4:
            data_saida = ts

    print(f"[RT:eventos] → entrada={data_entrada} saída={data_saida} rampa={rampa}")

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
    print(f"\n[RT] ===== get_status_em_tempo_real branch={branch_code} =====")
    token = _get_token()
    print("[RT] token OK")

    mecanicos = _get_mecanicos(token, branch_code)

    if not mecanicos:
        print("[RT] AVISO: lista de mecânicos vazia — retornando DataFrame vazio")
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

    print(f"[RT] situacoes vistas: {situacoes_vistas}")
    print(f"[RT] total placas com status real: {len(records)}")
    if records:
        sample = list(records.values())[:3]
        print(f"[RT] amostra records: {sample}")

    if not records:
        print("[RT] AVISO: nenhuma placa com situacao 2 ou 4 hoje")
        return pd.DataFrame(
            columns=["placa", "mecanico", "rampa", "data_entrada", "data_saida", "status_atual"]
        )

    df = pd.DataFrame(list(records.values()))
    print(f"[RT] DataFrame final: {df.shape} colunas={list(df.columns)}")
    return df
