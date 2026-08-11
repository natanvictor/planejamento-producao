# Gestão do Plano de Produção e Anomalias — Mottu

Dashboard Streamlit de monitoramento operacional de manutenções, em **4 abas**.

## Princípio de arquitetura (LEIA PRIMEIRO)

> **BigQuery define QUAIS motos; a API define o ESTADO de manutenção.**

- **BigQuery** (`data/plano_queries.py`) → *quais* motos entram em cada aba + atributos **não-manutenção** (categoria, SLA, dias, prazo, justificativa) + o `veiculoId`.
- **API Mottu em tempo real** (`data/realtime_manutencao.py`) → **todo** o estado de manutenção: situação, evento, horário que entrou, horário finalizada.

Motivo: a tabela BQ `man_operacao.manutencao_eventos` é **snapshot diário** (`modo_atualizacao: completa`), fica horas defasada. O estado de manutenção **precisa** ser tempo real → só a API entrega isso. Nunca voltar a puxar situação/evento/horário do BQ.

---

## Estrutura de arquivos

```
planejamento-producao/
├── app.py                         # 4 abas, cache, merge BQ+API, coloração
├── data/
│   ├── plano_queries.py           # 4 queries BQ (quais motos + veiculoId + atributos)
│   └── realtime_manutencao.py     # enriquecimento de manutenção via API em tempo real
├── components/
│   └── aba_tabela.py              # renderizador: filtros (filial+placa) + tabela colorida
└── .streamlit/secrets.toml        # credenciais (não versionado)
```

> `data/conquiste_client.py`, `data/transferencia_client.py`, `data/bigquery_client.py`,
> `data/realtime_client.py`, `components/kpi_cards.py`, `tabela_producao.py`,
> `anomalias_*.py`, `utils.py` são do app ANTIGO (3 abas) e **não são mais usados**.

## Credenciais (`.streamlit/secrets.toml`)

```toml
username = "usuario@mottu.com.br"     # SSO Mottu (API tempo real, password grant)
password = "senha_sso"
gcp_project_id = "dm-mottu-aluguel"   # BigQuery (ADC local)
```

---

## Fluxo de dados (por aba)

1. `_carregar_bq(aba)` (`@st.cache_data ttl=300`) → DataFrame com `placa, filial, ..., veiculoId`.
2. `_com_manutencao(df)` → pega `veiculoId`, chama `_enriquecer(tuple(ids))` (cache 5min) e adiciona colunas `Situação da Manutenção`, `_sid`, `Evento`, `Entrou na Manutenção`, `Finalizada`.
3. `render_aba(df, key)` → filtros na tela + tabela colorida.

### API em tempo real (`realtime_manutencao.enriquecer`)

- `POST /api/v3/Maintenance/info-by-vehicle-ids`  body `{"vehicleIds":[...]}` → `{vehicleId: maintenanceId}` (lote, chunk 300).
- `GET /api/v2/Manutencao/Detalhes/Eventos/{id}` (paralelo, `ThreadPoolExecutor` 24 workers + `Session` com pool grande) → timeline.
- Token: SSO password grant, `client_id=admin-v3-frontend-client`.
- Derivação da timeline (`_derivar`):
  - **situação/evento** = `situacaoDescricao` / `eventoTipoDescricao` do **último** evento.
  - **entrada** = 1ª vez `situacaoId==2` **no dia** (só considera o dia).
  - **finalizada** = último `situacaoId==4` **no dia**.
  - `situacao_id` (numérico) retornado para coloração robusta.

---

## As 4 abas

| # | Aba | Motos (BQ) | Colunas |
|---|-----|-----------|---------|
| 1 | **Planejamento de Produção** | `exp_frota.ordem_de_producao_historico` WHERE `dia_ordem = current_date` | Placa, Filial, Categoria¹, Situação, Entrou, Finalizada |
| 2 | **Planejamento do Consultor** | `exp_frota.ordem_producao_consultor` WHERE `data_ref = current_date` | Placa, Filial, Modelo, Categoria, SLA², Status da Triagem³, Entrou, Finalizada |
| 3 | **Anomalias de Conquiste** | query unificada (interna+cliente) `diasSituacao > 13`, **todas as filiais** | Placa, Filial, Dias na Situação, Evento, Situação, Entrou, Finalizada, Justificativa, Justificada? |
| 4 | **Anomalias de Titular Fim do Plano** | `flt_regulatorio.minha_mottu_transferencia` (em transferência, situação 1500) | Placa, Filial, Evento Manutenção, Situação, Status do Prazo⁴, Entrou, Finalizada |

