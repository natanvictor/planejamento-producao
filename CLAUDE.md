# Gestão do Plano de Produção e Anomalias — Mottu

Dashboard Streamlit de monitoramento operacional de manutenções, em **4 abas**.

## Princípio de arquitetura (LEIA PRIMEIRO)

> **BigQuery define QUAIS motos; a API define o ESTADO de manutenção.**

- **BigQuery** (`data/plano_queries.py`) → *quais* motos entram em cada aba + atributos **não-manutenção** (categoria, SLA, dias, prazo, justificativa) + o `veiculoId` + a **placa**.
- **API Mottu em tempo real** (`data/realtime_manutencao.py`) → **todo** o estado de manutenção: situação, evento, horário que entrou, horário finalizada.

Motivo: a tabela BQ `man_operacao.manutencao_eventos` é **snapshot diário** (`modo_atualizacao: completa`), fica horas defasada. O estado de manutenção **precisa** ser tempo real → só a API entrega isso. Nunca voltar a puxar situação/evento/horário do BQ.

> **Exceção (fallback de finalizadas):** o endpoint `info-by-vehicle-ids` só retorna a manutenção **ABERTA** do veículo (motos finalizadas voltam com `maintenanceId: null`). Sem tratamento, uma moto finalizada some do enriquecimento e aparece com Situação/Evento/horários **vazios** — nunca ficava verde "Finalizada". Fix: para os veículos sem manutenção aberta, buscamos apenas o **id da última manutenção** (inclui finalizada) no BQ `man_operacao.manutencao_eventos` por placa (`plano_queries.get_ultimo_mid_por_placa`) e enriquecemos pelo **mesmo endpoint de eventos ao vivo**. O BQ só entrega o ponteiro (id); o estado continua vindo da API. Por isso `enriquecer` recebe `{veiculoId: placa}`.

---

## Estrutura de arquivos

