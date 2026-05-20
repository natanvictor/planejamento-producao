import streamlit as st
import pandas as pd
from google.cloud import bigquery


def _get_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    return bigquery.Client(project=project)


_QUERY = """
WITH lista_transferencia AS (
  SELECT
    veiculoid,
    placa,
    prazo_fim_transferencia,
    dias_atraso_fim
  FROM `dm-mottu-aluguel.flt_regulatorio.minha_mottu_transferencia`
  WHERE filtro_contrato_valido = True
    AND titular_interna = True
    AND transferencia_finalizada = False
    AND em_transferencia = True
    AND veiculo_titular_situacao_id = 1500
),

ultima_manutencao AS (
  SELECT
    placa_veiculo AS placa,
    DATE(data_criacao) AS data_criacao,
    situacao_manutencao,
    tempo_estimado_execucao,
    tipo_manutencao,
    ROW_NUMBER() OVER (PARTITION BY placa_veiculo ORDER BY data_criacao DESC) AS rn
  FROM `man_operacao.manutencoes_agrupadas`
  WHERE DATE(data_finalizacao) IS NULL
),

frota AS (
  SELECT DISTINCT
    placa,
    lugar_nome
  FROM `exp_frota.frota_atual`
),

justificativas AS (
  SELECT
    placa,
    DATE(data_criacao) AS data_criacao,
    justificativa,
    peca_faltante,
    mao_obra,
    fase_atual,
    ROW_NUMBER() OVER (PARTITION BY placa ORDER BY data_criacao DESC) AS rn_just
  FROM `exp_frota.justificativa_producao`
),

divisao_filiais AS (
  SELECT
    filial,
    cm_nome,
    gerente_regional,
    ROW_NUMBER() OVER (PARTITION BY filial ORDER BY data_valor DESC) AS rn_data
  FROM `dm-mottu-aluguel.exp_frota.divisao_filiais`
),

email AS (
  SELECT
    nome_funcionario,
    email,
    ROW_NUMBER() OVER (PARTITION BY filial ORDER BY data_criacao DESC) AS rn_2
  FROM `exp_colaboradores.funcionarios_filiais`
  WHERE cargo = 'City Manager'
)

SELECT
  A.placa,
  A.lugar_nome AS filial,
  B.prazo_fim_transferencia,
  DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) AS data_ate_vencimento,
  C.data_criacao,
  C.situacao_manutencao,
  C.tempo_estimado_execucao,
  C.tipo_manutencao,
  D.data_criacao AS data_justificativa,
  D.justificativa,
  D.peca_faltante,
  D.mao_obra,
  D.fase_atual,
  E.cm_nome,
  E.gerente_regional,
  F.email,
  CASE
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) < 0
      THEN 'Passou do Prazo'
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) = 0
      THEN 'Dia de Transferencia'
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) BETWEEN 1 AND 7
      THEN 'Atenção Proximo do Prazo'
    ELSE 'No Prazo'
  END AS valida_prazo,
  CASE
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) <= 7 AND D.justificativa IS NULL THEN 'COBRAR'
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) <= 7 AND D.justificativa = 'Falha de conferência na ordem de produção' THEN 'COBRAR'
    WHEN DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) <= 7 AND D.justificativa = 'Moto não localizada' THEN 'COBRAR'
    ELSE 'NÃO COBRAR'
  END AS cobranca

FROM frota A
INNER JOIN lista_transferencia B ON A.placa = B.placa
LEFT JOIN ultima_manutencao C ON A.placa = C.placa AND C.rn = 1
LEFT JOIN justificativas D ON A.placa = D.placa AND D.rn_just = 1
LEFT JOIN divisao_filiais E ON A.lugar_nome = E.filial AND E.rn_data = 1
LEFT JOIN email F ON E.cm_nome = F.nome_funcionario AND F.rn_2 = 1
WHERE DATE_DIFF(B.prazo_fim_transferencia, CURRENT_DATE(), DAY) < 0
ORDER BY data_ate_vencimento DESC
"""


def get_transferencia_anomalias() -> pd.DataFrame:
    client = _get_client()
    return client.query(_QUERY).to_dataframe()
