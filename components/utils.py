import pandas as pd

_EM_ANDAMENTO = {
    "Em Execução", "Em Triagem", "Aguardando Peça", "Em Qualidade",
    "Em Manutenção", "Aguardando Aprovação", "Orçamento Enviado",
    "Aguardando Aprovação do Orçamento", "Em Análise", "Retornada para fila",
}
_FINALIZADO = {"Finalizada", "Concluída", "Finalizado"}


def get_status_execucao(situacao) -> str:
    if pd.isna(situacao) or str(situacao).strip() == "":
        return "🔴 Aguardando Manutenção"
    if situacao in _FINALIZADO:
        return "🟢 Finalizado"
    if situacao in _EM_ANDAMENTO:
        return "🟡 Em Andamento"
    return "🔴 Aguardando Manutenção"
