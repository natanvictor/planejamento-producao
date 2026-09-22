"""Aba 5 - Anomalia Geral (Desvio de Capacidade).

Renderiza um cartao de ALERTA por filial que tem backlog critico (titular fim do
plano E Conquiste >13d sem orcamento enviado) e esta com moto NAO PLANEJADA na
rampa agora. Esquerda = o erro (placa/rampa/mecanico/nivel/hora); direita = o que
deveria estar na rampa (backlog critico). A montagem dos dados fica no app.py; aqui
so o layout (mesmos componentes nativos do Streamlit das demais abas).
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
.ag-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ag-name{font-size:17px;font-weight:750}
.ag-reg{color:#8b93a7;font-size:12.5px}
.ag-cm{margin-left:auto;color:#8b93a7;font-size:12.5px}
.ag-cm b{color:#e6e9ef}
.ag-h4{font-size:11.5px;font-weight:750;text-transform:uppercase;letter-spacing:.5px;margin:2px 0 10px}
.ag-h4.err{color:#ff5a5f}
.ag-h4.ok{color:#00d563}
.ag-err{display:flex;align-items:center;gap:12px;background:#2a1416;border:1px solid #4a1c20;
        border-left:3px solid #ff4b4b;border-radius:9px;padding:9px 12px;margin-bottom:8px}
.ag-err .pl{font-family:Consolas,ui-monospace,monospace;font-weight:750;letter-spacing:1px;
            font-size:15px;min-width:96px}
.ag-err .wh{color:#e9bfc1;font-size:12.5px;flex:1;line-height:1.35}
.ag-err .wh b{color:#fff}
.ag-err .tm{text-align:right;min-width:56px}
.ag-err .tm .h{font-weight:750;font-size:15px;color:#ff8f93;font-variant-numeric:tabular-nums}
.ag-err .tm .l{color:#8b93a7;font-size:9.5px;text-transform:uppercase;letter-spacing:.4px}
.ag-sec{color:#8b93a7;font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 4px}
.ag-sec:first-child{margin-top:0}
.ag-bl{display:flex;align-items:center;gap:10px;padding:6px 2px;border-bottom:1px dashed #262c3a;font-size:13px}
.ag-bl:last-child{border-bottom:none}
.ag-bl .pl{font-family:Consolas,ui-monospace,monospace;font-weight:650;min-width:84px}
.ag-bl .pz{font-weight:650;font-size:12px}
.ag-bl .st{margin-left:auto;color:#8b93a7;font-size:11.5px}
.ag-red{color:#ff4b4b}.ag-amb{color:#f5b731}.ag-mut{color:#8b93a7}
.ag-more{color:#8b93a7;font-size:12px;padding-top:6px}
.ag-ok{color:#00d563;font-size:13px}.ag-ok span{color:#8b93a7}
</style>
"""


def _err_row(m: dict) -> str:
    return (
        f"<div class='ag-err'><span class='pl'>{m['placa']}</span>"
        f"<span class='wh'>Rampa <b>{m['rampa']}</b> · Mec. <b>{m['mec']}</b> · {m['nivel']}</span>"
        f"<span class='tm'><div class='h'>{m['hora'] or '—'}</div><div class='l'>entrou</div></span></div>"
    )


def _bl_row(m: dict) -> str:
    cls = {"red": "ag-red", "amber": "ag-amb"}.get(m.get("urg"), "ag-mut")
    return (
        f"<div class='ag-bl'><span class='pl'>{m['placa']}</span>"
        f"<span class='pz {cls}'>{m['prazo']}</span>"
        f"<span class='st'>{m['st']}</span></div>"
    )


def render_aba5(dados: dict, mostrar_ok: bool) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    k = dados["kpis"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filiais ACIONAR", k["acionar"], help="Backlog crítico + moto fora do plano na rampa agora")
    c2.metric("Não planejadas na rampa", k["nao_plan"], help="Motos fora do plano nas filiais acionáveis")
    c3.metric("Backlog crítico", k["backlog"], help="Titular fim do plano + Conquiste >13d sem orçamento")
    c4.metric("Só backlog (ok)", k["so_backlog"], help="Têm backlog mas a rampa está no plano")

    if not dados["acionar"] and not (mostrar_ok and dados["ok"]):
        st.success("Nenhuma filial para acionar: quem tem backlog crítico está com a rampa no plano. 🎉")
        return

    for f in dados["acionar"]:
        with st.container(border=True):
            st.markdown(
                f"<div class='ag-head'><span>🔴</span><span class='ag-name'>{f['filial']}</span>"
                f"<span class='ag-reg'>{f['regional']}</span>"
                f"<span class='ag-cm'>CM: <b>{f['cm']}</b></span></div>",
                unsafe_allow_html=True)
            esq, dir_ = st.columns([1.15, 1])
            with esq:
                st.markdown("<div class='ag-h4 err'>⚠️ Fazendo fora do plano (agora)</div>",
                            unsafe_allow_html=True)
                st.markdown("".join(_err_row(m) for m in f["fora"]), unsafe_allow_html=True)
            with dir_:
                st.markdown("<div class='ag-h4 ok'>✅ Deveria colocar na rampa</div>",
                            unsafe_allow_html=True)
                if f["titular"]:
                    st.markdown("<div class='ag-sec'>Titular fim do plano</div>", unsafe_allow_html=True)
                    st.markdown("".join(_bl_row(m) for m in f["titular"]), unsafe_allow_html=True)
                if f["conquiste"]:
                    st.markdown("<div class='ag-sec'>Conquiste &gt;13d sem orçamento</div>",
                                unsafe_allow_html=True)
                    st.markdown("".join(_bl_row(m) for m in f["conquiste"]), unsafe_allow_html=True)
                if f["extra"]:
                    st.markdown(f"<div class='ag-more'>+ {f['extra']} placas no backlog…</div>",
                                unsafe_allow_html=True)

    if mostrar_ok:
        for f in dados["ok"]:
            with st.container(border=True):
                st.markdown(
                    f"<div class='ag-head'><span>🟢</span><span class='ag-name'>{f['filial']}</span>"
                    f"<span class='ag-reg'>{f['regional']}</span></div>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='ag-ok'>Backlog crítico ({f['backlog']} motos), mas "
                    f"{f['rampas']} rampa(s) no plano. <span>Sem desvio — não precisa acionar.</span></div>",
                    unsafe_allow_html=True)
