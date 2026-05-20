import streamlit as st
import pandas as pd
from google.cloud import bigquery


def _get_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    return bigquery.Client(project=project)


def get_planejamento_do_dia(filial: str | None = None) -> pd.DataFrame:
    client = _get_client()

    query = """
        SELECT
            filial,
            dia_ordem,
            placa,
            modelo,
            tipo_moto_km,
            dias_na_situacao,
            necessidade,
            origem,
            ordem_prioridade,
            lugarId,
            ordem,
            veiculoId
        FROM `dm-mottu-aluguel.exp_frota.ordem_de_producao_historico`
        WHERE dia_ordem = CURRENT_DATE()
    """

    if filial:
        query += " AND filial = @filial"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("filial", "STRING", filial)]
        )
    else:
        job_config = bigquery.QueryJobConfig()

    query += " ORDER BY ordem_prioridade ASC NULLS LAST"

    df = client.query(query, job_config=job_config).to_dataframe()
    return df
