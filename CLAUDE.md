# Dashboard de Planejamento de Produção — Mottu

Dashboard Streamlit de monitoramento operacional de manutenções. Roda com auto-refresh a cada 5 minutos.

---

## Estrutura de arquivos

```
planejamento-producao/
├── app.py                            # Ponto de entrada — abas, cache, sidebar
├── requirements.txt                  # Dependências Python
├── filiais.json                      # Mapeamento nome → {bq_filial, api_codigo} para 180+ filiais
├── .streamlit/
│   └── secrets.toml                  # Credenciais (ver seção abaixo)
├── data/
│   ├── bigquery_client.py            # Query do planejamento diário (Aba 1)
│   ├── realtime_client.py            # API Mottu em tempo real (Aba 1)
│   ├── conquiste_client.py           # Query anomalias Conquiste (Aba 2)
│   └── transferencia_client.py       # Query anomalias Transferência (Aba 3)
└── components/
    ├── kpi_cards.py                  # Cards KPI da Aba 1
    ├── tabela_producao.py            # Tabela da Aba 1
    ├── anomalias_conquiste.py        # KPIs + tabela da Aba 2
    ├── anomalias_transferencia.py    # KPIs + tabela da Aba 3
    └── utils.py                      # get_status_execucao() + paginar_dataframe()
```

---

## Credenciais necessárias

Arquivo `.streamlit/secrets.toml` (não versionado):

```toml
username = "usuario@mottu.com.br"     # SSO Mottu (para API em tempo real)
password = "senha_sso"
gcp_project_id = "dm-mottu-aluguel"   # Projeto BigQuery
```

As credenciais GCP são resolvidas via ADC (Application Default Credentials) quando rodando localmente. Em produção (Streamlit Cloud), usar o campo `[gcp_service_account]` no secrets.toml.

---

## Aba 1 — Planejamento de Produção

**O que faz:** Mostra o planejamento diário de manutenções da filial selecionada, enriquecido com status em tempo real da API Mottu.

**Filtros (sidebar + inline):**
- Filial — seletor no sidebar (180+ filiais Brasil + México)
- Status — Todos / não direcionada / em andamento / finalizada
- Prioridade — dinâmico conforme dados do dia

**KPIs:** Total planejado, Concluídas, Em andamento, Não direcionadas, % conclusão.

**Tabela:** Placa, Modelo, Prioridade, Necessidade, Status (🟢🟡🔴), Mecânico, Rampa, Entrada.

**Fontes de dados:**
- `dm-mottu-aluguel.exp_frota.ordem_de_producao_historico` — planejamento diário (BigQuery, `data/bigquery_client.py`)
- API Mottu (SSO → branch-management → employee-management → maintenance-backend v2/v2.6) — status em tempo real por mecânico (`data/realtime_client.py`)

**Comportamento de falha:** Se a API Mottu estiver indisponível, o dashboard exibe um banner de aviso e carrega apenas os dados do BigQuery, com todos os status como "não direcionada". As outras abas não são afetadas.

---

## Aba 2 — Anomalias Conquiste

**O que faz:** Lista motos com vínculo Conquiste, cliente ativo, em manutenção há mais de 3 dias.

**Filtros:**
- Filial, Produto Categoria, Cobrança, Status Execução, Placa (texto), Evento Manutenção

**KPIs:** Total anomalias, Cobrar, Não Cobrar, Sem Justificativa, Orçamento Pendente.

**Tabela (com cores):**
- Dias na Situação — gradiente de cor (amarelo >3d → laranja >13d → vermelho >30d → vinho >60d)
- Status (kanban) — cor por etapa do fluxo (triagem, orçamento, manutenção, qualidade, concluída)
- Mecânico e Entrada — vindos do BigQuery (`manutencoes_agrupadas`)
- Rampa e Saída — exibem "—" (não disponíveis no BigQuery para manutenções abertas)

**Paginação:** 50 registros por página.

**Lógica de cobrança:**
- **Cobrar:** sem justificativa, ou justificativa = "Falha de conferência" / "Moto está em outra base" / "Moto não localizada"
- **Não Cobrar:** orçamento pendente de aprovação, ou tem justificativa válida

**Fonte de dados:** Query com 15+ CTEs em `data/conquiste_client.py`.
Tabelas BigQuery: `exp_frota.lista_motos_aux_historico`, `man_operacao.manutencoes_agrupadas`, `man_operacao.manutencao_evento`, `exp_frota.justificativa_producao`, `exp_frota.divisao_filiais`, `exp_colaboradores.funcionarios_filiais`.

---

## Aba 3 — Anomalias Transferência

**O que faz:** Lista motos "Minha Mottu" em processo de transferência com prazo vencido ou próximo a vencer.

**Filtros:**
- Filial, Valida Prazo, Status Execução

**KPIs:** Total, Passou do Prazo, Atenção Próximo do Prazo, Dia de Transferência, No Prazo.

**Tabela (com cores):**
- Valida Prazo — vermelho (vencido), laranja (hoje), amarelo (1-7 dias), verde (>7 dias)
- Mecânico e Entrada — vindos do BigQuery (`manutencoes_agrupadas`)
- Rampa e Saída — exibem "—"

**Paginação:** 50 registros por página.

**Lógica de cobrança:**
- **COBRAR:** prazo ≤ 7 dias e sem justificativa, ou com justificativa "Falha de conferência" / "Moto não localizada"
- **NÃO COBRAR:** demais casos

**Fonte de dados:** Query com 6 CTEs em `data/transferencia_client.py`.
Tabelas BigQuery: `flt_regulatorio.minha_mottu_transferencia`, `exp_frota.frota_atual`, `man_operacao.manutencoes_agrupadas`, `exp_frota.justificativa_producao`, `exp_frota.divisao_filiais`, `exp_colaboradores.funcionarios_filiais`.

---

## Arquitetura de cache

| Função | TTL | Nota |
|--------|-----|------|
| `_load_filiais()` | `@st.cache_resource` (permanente) | Arquivo local, não muda |
| `_carregar_planejamento_bq()` | 5 min | Por filial selecionada |
| `_carregar_status_rt()` | 5 min | Por código de filial (API) |
| `_carregar_conquiste()` | 5 min | Sem parâmetro — todas as filiais |
| `_carregar_transferencia()` | 5 min | Sem parâmetro — todas as filiais |

---

## Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Autenticação GCP local: `gcloud auth application-default login`

---

## Melhorias pendentes

- **Rampa e Saída nas anomalias:** não disponíveis via BigQuery. Para popular, seria necessário chamar `GET /api/v2/Manutencao/Detalhes/Eventos/{id}` para cada `manutencao_id` — potencialmente lento (1 chamada por registro). Avaliar se vale implementar com `ThreadPoolExecutor`.
- **Exportação CSV/Excel:** nenhum botão de download nas tabelas.
- **Busca por texto em múltiplas colunas:** filtro de placa existe só na aba Conquiste.
- **Filtro multi-filial:** sidebar permite apenas uma filial por vez para o Planejamento.
- **Logs de debug:** `realtime_client.py` usa `print()` em vez de `logging` estruturado.
- **Sem ações diretas:** interface é somente leitura; não permite atualizar status, adicionar notas, etc.