¹ Aba 1 **não tem coluna "categoria"** na tabela → usa `origem` (Complementares, Suprir Agendamento, Conquiste, Limpeza…).
² SLA = `sla_estourado` → "Estourado" / "No prazo".
³ Status da Triagem: situação real-time em ("Aguardando Triagem","Em Triagem") ou sem manutenção → **Não realizado**; senão **Triagem realizada**.
⁴ Status do Prazo: `DATE_DIFF(prazo, hoje)` → Passou do Prazo / Dia de Transferencia / Atenção Proximo do Prazo / No Prazo.

### Filtros e coloração (`components/aba_tabela.py`)
- Filtros **na tela principal** (não sidebar): **Filial** + **Placa**, `st.multiselect` (busca por digitação + seleção múltipla).
- **Cores da Situação por `situacaoId`** (numérico, robusto):
  - 🔴 **1** Aguardando Manutenção, **5** Aguardando Triagem, **6** Em Triagem
  - 🟡 **2** Manutenção, **3** Qualidade
  - 🟢 **4** Finalizada
- Também colore: Status da Triagem (verde/vermelho), Justificada? (verde/vermelho), Status do Prazo.

> ⚠️ A API chama `situacaoId=2` de **"Manutenção"** (não "Em Manutenção") e `6` de **"Triagem"**. Por isso a cor é por **ID numérico**, não pelo texto.

---

## Enum de manutenção (fonte: production-order-backend + Dataform `manutencao_eventos`)

### `situacaoManutencao` (fase / situação — 6 estados)
| id | descrição (BQ) | API `situacaoDescricao` |
|----|----------------|--------------------------|
| 1 | Aguardando Manutenção | Aguardando Manutenção |
| 2 | Em Manutenção | **Manutenção** |
| 3 | Qualidade | Qualidade |
| 4 | Finalizada | Finalizada |
| 5 | Aguardando Triagem | Aguardando Triagem |
| 6 | Em Triagem | **Triagem** |

### `manutencaoEventoTipoId` (eventos / transições — principais)
0 Criação · 1 Iniciada Triagem · 2 Finalizada Triagem · 3 Iniciada Manutenção · 4 Enviou para Qualidade · 5 Aprovada Qualidade · 7 Reprovada Qualidade · 8 Retornada para fila · 13 Alterar mecânico · 15 Encerrar manutenção · 16 Cancelar manutenção · 18 Manutenção reaberta · 24/25 Iniciada/Finalizada Triagem N2 · 27 Retornar envio qualidade · 32/33/35 Orçamento Enviado/Aprovado/Reprovado · 36-40 Bloqueios. (Fonte real-time = `eventoTipoDescricao` da API.)

---

## Cache

| Função | TTL |
|--------|-----|
| `_carregar_bq(aba)` | 5 min (por aba) |
| `_enriquecer(ids)` | 5 min (por tupla de veiculoIds) |

Trocar filtro **não** re-chama a API (opera sobre o cache). Só o 1º load de cada janela de 5 min é lento.

## Rodar localmente

```bash
pip install -r requirements.txt
gcloud auth application-default login
streamlit run app.py --server.port 8501
```

## Caveats / pendências
- **1º load ~30-40s**: abas 1 e 2 enriquecem ~1200 e ~940 motos via API (1 chamada de lote + N `Eventos`). Mitigado por cache + spinner.
- `st.tabs` executa as 4 abas a cada rerun → as 4 enriquecem no 1º load (cacheado depois).
- Entrada/finalização "só do dia": manutenção iniciada em dia anterior aparece com "—" nesses campos (por design).
- Custo BQ: cada aba escaneia tabelas de plano (pequenas); o peso de manutenção migrou para a API.
