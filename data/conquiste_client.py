import streamlit as st
import pandas as pd
from google.cloud import bigquery


def _get_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    return bigquery.Client(project=project)


_QUERY = """
WITH conquiste_historico AS (
  SELECT DISTINCT
    data_atualizacao,
    placa,
    filial                                                          AS Filial,
    modelo,
    tipoKm,
    situacao,
    diasSituacao,
    produto,
    CASE
      WHEN produto = '42.Extensão Auxílio' THEN 'Extensão Auxílio (ABL)'
      ELSE 'Conquiste Puro'
    END                                                             AS produto_categoria
  FROM `dm-mottu-aluguel.exp_frota.lista_motos_aux_historico`
  WHERE tipoVinculo            = 'Conquiste'
    AND situacaoClienteTitular = 'Ativo'
    AND situacao               = 'Em manutenção'
    AND diasSituacao           > 1
),
justificativa AS (
  SELECT
    placa,
    CASE
      WHEN justificativa = 'Conquiste - Falta de aprovação do orçamento' THEN NULL
      ELSE justificativa
    END                                                             AS justificativa,
    peca_faltante,
    mao_obra,
    data_criacao,
    fase_atual
  FROM `dm-mottu-aluguel.exp_frota.justificativa_producao`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa ORDER BY data_criacao DESC) = 1
),
manutencao_aberta AS (
  SELECT
    placa_veiculo                                                   AS placa,
    manutencao_id,
    DATE(data_criacao)                                              AS data_abertura_manutencao,
    situacao_manutencao,
    tipo_manutencao,
    mecanico,
    sintomas
  FROM `dm-mottu-aluguel.man_operacao.manutencoes_agrupadas`
  WHERE data_finalizacao IS NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa_veiculo ORDER BY data_criacao DESC) = 1
),
eventos_kanban AS (
  SELECT
    ev.placa,
    ev.manutencaoId,
    ev.evento_manutencao,
    ev.data_evento,
    ch.data_atualizacao                                             AS data_ref
  FROM `dm-mottu-aluguel.man_operacao.manutencao_evento` ev
  INNER JOIN manutencao_aberta  ma ON ev.manutencaoId = ma.manutencao_id
  INNER JOIN conquiste_historico ch ON ev.placa = ch.placa
         AND DATE(ev.data_evento) <= ch.data_atualizacao
  WHERE ev.evento_manutencao IN (
    'Criação','Iniciada Triagem','Iniciada Triagem N2',
    'Finalizada Triagem','Finalizada Triagem N2',
    'Iniciada Manutenção','Manutenção reaberta','Retornada para fila',
    'Enviou para Qualidade','Retornar envio qualidade',
    'Aprovada Qualidade','Reprovada Qualidade',
    'Orçamento Enviado','Orçamento Aprovado','Orçamento Reprovado'
  )
),
ultimo_evento_fluxo AS (
  SELECT
    placa,
    data_ref,
    evento_manutencao                                               AS ultimo_evento_fluxo,
    data_evento                                                     AS data_ultimo_evento_fluxo
  FROM eventos_kanban
  WHERE evento_manutencao IN (
    'Criação','Iniciada Triagem','Iniciada Triagem N2',
    'Finalizada Triagem','Finalizada Triagem N2',
    'Iniciada Manutenção','Manutenção reaberta','Retornada para fila',
    'Enviou para Qualidade','Retornar envio qualidade',
    'Aprovada Qualidade','Reprovada Qualidade'
  )
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa, data_ref ORDER BY data_evento DESC) = 1
),
ultimo_orcamento_enviado AS (
  SELECT placa, data_ref, data_evento AS data_ultimo_envio
  FROM eventos_kanban
  WHERE evento_manutencao = 'Orçamento Enviado'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY placa, data_ref ORDER BY data_evento DESC) = 1
),
flag_orcamento_aprovado AS (
  SELECT DISTINCT ue.placa, ue.data_ref
  FROM ultimo_orcamento_enviado ue
  INNER JOIN eventos_kanban apr
          ON apr.placa = ue.placa AND apr.data_ref = ue.data_ref
         AND apr.evento_manutencao = 'Orçamento Aprovado'
         AND apr.data_evento > ue.data_ultimo_envio
),
flag_orcamento_reprovado AS (
  SELECT DISTINCT ue.placa, ue.data_ref
  FROM ultimo_orcamento_enviado ue
  INNER JOIN eventos_kanban rep
          ON rep.placa = ue.placa AND rep.data_ref = ue.data_ref
         AND rep.evento_manutencao = 'Orçamento Reprovado'
         AND rep.data_evento > ue.data_ultimo_envio
),
flag_orcamento_pendente AS (
  SELECT ue.placa, ue.data_ref
  FROM ultimo_orcamento_enviado ue
  LEFT JOIN flag_orcamento_aprovado  apr ON ue.placa = apr.placa AND ue.data_ref = apr.data_ref
  LEFT JOIN flag_orcamento_reprovado rep ON ue.placa = rep.placa AND ue.data_ref = rep.data_ref
  WHERE apr.placa IS NULL AND rep.placa IS NULL
),
flag_orcamento_enviado AS (
  SELECT placa, data_ref, MIN(data_evento) AS data_primeiro_envio
  FROM eventos_kanban
  WHERE evento_manutencao = 'Orçamento Enviado'
  GROUP BY placa, data_ref
),
divisao_recente AS (
  SELECT filial, cm_nome, gerente_regional
  FROM `dm-mottu-aluguel.exp_frota.divisao_filiais`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY filial ORDER BY data_valor DESC) = 1
),
email_gerente_regional AS (
  SELECT nome_funcionario, email AS email_gerente_regional
  FROM `dm-mottu-aluguel.exp_colaboradores.funcionarios_filiais`
  WHERE cargo = 'Gerente Regional'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nome_funcionario ORDER BY 1) = 1
),
email_city_manager AS (
  SELECT nome_funcionario, email AS email_city_manager
  FROM `dm-mottu-aluguel.exp_colaboradores.funcionarios_filiais`
  WHERE cargo = 'City Manager'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY nome_funcionario ORDER BY 1) = 1
),
frota AS (
  SELECT placa, pais_filial
  FROM `exp_frota.frota_atual`
)
SELECT
  A.data_atualizacao,
  A.placa,
  A.Filial,
  A.modelo,
  A.tipoKm,
  A.produto,
  A.produto_categoria,
  A.diasSituacao,
  CASE
    WHEN A.diasSituacao > 60 THEN '5. Mais de 60 dias'
    WHEN A.diasSituacao > 30 THEN '4. Mais de 30 dias'
    WHEN A.diasSituacao > 13 THEN '3. Mais de 13 dias'
    WHEN A.diasSituacao >  3 THEN '2. Mais de 3 dias'
    ELSE                          '1. Mais de 1 dia'
  END                                                               AS faixa_dias,
  CASE
    WHEN uef.ultimo_evento_fluxo IN ('Enviou para Qualidade','Retornar envio qualidade')
      THEN '6. Em Qualidade'
    WHEN uef.ultimo_evento_fluxo = 'Aprovada Qualidade'
      THEN '7. Concluída'
    WHEN oa_apr.placa IS NOT NULL
      THEN 'Realizar manutenção'
    WHEN uef.ultimo_evento_fluxo = 'Reprovada Qualidade'
      THEN 'Realizar manutenção'
    WHEN op.placa IS NOT NULL
      THEN '4. Orçamento Enviado'
    WHEN oa_rep.placa IS NOT NULL
      THEN 'Enviar orçamento'
    WHEN uef.ultimo_evento_fluxo IN (
        'Finalizada Triagem','Finalizada Triagem N2',
        'Iniciada Manutenção','Retornada para fila','Manutenção reaberta')
     AND oe.placa IS NULL
      THEN 'Enviar orçamento'
    WHEN uef.ultimo_evento_fluxo IN ('Iniciada Triagem','Iniciada Triagem N2')
      THEN 'Enviar orçamento'
    ELSE 'Realizar triagem e Enviar orçamento'
  END                                                               AS kanban_coluna,
  CASE
    WHEN (uef.ultimo_evento_fluxo IS NULL OR uef.ultimo_evento_fluxo = 'Criação')
     AND oe.placa IS NULL
      THEN CASE WHEN A.diasSituacao <= 3 THEN 'CM' ELSE 'Regional' END
    WHEN uef.ultimo_evento_fluxo IN (
         'Finalizada Triagem','Finalizada Triagem N2',
         'Iniciada Manutenção','Retornada para fila','Manutenção reaberta')
     AND oe.placa IS NULL
      THEN CASE WHEN A.diasSituacao <= 7 THEN 'CM' ELSE 'Regional' END
    WHEN oa_rep.placa IS NOT NULL
      THEN CASE WHEN A.diasSituacao <= 7 THEN 'CM' ELSE 'Regional' END
    ELSE NULL
  END                                                               AS sla_responsavel,
  COALESCE(uef.ultimo_evento_fluxo, 'Sem evento')                   AS ultimo_evento_fluxo,
  uef.data_ultimo_evento_fluxo,
  CASE WHEN oe.placa     IS NOT NULL THEN 'Sim' ELSE 'Não' END      AS teve_orcamento_enviado,
  CASE WHEN oa_apr.placa IS NOT NULL THEN 'Sim' ELSE 'Não' END      AS tem_orcamento_aprovado,
  CASE WHEN oa_rep.placa IS NOT NULL THEN 'Sim' ELSE 'Não' END      AS tem_orcamento_reprovado,
  CASE WHEN op.placa     IS NOT NULL THEN 'Sim' ELSE 'Não' END      AS orcamento_pendente,
  oe.data_primeiro_envio                                             AS data_orcamento_enviado,
  ma.data_abertura_manutencao,
  ma.situacao_manutencao,
  ma.tipo_manutencao,
  ma.mecanico,
  ma.sintomas,
  CASE
    WHEN op.placa IS NOT NULL
      THEN 'Conquiste - Falta de aprovação do orçamento'
    ELSE COALESCE(J.justificativa, 'Não justificou')
  END                                                               AS justificativa,
  J.peca_faltante,
  J.mao_obra,
  J.data_criacao                                                    AS data_justificativa,
  J.fase_atual,
  CASE
    WHEN op.placa IS NOT NULL THEN 'Não Cobrar'
    WHEN J.justificativa IS NULL THEN 'Cobrar'
    WHEN J.justificativa IN (
      'Falha de conferência na ordem de produção',
      'Moto está em outra base',
      'Moto não localizada'
    ) THEN 'Cobrar'
    ELSE 'Não Cobrar'
  END                                                               AS cobranca,
  d.cm_nome,
  d.gerente_regional,
  egr.email_gerente_regional,
  ecm.email_city_manager                                            AS email,
  'natan.deus@mottu.com.br'                                         AS meu_email
FROM conquiste_historico           A
LEFT JOIN manutencao_aberta        ma      ON A.placa  = ma.placa
LEFT JOIN ultimo_evento_fluxo      uef     ON A.placa  = uef.placa     AND A.data_atualizacao = uef.data_ref
LEFT JOIN flag_orcamento_enviado   oe      ON A.placa  = oe.placa      AND A.data_atualizacao = oe.data_ref
LEFT JOIN flag_orcamento_aprovado  oa_apr  ON A.placa  = oa_apr.placa  AND A.data_atualizacao = oa_apr.data_ref
LEFT JOIN flag_orcamento_reprovado oa_rep  ON A.placa  = oa_rep.placa  AND A.data_atualizacao = oa_rep.data_ref
LEFT JOIN flag_orcamento_pendente  op      ON A.placa  = op.placa      AND A.data_atualizacao = op.data_ref
LEFT JOIN justificativa            J       ON A.placa  = J.placa
LEFT JOIN divisao_recente          d       ON A.Filial = d.filial
LEFT JOIN email_gerente_regional   egr     ON d.gerente_regional = egr.nome_funcionario
LEFT JOIN email_city_manager       ecm     ON d.cm_nome          = ecm.nome_funcionario
LEFT JOIN frota                    ft      ON A.placa  = ft.placa
WHERE data_atualizacao = CURRENT_DATE()
  AND A.diasSituacao  > 3
ORDER BY kanban_coluna, A.diasSituacao DESC
"""


def get_conquiste_anomalias() -> pd.DataFrame:
    client = _get_client()
    return client.query(_QUERY).to_dataframe()
