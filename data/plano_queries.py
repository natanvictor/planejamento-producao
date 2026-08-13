"""Queries BigQuery — definem QUAIS motos e atributos NAO-manutencao + veiculoId.
O estado de manutencao (situacao, evento, horarios) vem da API em tempo real
(ver data/realtime_manutencao.py)."""
import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import credentials as oauth2_credentials
from google.oauth2 import service_account

_SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/cloud-platform",
]


def _get_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    # No Streamlit Cloud a credencial vem dos Secrets ([gcp_service_account]).
    # Localmente, sem esse bloco, cai no ADC do gcloud.
    info = st.secrets.get("gcp_service_account", None)
    if info:
        info = dict(info)
        if info.get("type") == "authorized_user":
            # NAO passar scopes: o token do gcloud ja vem com cloud-platform;
            # scopes diferentes causam invalid_scope na renovacao.
            creds = oauth2_credentials.Credentials.from_authorized_user_info(info)
        else:
            creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
        return bigquery.Client(project=project, credentials=creds)
    return bigquery.Client(project=project)


def _run(sql: str) -> pd.DataFrame:
    return _get_client().query(sql).to_dataframe()


# =====================================================================
# ABA 1 - Planejamento de Producao
# =====================================================================
_Q_ABA1 = """
SELECT placa, filial, TRIM(origem) AS categoria, veiculoId
FROM `dm-mottu-aluguel.exp_frota.ordem_de_producao_historico`
WHERE dia_ordem = CURRENT_DATE('America/Sao_Paulo')
QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY ordem_prioridade) = 1
"""


def get_aba1_planejamento() -> pd.DataFrame:
    return _run(_Q_ABA1)


# =====================================================================
# ABA 2 - Planejamento do Consultor (triagem)
# =====================================================================
_Q_ABA2 = """
SELECT
  placa, filial, modelo, categoria_nome AS categoria,
  IF(sla_estourado, 'Estourado', 'No prazo') AS sla,
  veiculo_id AS veiculoId
FROM `dm-mottu-aluguel.exp_frota.ordem_producao_consultor`
WHERE data_ref = CURRENT_DATE('America/Sao_Paulo')
QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY ordem_prioridade) = 1
"""


def get_aba2_consultor() -> pd.DataFrame:
    return _run(_Q_ABA2)


# =====================================================================
# ABA 3 - Anomalias de Conquiste (>13 dias, todas as filiais)
# =====================================================================
_Q_ABA3 = """
WITH conquiste_interna AS (
  SELECT
    placa, filial, diasSituacao, produto,
    CASE WHEN produto <> '42.Extensão Auxílio' THEN 'Conquiste Interna' ELSE 'Extensão Auxílio' END AS produto_categoria
  FROM `exp_frota.lista_motos_aux`
  WHERE tipoVinculo = 'Conquiste'
    AND situacaoClienteTitular = 'Ativo'
    AND situacao = 'Em manutenção'
    AND produto IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY diasSituacao DESC) = 1
),
titular_status AS (
  SELECT placa, ANY_VALUE(situacaoClienteTitular) AS situacaoClienteTitular
  FROM `exp_frota.lista_motos_aux`
  WHERE tipoVinculo = 'Conquiste'
  GROUP BY placa
),
cliente_raw AS (
  SELECT
    BranchName AS filial, PlateVehicle AS placa, AttendanceElapsedTimeMinutes AS tempo_minutos, MaintenanceId,
    ROW_NUMBER() OVER (PARTITION BY MaintenanceId ORDER BY atualizacao_dt DESC) AS rn
  FROM `dm-mottu-aluguel.exp_atendimentos.command_tower`
  WHERE ServiceTypeName LIKE '%Conquiste%'
    AND DATE(atualizacao_dt, 'America/Sao_Paulo') = CURRENT_DATE('America/Sao_Paulo')
),
cliente AS (
  SELECT filial, placa, CAST(ROUND(MAX(tempo_minutos)/1440) AS INT64) AS diasSituacao, 'Conquiste Cliente' AS produto_categoria
  FROM cliente_raw WHERE rn = 1
  GROUP BY filial, placa
),
cliente_dedup AS (
  SELECT c.filial, c.placa, c.diasSituacao, c.produto_categoria
  FROM cliente c
  LEFT JOIN conquiste_interna ci ON c.placa = ci.placa
  LEFT JOIN titular_status ts ON c.placa = ts.placa
  WHERE ci.placa IS NULL AND COALESCE(ts.situacaoClienteTitular, 'Ativo') <> 'Inativo'
),
unificado AS (
  SELECT placa, filial, diasSituacao, produto_categoria FROM conquiste_interna
  UNION ALL
  SELECT placa, filial, diasSituacao, produto_categoria FROM cliente_dedup
),
justificativa AS (
  SELECT placa, justificativa
  FROM `dm-mottu-aluguel.exp_frota.justificativa_producao`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY data_criacao DESC) = 1
),
frota AS (
  SELECT placa, id AS veiculoId FROM `exp_frota.frota_atual`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY id DESC) = 1
)
SELECT
  u.placa,
  u.filial,
  u.diasSituacao,
  u.produto_categoria AS categoria,
  COALESCE(j.justificativa, 'Não justificou') AS justificativa,
  IF(j.justificativa IS NOT NULL, 'Justificada', 'Não justificada') AS justificada,
  f.veiculoId
FROM unificado u
LEFT JOIN justificativa j ON u.placa = j.placa
LEFT JOIN frota f ON u.placa = f.placa
WHERE u.diasSituacao > 13
ORDER BY u.diasSituacao DESC
"""