```
planejamento-producao/
├── app.py                         # 4 abas, cache, merge BQ+API, coloração + rampas ao vivo na aba 1
├── data/
│   ├── plano_queries.py           # 4 queries BQ (quais motos + veiculoId + placa) + get_ultimo_mid_por_placa (fallback finalizadas)
│   ├── realtime_manutencao.py     # enriquecimento de manutenção via API em tempo real (+ fallback BQ p/ finalizadas; deriva horários de triagem)
│   └── rampas_ativas.py           # rampas ativas por filial ao vivo (API /Ativas, Situacoes=2); lugar_id via filiais.json (api_codigo)
├── components/
│   ├── aba_tabela.py              # renderizador: filtros (filial+placa+situação, justificativa por checkbox) + tabela colorida
│   └── rampas_filial.py           # HTML da faixa "rampas ativas por filial" p/ st.components.v1.html
├── filiais.json                   # nome→{bq_filial, api_codigo}; api_codigo = lugar_id da API de manutenção
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
2. `_com_manutencao(df)` → monta `{veiculoId: placa}`, chama `_enriquecer(tuple(sorted(vp.items())))` (cache 5min) e adiciona colunas `Situação da Manutenção`, `_sid`, `Evento`, `Entrou na Manutenção`, `Finalizada`.
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
| 1 | **Planejamento de Produção** | `exp_frota.ordem_de_producao_historico` WHERE `dia_ordem = current_date` | Placa, Filial, Categoria¹, Situação, Entrou, Finalizada — **+ faixa "Rampas ativas por filial" abaixo da tabela** (ver seção própria) |
| 2 | **Planejamento do Consultor** | `exp_frota.ordem_producao_consultor` WHERE `data_ref = current_date` | Placa, Filial, Modelo, Categoria, SLA², Status da Triagem³, Situação, **Iniciou Triagem**, **Finalizou Triagem**⁶ |
| 3 | **Anomalias de Conquiste** | query unificada (interna+cliente) `diasSituacao > 13`, **todas as filiais** | Placa, Filial, Dias na Situação, Evento, Situação, Entrou, Finalizada, Justificativa, Justificada? |
| 4 | **Anomalias de Titular Fim do Plano** | `flt_regulatorio.minha_mottu_transferencia` (em transferência, situação 1500) | Placa, Filial, Evento Manutenção, Situação, **Data de Vencimento**⁵, **Dias até o Vencimento**⁷, Status do Prazo⁴, **Justificativa**⁸, Entrou, Finalizada |

¹ Aba 1 **não tem coluna "categoria"** na tabela → usa `origem` (Complementares, Suprir Agendamento, Conquiste, Limpeza…).
² SLA = `sla_estourado` → "Estourado" / "No prazo".
³ Status da Triagem: situação real-time em ("Aguardando Triagem","Em Triagem") ou sem manutenção → **Não realizado**; senão **Triagem realizada**.
⁴ Status do Prazo: `DATE_DIFF(prazo, hoje)` → Passou do Prazo / Dia de Transferencia / Atenção Proximo do Prazo / No Prazo.
⁵ Data de Vencimento: `prazo_fim_transferencia` (data-limite da transferência), formatada `dd/mm/aaaa`. Vazio → "—".
⁶ Aba 2 é **só o planejamento (triagem)** → os horários mostram **início/fim da TRIAGEM**, não da manutenção. Derivados em `realtime_manutencao._derivar`: `entrada_triagem` = 1º evento "Iniciada Triagem" (ou `situacaoId==6`) no dia; `finalizada_triagem` = último "Finalizada Triagem" no dia. KPI da aba 2 = "Iniciou triagem". Só eventos **do dia** (mesmo design de Entrou/Finalizada).
⁷ Dias até o Vencimento: `DATE_DIFF(prazo_fim_transferencia, hoje)` calculado no **Streamlit** (fuso `America/Sao_Paulo`); negativo = vencido; sem data → "—".
⁸ Aba 4 ganhou `LEFT JOIN exp_frota.justificativa_producao` (mesma da aba 3); COALESCE → "Não justificou".

### Filtros, cartões e coloração (`components/aba_tabela.py`)
- Filtros **na tela principal** (não sidebar): **Filial** + **Placa** + **Situação da Manutenção** (todas as abas), `st.multiselect` (busca por digitação + seleção múltipla).
- **Filtro de justificativa por checkbox** (abas 3 e 4, quando existe coluna `Justificativa`): `st.expander` com uma checkbox por justificativa distinta — **marcada = mantém** a linha. Escolhe quais justificativas tirar/ficar.
- **Cartões (KPIs) no topo**, `st.metric`, refletem o **filtro atual**: **Motos (placas)** = `Placa.nunique()`; **Finalizadas** = `_sid == 4`; **Iniciou manutenção** = `Entrou na Manutenção` preenchido (≠ vazio).
  - **Aba 2 (Consultor)** substitui "Finalizadas" por **Triagem finalizada** (`Status da Triagem == "Triagem realizada"`) e adiciona **% Triagem finalizada** (triagem finalizada / total de placas). Detecção pela presença da coluna `Status da Triagem`.
- **Cores da Situação por `situacaoId`** (numérico, robusto):
  - 🔴 **1** Aguardando Manutenção, **5** Aguardando Triagem, **6** Em Triagem
  - 🟡 **2** Manutenção, **3** Qualidade
  - 🟢 **4** Finalizada
- Também colore: Status da Triagem (verde/vermelho), Justificada? (verde/vermelho), Status do Prazo.

> ⚠️ A API chama `situacaoId=2` de **"Manutenção"** (não "Em Manutenção") e `6` de **"Triagem"**. Por isso a cor é por **ID numérico**, não pelo texto.

---

## Rampas ativas por filial (aba 1, abaixo da tabela)

Faixa horizontal de células, **uma linha por filial**, **uma célula por rampa ativa** (cada rampa = 1 moto), colorida pela categoria da moto. Renderizada via `st.components.v1.html` com o HTML de `components/rampas_filial.py`.

> **Princípio:** BQ (plano do dia da aba 1) diz **quais placas são do plano**; a API ao vivo diz **quais rampas estão ocupadas agora** e por qual moto/tipo.

- **Dados ao vivo** (`data/rampas_ativas.py`): `GET /api/v2.6/Ativas/{lugar_id}/Ativas?Tipos=...&Situacoes=2` → manutenções em curso (situação 2). Campos usados: `plataforma` (= a **rampa**), `placa`, `tipo`, `ultimoMecanicoNome`. Descarta plataformas de **alinhamento/iot**. `lugar_id` vem de `filiais.json` (`bq_filial` → `api_codigo`). Token/sessão reaproveitados de `realtime_manutencao`. Paralelo (24 workers), cache 5 min.
- **Classificação da categoria** (em `app.py`, cruzando com as placas do plano da aba 1):
  - `tipo ∈ {1,2,5,7,10,11,12,13}` → **cliente** 🔵 (`#3632a8`)
  - interna (`tipo ∈ {3,4,6,9,15}`) e placa **no plano de hoje** → **planejamento** 🟢 (`#28a745`)
  - interna e placa **fora do plano** → **nao_planejamento** 🔴 (`#dc3545`)
  - comparação de placa é **normalizada** (remove hífen/símbolos, upper) p/ evitar gotcha placa com/sem hífen.
  - **Leitura de decisão:** vermelho = rampa sendo gasta **fora do plano** (mecânico burlando a fila).
- **Sob demanda (gate por botão):** só busca a API ao clicar **"🔧 Carregar rampas ativas"** (`st.session_state["mostrar_rampas"]`). Motivo: a aba 1 é Brasil inteiro → seria ~1 chamada por filial do plano (100+) a cada janela de cache, e `st.tabs` roda as 4 abas a cada rerun. **Follow-up em aberto:** avaliar se vira automático, se filtra por filial, e/ou incluir mecânico no tooltip.
- `render_rampas_por_filial(df[filial,rampa,moto_id,categoria])` → HTML autocontido; legenda no topo-direito; nome da filial com largura fixa; faixa com `overflow-x:auto`; tooltip por célula (rampa/moto/categoria); cores em `CORES_CATEGORIA` (dict configurável no topo). Altura via `altura_componente(n) = 60 + n*60`.

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
| `_enriquecer(vid_placa_items)` | 5 min (por tupla de `(veiculoId, placa)`) |
| `_carregar_rampas(filiais)` | 5 min (por tupla de filiais do plano; aba 1, sob demanda) |

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
