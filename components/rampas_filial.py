"""Visualizacao de "rampas ativas por filial" para Streamlit (st.components.v1.html).

Cada rampa comporta exatamente 1 moto por vez. Renderiza, por filial, uma faixa
horizontal de celulas coloridas — uma celula por rampa ativa — colorida pela
categoria da moto que esta nela.

Fonte dos dados (contexto Mottu): a lista de rampas ativas vem da API de
manutencoes ativas (endpoint `/api/v2.6/Ativas/{lugar}/Ativas?...&Situacoes=2`),
onde `plataforma` = rampa e o `tipo` da manutencao separa Interna x Cliente. A
divisao da interna em `planejamento` x `nao_planejamento` depende do cruzamento
da placa com o plano do dia (`ordem_de_producao_historico`) — ver
`categoria_da_moto` abaixo.
"""
from __future__ import annotations

import html
import re

import pandas as pd

# Cores por categoria — ajuste o tom aqui.
CORES_CATEGORIA: dict[str, str] = {
    "planejamento": "#28a745",      # verde  — interna do plano do dia
    "nao_planejamento": "#dc3545",  # vermelho — interna fora do plano
    "cliente": "#3632a8",           # azul   — manutencao de cliente
}

# Rotulos exibidos na legenda / tooltip.
ROTULO_CATEGORIA: dict[str, str] = {
    "planejamento": "Planejamento",
    "nao_planejamento": "Não planejamento",
    "cliente": "Cliente",
}

# Cor para categoria desconhecida (defensivo).
_COR_PADRAO = "#9e9e9e"

# Classificacao Interna x Cliente por `tipo` de manutencao (fonte: get_rampas do
# painel de producao). Exposto para reuso na derivacao da categoria.
TIPOS_INTERNA = frozenset({3, 4, 6, 9, 15})
TIPOS_CLIENTE = frozenset({1, 2, 5, 7, 10, 11, 12, 13})


def altura_componente(num_filiais: int) -> int:
    """Altura sugerida (px) para `st.components.v1.html(..., height=...)`.

    Cresce linearmente com o numero de filiais: 60px de cabecalho/legenda + 60px
    por linha de filial.
    """
    return 60 + max(num_filiais, 0) * 60


def _ordem_rampa(valor: object) -> tuple[str, int, str]:
    """Chave de ordenacao "natural" para rampas: 'R2' < 'R10' < 'R10a'."""
    s = str(valor)
    m = re.search(r"\d+", s)
    prefixo = re.sub(r"\d+", "", s).lower()
    numero = int(m.group()) if m else 0
    return (prefixo, numero, s)