def get_aba3_conquiste() -> pd.DataFrame:
    return _run(_Q_ABA3)


# =====================================================================
# ABA 4 - Transferencia Fim do Plano (Titular)
# =====================================================================
_Q_ABA4 = """
WITH lista_transferencia AS (
  SELECT veiculoid AS veiculoId, placa, prazo_fim_transferencia
  FROM `dm-mottu-aluguel.flt_regulatorio.minha_mottu_transferencia`
  WHERE filtro_contrato_valido = True AND titular_interna = True
    AND transferencia_finalizada = False AND em_transferencia = True
    AND veiculo_titular_situacao_id = 1500
),
frota AS (
  SELECT DISTINCT placa, lugar_nome AS filial FROM `exp_frota.frota_atual`
),
justificativa AS (
  SELECT placa, justificativa
  FROM `dm-mottu-aluguel.exp_frota.justificativa_producao`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY data_criacao DESC) = 1
)
SELECT
  t.placa,
  f.filial,
  CASE
    WHEN DATE_DIFF(t.prazo_fim_transferencia, CURRENT_DATE(), DAY) < 0 THEN 'Passou do Prazo'
    WHEN DATE_DIFF(t.prazo_fim_transferencia, CURRENT_DATE(), DAY) = 0 THEN 'Dia de Transferencia'
    WHEN DATE_DIFF(t.prazo_fim_transferencia, CURRENT_DATE(), DAY) BETWEEN 1 AND 7 THEN 'Atenção Proximo do Prazo'
    ELSE 'No Prazo'
  END AS status_prazo,
  t.prazo_fim_transferencia,
  COALESCE(j.justificativa, 'Não justificou') AS justificativa,
  t.veiculoId
FROM lista_transferencia t
LEFT JOIN frota f ON t.placa = f.placa
LEFT JOIN justificativa j ON t.placa = j.placa
ORDER BY t.prazo_fim_transferencia
"""


def get_aba4_transferencia() -> pd.DataFrame:
    return _run(_Q_ABA4)


# =====================================================================
# Fallback de manutencao FINALIZADA (info-by-vehicle-ids so devolve aberta)
# =====================================================================
_Q_ULT_MID = """
SELECT placa, manutencaoId
FROM `dm-mottu-aluguel.man_operacao.manutencao_eventos`
WHERE placa IN UNNEST(@placas)
QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY data_evento DESC) = 1
"""


def get_ultimo_mid_por_placa(placas: tuple) -> dict:
    """{placa: manutencaoId} da ultima manutencao (inclui finalizada) por placa.
    Fornece so o ID; o estado continua vindo da API ao vivo."""
    if not placas:
        return {}
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ArrayQueryParameter("placas", "STRING", list(placas))])
    df = _get_client().query(_Q_ULT_MID, job_config=job_config).to_dataframe()
    return {r.placa: int(r.manutencaoId)
            for r in df.itertuples() if pd.notna(r.manutencaoId)}
