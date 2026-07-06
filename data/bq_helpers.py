import streamlit as st
from google.cloud import bigquery


def get_bq_client() -> bigquery.Client:
    project = st.secrets.get("gcp_project_id", None)
    return bigquery.Client(project=project)