def render_rampas_por_filial(
    df: pd.DataFrame,
    *,
    largura_nome_px: int = 180,
    largura_celula_px: int = 52,
    ordenar_filiais: bool = True,
) -> str:
    """Gera o HTML da faixa de rampas ativas por filial.

    Parametros
    ----------
    df:
        DataFrame com uma linha por rampa ativa e as colunas:
          - ``filial``    (str): nome da filial.
          - ``rampa``     (str): identificador da rampa (ex.: "R01", "Box 1").
          - ``moto_id``   (str): placa/identificador da moto na rampa.
          - ``categoria`` (str): "planejamento", "nao_planejamento" ou "cliente".
    largura_nome_px:
        Largura fixa (px) da coluna do nome da filial — mantem as linhas alinhadas.
    largura_celula_px:
        Largura minima (px) de cada celula de rampa.
    ordenar_filiais:
        Se ``True``, ordena as filiais alfabeticamente; senao preserva a ordem
        de aparicao no DataFrame.

    Retorna
    -------
    str
        HTML autocontido (com ``<style>`` inline) pronto para
        ``st.components.v1.html(html, height=altura_componente(n), scrolling=False)``.

    Levanta
    -------
    ValueError
        Se faltar alguma coluna obrigatoria.
    """
    obrigatorias = {"filial", "rampa", "moto_id", "categoria"}
    faltando = obrigatorias - set(df.columns)
    if faltando:
        raise ValueError(f"DataFrame sem colunas obrigatórias: {sorted(faltando)}")

    css = f"""
    <style>
      .rf-wrap {{ font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif; color:#111; padding:2px; }}
      .rf-legenda {{ display:flex; gap:18px; justify-content:flex-end; align-items:center;
                     margin:0 2px 12px 2px; font-size:13px; }}
      .rf-lg-item {{ display:inline-flex; align-items:center; gap:6px; }}
      .rf-lg-quad {{ width:14px; height:14px; border-radius:3px; display:inline-block;
                     box-shadow:inset 0 0 0 1px rgba(0,0,0,.12); }}
      .rf-linha {{ display:flex; align-items:center; margin-bottom:8px; }}
      .rf-nome {{ width:{largura_nome_px}px; min-width:{largura_nome_px}px; box-sizing:border-box;
                  font-weight:600; font-size:14px; padding-right:10px;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .rf-faixa {{ display:flex; gap:4px; flex:1; overflow-x:auto; padding-bottom:6px; }}
      .rf-celula {{ min-width:{largura_celula_px}px; height:34px; flex:0 0 auto;
                    display:flex; align-items:center; justify-content:center;
                    border-radius:4px; color:#fff; font-size:12px; font-weight:700;
                    cursor:default; box-shadow:inset 0 0 0 1px rgba(0,0,0,.10); }}
      .rf-celula:hover {{ filter:brightness(1.08); transform:translateY(-1px);
                          transition:transform .1s ease, filter .1s ease; }}
      .rf-vazio {{ color:#999; font-size:12px; font-style:italic; }}
      .rf-faixa::-webkit-scrollbar {{ height:7px; }}
      .rf-faixa::-webkit-scrollbar-thumb {{ background:#cfcfcf; border-radius:4px; }}
    </style>
    """

    legenda = "".join(
        f'<span class="rf-lg-item">'
        f'<span class="rf-lg-quad" style="background:{CORES_CATEGORIA[k]}"></span>'
        f'{html.escape(ROTULO_CATEGORIA[k])}</span>'
        for k in ("planejamento", "nao_planejamento", "cliente")
    )

    filiais = list(dict.fromkeys(df["filial"].dropna().tolist()))
    if ordenar_filiais:
        filiais = sorted(filiais, key=lambda s: str(s).lower())

    linhas: list[str] = []
    for filial in filiais:
        sub = df[df["filial"] == filial]
        sub = sub.sort_values(by="rampa", key=lambda col: col.map(_ordem_rampa))

        celulas: list[str] = []
        for r in sub.itertuples(index=False):
            cat = str(getattr(r, "categoria", "") or "")
            cor = CORES_CATEGORIA.get(cat, _COR_PADRAO)
            rotulo = ROTULO_CATEGORIA.get(cat, cat or "—")
            rampa_txt = html.escape(str(r.rampa))
            tooltip = html.escape(
                f"Rampa: {r.rampa}  |  Moto: {r.moto_id}  |  Categoria: {rotulo}"
            )
            celulas.append(
                f'<div class="rf-celula" style="background:{cor}" title="{tooltip}">{rampa_txt}</div>'
            )

        faixa = "".join(celulas) or '<span class="rf-vazio">sem rampas ativas</span>'
        linhas.append(
            f'<div class="rf-linha">'
            f'<div class="rf-nome" title="{html.escape(str(filial))}">{html.escape(str(filial))}</div>'
            f'<div class="rf-faixa">{faixa}</div>'
            f'</div>'
        )

    return (
        f'{css}<div class="rf-wrap">'
        f'<div class="rf-legenda">{legenda}</div>'
        f'{"".join(linhas)}'
        f'</div>'
    )


def categoria_da_moto(tipo: int, placa: str, placas_do_plano: set[str]) -> str:
    """Deriva a `categoria` de uma moto em rampa (helper opcional/upstream).

    - `tipo` de cliente  -> "cliente".
    - `tipo` interna e placa no plano do dia -> "planejamento".
    - `tipo` interna e placa fora do plano   -> "nao_planejamento".

    `placas_do_plano` = conjunto de placas de `ordem_de_producao_historico` de hoje.
    """
    if tipo in TIPOS_CLIENTE:
        return "cliente"
    return "planejamento" if placa in placas_do_plano else "nao_planejamento"
