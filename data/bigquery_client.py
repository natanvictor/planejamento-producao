import streamlit as st
import pandas as pd
from google.cloud import bigquery


def _get_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    return bigquery.Client(project=project)


def get_planejamento_do_dia(filial: str | None = None) -> pd.DataFrame:
    client = _get_client()

    query = """
        WITH ultima_manutencao AS (
          SELECT
            placa_veiculo AS placa,
            data_finalizacao,
            nivel_manutencao,
            tempo_estimado_execucao,
            ROW_NUMBER() OVER (PARTITION BY placa_veiculo ORDER BY data_criacao DESC) AS rn
          FROM `dm-mottu-aluguel.man_operacao.manutencoes_agrupadas`
        )
        SELECT
            o.filial,
            o.dia_ordem,
            o.placa,
            o.modelo,
            o.tipo_moto_km,
            o.dias_na_situacao,
            o.necessidade,
            o.origem,
            o.ordem_prioridade,
            o.lugarId,
            o.ordem,
            o.veiculoId,
            ma.data_finalizacao,
            ma.nivel_manutencao,
            ma.tempo_estimado_execucao
        FROM `dm-mottu-aluguel.exp_frota.ordem_de_producao_historico` o
        LEFT JOIN ultima_manutencao ma ON o.placa = ma.placa AND ma.rn = 1
        WHERE o.dia_ordem = CURRENT_DATE()
    """

    if filial:
        query += " AND o.filial = @filial"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("filial", "STRING", filial)]
        )
    else:
        job_config = bigquery.QueryJobConfig()

    query += " ORDER BY o.ordem_prioridade ASC NULLS LAST"

    df = client.query(query, job_config=job_config).to_dataframe()
    return df


def get_manutencoes_por_placa(filial: str | None = None) -> pd.DataFrame:
    """
    Última manutenção (aberta ou finalizada hoje) por placa da filial.
    Usado para enriquecer as motos que NÃO estão no planejamento com
    nível e tempo estimado. Colunas: placa, filial, nivel_manutencao,
    tempo_estimado_execucao, situacao_manutencao, data_finalizacao.
    """
    client = _get_client()

    where = "WHERE (data_finalizacao IS NULL OR DATE(data_finalizacao) = CURRENT_DATE())"
    job_config = bigquery.QueryJobConfig()
    if filial:
        where += " AND filial = @filial"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("filial", "STRING", filial)]
        )

    query = f"""
        SELECT
          placa_veiculo AS placa,
          filial,
          nivel_manutencao,
          tempo_estimado_execucao,
          situacao_manutencao,
          data_finalizacao
        FROM `dm-mottu-aluguel.man_operacao.manutencoes_agrupadas`
        {where}
        QUALIFY ROW_NUMBER() OVER (PARTITION BY placa_veiculo ORDER BY data_criacao DESC) = 1
    """

    return client.query(query, job_config=job_config).to_dataframe()
