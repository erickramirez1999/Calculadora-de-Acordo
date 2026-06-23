"""
Wizard de Novo Acordo — 7 passos (briefing Seção 16).

Passo 1: Identificação cliente + Negociador
Passo 2: Upload .xlsx títulos
Passo 3: Parâmetros financeiros (4 percentuais)
Passo 4: Calculadora (preview com juros calculados)
Passo 5: Configuração parcelamento (tipo, data, periodicidade, qtd parcelas)
Passo 6: Preview cronograma
Passo 7: Confirmação (Salvar Acordo / Salvar Rascunho)

Estado guardado em st.session_state["wizard"].
Suporta salvar rascunho em qualquer passo.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

from src.banco import repo_cliente, repo_usuario, repo_acordo, repos_auxiliares
from src.banco.repo_acordo import salvar_acordo_completo
from src.modelos.tipos import (
    Empresa, Periodicidade, PerfilUsuario, StatusAcordo, TipoCobranca,
)
from src.servicos.fifo import montar_acordo_qtd_fixa, montar_acordo_valor_fixo, validar_consistencia
from src.servicos.juros import calcular_boleto_caso1
from src.servicos.leitor_xlsx import (
    gerar_template_xlsx,
    importar_xlsx_titulos,
    montar_relatorio_importacao,
)
from src.utils.feedback import drenar_mensagens
from src.utils.formatadores import formatar_brl, formatar_data
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE


CHAVE_ESTADO = "wizard"


def renderizar_wizard(usuario):
    drenar_mensagens()
    # Diretoria agora pode criar acordos também (decisão Erick 13/05/2026)
    # Os 3 perfis (ADMIN, DIRETORIA, COBRANCA) podem usar o wizard.

    # Detecta se veio da Calculadora ANTES de inicializar
    veio_da_simulacao = st.session_state.get("pre_calc_disponivel", False)
    # Detecta se veio do perfil do cliente ANTES de inicializar
    veio_do_cliente = bool(st.session_state.get("novo_acordo_cliente_preset"))

    _inicializar_estado(usuario)

    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>➕ Novo Acordo</h1>", unsafe_allow_html=True)

    if veio_da_simulacao:
        st.success(
            "✓ **Simulação carregada da Calculadora.** Os títulos, parâmetros e "
            "parcelamento já estão preenchidos. Só preencha o cliente no passo 1 e avance."
        )

    estado = st.session_state[CHAVE_ESTADO]
    passo = estado["passo_atual"]

    # Banner se veio do perfil do cliente (já tá no Passo 2)
    if veio_do_cliente or (passo >= 2 and estado.get("cliente_id")):
        st.info(
            f"📌 Acordo sendo criado para o cliente **{estado.get('cliente_nome', '')}**. "
            f"Se quiser ajustar dados do cliente, volte ao **Passo 1**."
        )

    _stepper(passo)

    # Roteia pro passo correto
    if passo == 1:
        _passo_1_identificacao(usuario)
    elif passo == 2:
        _passo_2_upload(usuario)
    elif passo == 3:
        _passo_3_parametros(usuario)
    elif passo == 4:
        _passo_4_calculadora(usuario)
    elif passo == 5:
        _passo_5_parcelamento(usuario)
    elif passo == 6:
        _passo_6_preview(usuario)
    elif passo == 7:
        _passo_7_confirmar(usuario)


# ============================================================
# ESTADO E NAVEGAÇÃO
# ============================================================

def _inicializar_estado(usuario):
    """Carrega rascunho, simulação da Calculadora, preset de cliente, ou cria estado vazio."""
    if CHAVE_ESTADO in st.session_state:
        return

    # 1) Se veio com rascunho pra retomar
    rascunho_id = st.session_state.get("rascunho_id") or st.session_state.pop("rascunho_retomar_id", None)
    if rascunho_id:
        # Admin pode retomar rascunho de qualquer um
        eh_admin = usuario.perfil == PerfilUsuario.ADMIN
        if eh_admin:
            rasc = repos_auxiliares.buscar_rascunho(rascunho_id, usuario_id=None)
        else:
            rasc = repos_auxiliares.buscar_rascunho(rascunho_id, usuario.id)
        if rasc:
            estado = rasc["estado"]
            estado["rascunho_id"] = rascunho_id
            estado["passo_atual"] = rasc["passo_atual"]
            st.session_state[CHAVE_ESTADO] = estado
            return

    # 1.5) Veio do perfil do cliente com Novo Acordo
    # (decisão Erick 13/05/2026: pula passo 1 porque cliente já tá definido)
    preset_cliente = st.session_state.get("novo_acordo_cliente_preset")
    if preset_cliente:
        # Verifica se vieram títulos pré-carregados do perfil do cliente
        titulos_pre = st.session_state.pop("pre_titulos_cliente", [])

        st.session_state[CHAVE_ESTADO] = {
            "passo_atual": 2,  # pula direto pro Passo 2 (Upload de títulos)
            "rascunho_id": None,
            # Cliente PRÉ-PREENCHIDO
            "cliente_id": preset_cliente.get("cliente_id"),
            "cliente_nome": preset_cliente.get("cliente_nome", ""),
            "cliente_cnpj": preset_cliente.get("cliente_cnpj", ""),
            "cliente_contato": preset_cliente.get("cliente_contato", ""),
            "cliente_email": preset_cliente.get("cliente_email", ""),
            "cliente_telefone": preset_cliente.get("cliente_telefone", ""),
            "cliente_tem_whatsapp": preset_cliente.get("cliente_tem_whatsapp", False),
            "negociador_id": usuario.id,
            # Títulos pré-carregados do cliente (se existirem)
            "boletos_dict": titulos_pre,
            "pct_juros_titulos": 8.0,
            "pct_multa_titulos": 2.0,
            "pct_juros_mora": 5.0,
            "pct_multa_mora": 2.0,
            "pct_desconto": 0.0,
            "data_acordo": date.today().isoformat(),
            "tipo_cobranca": "BOLETO",
            "periodicidade": "MENSAL",
            "intervalo_personalizado_dias": 1,
            "modo_parcelamento": "QTD",
            "qtd_parcelas": 12,
            "valor_parcela": 0.0,
            "data_primeira_parcela": date.today().isoformat(),
            "boletos_calculados": [],
            "parcelas_calculadas": [],
            "observacoes": "",
            "justificativa_aprovacao": "",
        }

        # Se vieram títulos, também pré-popula o session_state do uploader
        # para que apareçam na aba "📑 Atuais" e na lista de seleção
        if titulos_pre:
            st.session_state["wiz_arquivos_importados"] = [{
                "chave_uploader": "pre_titulos_cliente",
                "nome": f"Títulos de {preset_cliente.get('cliente_nome', 'cliente')} (cadastrados)",
                "boletos": titulos_pre,
                "erros_bloqueantes": False,
                "feedback": None,
            }]
            st.session_state["wiz_qtd_slots_upload"] = 1
            st.session_state["wiz_titulos_selecionados"] = {
                b["numero_unico"]: True for b in titulos_pre
            }

        # Limpa preset pra não reaplicar
        del st.session_state["novo_acordo_cliente_preset"]
        return

    # 2) Se a Calculadora carregou uma simulação, consumir aqui
    if st.session_state.get("pre_calc_disponivel"):
        pre_boletos = st.session_state.get("pre_calc_boletos", [])
        pre_data_acordo = st.session_state.get("pre_calc_data_acordo", date.today())
        pre_juros = st.session_state.get("pre_calc_juros", 8.0)
        pre_multa = st.session_state.get("pre_calc_multa", 2.0)
        pre_juros_mora = st.session_state.get("pre_calc_juros_mora", 5.0)
        pre_multa_mora = st.session_state.get("pre_calc_multa_mora", 2.0)
        pre_desconto = st.session_state.get("pre_calc_desconto", 0.0)
        pre_tipo = st.session_state.get("pre_calc_tipo_cobranca", "BOLETO")
        pre_periodicidade = st.session_state.get("pre_calc_periodicidade", "MENSAL")
        pre_intervalo = st.session_state.get("pre_calc_intervalo_pers", 1)
        pre_modo = st.session_state.get("pre_calc_modo", "QTD")
        pre_qtd = st.session_state.get("pre_calc_qtd_parcelas", 12)
        pre_valor = st.session_state.get("pre_calc_valor_parcela", 0.0)
        pre_data_primeira = st.session_state.get("pre_calc_data_primeira", date.today())

        # Converte boletos pra dict
        boletos_dict = [_boleto_para_dict(b) for b in pre_boletos]

        st.session_state[CHAVE_ESTADO] = {
            "passo_atual": 1,
            "rascunho_id": None,
            # Cliente VAZIO (usuário precisa preencher)
            "cliente_nome": "",
            "cliente_cnpj": "",
            "cliente_contato": "",
            "cliente_email": "",
            "cliente_telefone": "",
            "cliente_tem_whatsapp": False,
            "negociador_id": usuario.id,
            # Já vem com títulos
            "boletos_dict": boletos_dict,
            # Parâmetros financeiros preenchidos
            "pct_juros_titulos": float(pre_juros),
            "pct_multa_titulos": float(pre_multa),
            "pct_juros_mora": float(pre_juros_mora),
            "pct_multa_mora": float(pre_multa_mora),
            "pct_desconto": float(pre_desconto),
            "data_acordo": pre_data_acordo.isoformat() if hasattr(pre_data_acordo, "isoformat") else str(pre_data_acordo),
            # Parcelamento preenchido
            "tipo_cobranca": pre_tipo,
            "periodicidade": pre_periodicidade,
            "intervalo_personalizado_dias": int(pre_intervalo),
            "modo_parcelamento": pre_modo,
            "qtd_parcelas": int(pre_qtd),
            "valor_parcela": float(pre_valor),
            "data_primeira_parcela": pre_data_primeira.isoformat() if hasattr(pre_data_primeira, "isoformat") else str(pre_data_primeira),
            # Vazios
            "boletos_calculados": [],
            "parcelas_calculadas": [],
            "observacoes": "",
            "justificativa_aprovacao": "",
        }

        # Limpa flags do session_state pra não reaplicar
        for k in list(st.session_state.keys()):
            if k.startswith("pre_calc_"):
                del st.session_state[k]
        return

    # 3) Estado vazio (caminho padrão)
    st.session_state[CHAVE_ESTADO] = {
        "passo_atual": 1,
        "rascunho_id": None,
        # Passo 1
        "cliente_nome": "",
        "cliente_cnpj": "",
        "cliente_contato": "",
        "cliente_email": "",
        "cliente_telefone": "",
        "cliente_tem_whatsapp": False,
        "negociador_id": usuario.id,
        # Passo 2 — boletos importados (lista de dicts pra serializar)
        "boletos_dict": [],
        # Passo 3
        "pct_juros_titulos": 8.0,
        "pct_multa_titulos": 2.0,
        "pct_juros_mora": 5.0,
        "pct_multa_mora": 2.0,
        "data_acordo": date.today().isoformat(),
        # Desconto
        "pct_desconto": 0.0,
        # Passo 5
        "tipo_cobranca": "BOLETO",
        "periodicidade": "MENSAL",
        "intervalo_personalizado_dias": 1,
        "modo_parcelamento": "QTD",  # "QTD" ou "VALOR"
        "qtd_parcelas": 12,
        "valor_parcela": 0.0,
        "data_primeira_parcela": date.today().isoformat(),
        # Passo 6 — resultado calculado
        "boletos_calculados": [],
        "parcelas_calculadas": [],
        # Outros
        "observacoes": "",
        "justificativa_aprovacao": "",
    }


def _stepper(passo_atual: int):
    """Visualização dos 7 passos."""
    passos = [
        "Identificação", "Upload", "Parâmetros", "Calculadora",
        "Parcelamento", "Preview", "Confirmar",
    ]
    cols = st.columns(len(passos))
    for i, nome in enumerate(passos, start=1):
        bg = AZUL_ESCURO if i <= passo_atual else "#E9ECEF"
        cor = "white" if i <= passo_atual else "#666"
        with cols[i - 1]:
            st.markdown(
                f"""
<div style="background:{bg}; color:{cor};
            padding:8px; text-align:center;
            border-radius:6px; font-size:11px;
            font-weight:{'700' if i == passo_atual else '500'};">
    {i}. {nome}
</div>
                """,
                unsafe_allow_html=True,
            )


def _navegacao(usuario, mostrar_voltar: bool = True, mostrar_avancar: bool = True,
               label_avancar: str = "Avançar →", pode_avancar: bool = True,
               on_avancar=None):
    """Rodapé com botões Voltar / Avançar / Salvar rascunho."""
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if mostrar_voltar and estado["passo_atual"] > 1:
            if st.button("← Voltar", use_container_width=True):
                estado["passo_atual"] -= 1
                st.rerun()
    with col2:
        if mostrar_avancar:
            avancar = st.button(
                label_avancar,
                type="primary",
                use_container_width=True,
                disabled=not pode_avancar,
            )
            if avancar:
                if on_avancar:
                    if on_avancar() is False:
                        return
                if estado["passo_atual"] < 7:
                    estado["passo_atual"] += 1
                    st.rerun()
    with col3:
        col_sr, col_dc = st.columns(2)
        with col_sr:
            if st.button("💾 Salvar Rascunho", use_container_width=True):
                _salvar_rascunho(usuario)
        with col_dc:
            if st.button("❌ Descartar", use_container_width=True):
                _descartar_wizard()


def _salvar_rascunho(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    titulo = estado.get("cliente_nome") or f"Rascunho de {usuario.nome}"
    try:
        rascunho_id = repos_auxiliares.salvar_rascunho(
            usuario_id=usuario.id,
            titulo=titulo,
            passo_atual=estado["passo_atual"],
            estado=estado,
            rascunho_id=estado.get("rascunho_id"),
        )
        estado["rascunho_id"] = rascunho_id
        st.toast("✅ Rascunho salvo!", icon="✅")
        st.success(f"✅ Rascunho salvo! Você pode retomá-lo na tela Início.")
    except Exception as e:
        st.error(f"❌ Erro ao salvar rascunho: {e}")
        st.exception(e)


def _descartar_wizard():
    if CHAVE_ESTADO in st.session_state:
        del st.session_state[CHAVE_ESTADO]
    if "rascunho_id" in st.session_state:
        del st.session_state["rascunho_id"]
    st.rerun()


# ============================================================
# PASSOS
# ============================================================

def _passo_1_identificacao(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 1. Identificação do cliente e negociador")

    col1, col2 = st.columns(2)
    with col1:
        estado["cliente_nome"] = st.text_input(
            "Razão Social do cliente *",
            value=estado["cliente_nome"],
            placeholder="Ex: LLE Ferragens LTDA",
        )
        estado["cliente_cnpj"] = st.text_input(
            "CNPJ", value=estado["cliente_cnpj"], placeholder="00.000.000/0001-00",
        )
        estado["cliente_contato"] = st.text_input(
            "Contato", value=estado["cliente_contato"], placeholder="Nome do responsável",
        )
    with col2:
        estado["cliente_email"] = st.text_input(
            "E-mail de cobrança", value=estado["cliente_email"],
        )
        col_tel, col_wpp = st.columns([3, 1])
        with col_tel:
            estado["cliente_telefone"] = st.text_input(
                "Telefone", value=estado["cliente_telefone"], placeholder="(21) 99999-9999",
            )
        with col_wpp:
            # Espaçador pra alinhar com o text_input
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            estado["cliente_tem_whatsapp"] = st.checkbox(
                "📱 WhatsApp",
                value=estado.get("cliente_tem_whatsapp", False),
                help="Marque se o telefone também é WhatsApp",
            )

        # Negociador (dropdown - Seção 24)
        from src.utils.cache import listar_negociadores_ativos_cached
        negs = listar_negociadores_ativos_cached()
        opcoes = {n["id"]: n["nome"] for n in negs}
        if estado["negociador_id"] not in opcoes:
            estado["negociador_id"] = usuario.id if usuario.id in opcoes else (negs[0]["id"] if negs else None)
        if opcoes:
            estado["negociador_id"] = st.selectbox(
                "Negociador *",
                options=list(opcoes.keys()),
                format_func=lambda i: opcoes.get(i, "?"),
                index=list(opcoes.keys()).index(estado["negociador_id"])
                if estado["negociador_id"] in opcoes else 0,
            )

    pode_avancar = bool(estado["cliente_nome"].strip()) and estado["negociador_id"] is not None
    if not pode_avancar:
        st.caption("⚠ Preencha Razão Social e selecione um Negociador para avançar.")

    _navegacao(usuario, mostrar_voltar=False, pode_avancar=pode_avancar)


def _passo_2_upload(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 2. Upload dos títulos (.xlsx)")
    st.caption(
        "O arquivo deve seguir o padrão LLE. Veja na aba 'Template' como deve estar estruturado."
    )

    tab_up, tab_tpl, tab_atual = st.tabs(["📤 Enviar", "📋 Template", "📑 Atuais"])

    st.caption(
        "O arquivo deve seguir o padrão LLE. Veja na aba 'Template' como deve estar estruturado. "
        "Pode adicionar **vários arquivos** se for um grupo econômico — cada arquivo é um cliente diferente."
    )

    tab_up, tab_tpl, tab_atual = st.tabs(["📤 Enviar", "📋 Template", "📑 Atuais"])

    with tab_up:
        # Lista de arquivos importados na sessão (acumulativa)
        if "wiz_arquivos_importados" not in st.session_state:
            st.session_state["wiz_arquivos_importados"] = []

        arquivos_imp = st.session_state["wiz_arquivos_importados"]

        # Quantos uploaders mostrar? Pelo menos 1, mais se usuário pediu
        qtd_slots = max(1, st.session_state.get("wiz_qtd_slots_upload", 1))

        for i in range(qtd_slots):
            chave = f"wiz_upload_{i}"
            arq = st.file_uploader(
                f"Arquivo {i+1}",
                type=["xls", "xlsx"],
                key=chave,
            )
            if arq:
                # Já processado nesta sessão? evita reprocessamento
                ja_processado = any(
                    a.get("chave_uploader") == chave for a in arquivos_imp
                )
                if not ja_processado:
                    bytes_arq = arq.read()
                    res = importar_xlsx_titulos(bytes_arq, arq.name)
                    arquivos_imp.append({
                        "chave_uploader": chave,
                        "nome": arq.name,
                        "boletos": [_boleto_para_dict(b) for b in res.boletos] if res.boletos else [],
                        "erros_bloqueantes": res.tem_erros_bloqueantes,
                        "feedback": res,
                    })

        # Mostra feedback de cada arquivo importado
        if arquivos_imp:
            for idx, a in enumerate(arquivos_imp):
                with st.expander(
                    f"📄 {a['nome']} · {len(a['boletos'])} título(s)",
                    expanded=False,
                ):
                    if a.get("feedback") is not None:
                        from src.telas.calculadora import _mostrar_feedback_upload
                        _mostrar_feedback_upload(a["feedback"])
                    else:
                        st.success(f"✅ {len(a['boletos'])} título(s) carregados do cadastro do cliente.")

        # Botão "+ Adicionar outro arquivo"
        col_add, col_lim = st.columns([2, 2])
        with col_add:
            if st.button("➕ Adicionar outro arquivo", use_container_width=True):
                st.session_state["wiz_qtd_slots_upload"] = qtd_slots + 1
                st.rerun()
        with col_lim:
            if arquivos_imp:
                if st.button(
                    "🗑 Limpar todos os arquivos",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state["wiz_arquivos_importados"] = []
                    st.session_state["wiz_qtd_slots_upload"] = 1
                    # Limpar uploaders também
                    for i in range(qtd_slots):
                        if f"wiz_upload_{i}" in st.session_state:
                            del st.session_state[f"wiz_upload_{i}"]
                    estado["boletos_dict"] = []
                    st.rerun()

        # Consolidar todos os boletos no estado
        if arquivos_imp:
            todos_boletos = []
            for a in arquivos_imp:
                if not a.get("erros_bloqueantes"):
                    todos_boletos.extend(a["boletos"])

            # SELEÇÃO DE TÍTULOS (Erick - 13/05/2026)
            # Cada título tem um id único (numero_unico). Por padrão tudo marcado.
            # Usuário pode desmarcar os que NÃO quer negociar.
            chave_sel = "wiz_titulos_selecionados"
            if chave_sel not in st.session_state:
                # Inicializa marcando TODOS por padrão
                st.session_state[chave_sel] = {
                    b["numero_unico"]: True for b in todos_boletos
                }
            else:
                # Sincroniza com novos títulos importados (mantém o que já tinha)
                for b in todos_boletos:
                    if b["numero_unico"] not in st.session_state[chave_sel]:
                        st.session_state[chave_sel][b["numero_unico"]] = True

            # Limpa entradas de títulos que sumiram
            ids_atuais = {b["numero_unico"] for b in todos_boletos}
            st.session_state[chave_sel] = {
                k: v for k, v in st.session_state[chave_sel].items()
                if k in ids_atuais
            }

            sel = st.session_state[chave_sel]
            qtd_selecionados = sum(1 for v in sel.values() if v)
            total_selecionado = sum(
                b["principal"] for b in todos_boletos
                if sel.get(b["numero_unico"], False)
            )

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(
                f"<h4 style='color:{AZUL_ESCURO}; margin-bottom:6px;'>"
                f"📋 Selecione os títulos que serão negociados</h4>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Por padrão, todos os títulos vêm marcados. Desmarque os que "
                "você NÃO quer incluir no acordo."
            )

            # Header: marcar/desmarcar todos + resumo
            col_acoes, col_resumo = st.columns([2, 3])
            with col_acoes:
                ca, cb = st.columns(2)
                with ca:
                    if st.button("☑ Marcar todos", use_container_width=True, key="wiz_marcar_todos"):
                        for b in todos_boletos:
                            num_unico = b["numero_unico"]
                            st.session_state[chave_sel][num_unico] = True
                            # Apaga a key do widget pra forçar reconstrução com o novo valor
                            widget_key = f"wiz_chk_{num_unico}"
                            if widget_key in st.session_state:
                                del st.session_state[widget_key]
                        st.rerun()
                with cb:
                    if st.button("☐ Desmarcar todos", use_container_width=True, key="wiz_desmarcar_todos"):
                        for b in todos_boletos:
                            num_unico = b["numero_unico"]
                            st.session_state[chave_sel][num_unico] = False
                            widget_key = f"wiz_chk_{num_unico}"
                            if widget_key in st.session_state:
                                del st.session_state[widget_key]
                        st.rerun()
            with col_resumo:
                cor_resumo = VERDE if qtd_selecionados > 0 else "#DC3545"
                st.markdown(
                    f"<div style='text-align:right; padding-top:6px;'>"
                    f"<b style='color:{cor_resumo}; font-size:15px;'>"
                    f"{qtd_selecionados} de {len(todos_boletos)} título(s) marcados</b><br>"
                    f"<span style='font-size:13px; color:#444;'>"
                    f"Total selecionado: <b>{formatar_brl(total_selecionado)}</b>"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

            # Lista de checkboxes (renderiza em scroll se muitos)
            from src.utils.formatadores import formatar_data as _fd
            container = st.container(height=400 if len(todos_boletos) > 8 else None)
            with container:
                for idx, b in enumerate(todos_boletos):
                    num_unico = b["numero_unico"]
                    venc_str = _fd(b["vencimento"]) if b.get("vencimento") else "—"

                    col_chk, col_info, col_val = st.columns([0.5, 5, 2])
                    with col_chk:
                        marcado = st.checkbox(
                            " ",
                            value=sel.get(num_unico, True),
                            key=f"wiz_chk_{num_unico}",
                            label_visibility="collapsed",
                        )
                        st.session_state[chave_sel][num_unico] = marcado
                    with col_info:
                        cor_linha = "#222" if marcado else "#999"
                        st.markdown(
                            f"<div style='color:{cor_linha}; font-size:13px; "
                            f"padding-top:4px;'>"
                            f"<b>{b['codigo_parceiro']}</b> · "
                            f"{b['razao_social_parceiro'][:40]}<br>"
                            f"<span style='font-size:11px;'>"
                            f"Venc: {venc_str} · Nota {b['numero_nota']} · "
                            f"Único {num_unico} · "
                            f"Emp {b['empresa']}"
                            f"</span></div>",
                            unsafe_allow_html=True,
                        )
                    with col_val:
                        cor_linha = AZUL_ESCURO if marcado else "#999"
                        st.markdown(
                            f"<div style='text-align:right; color:{cor_linha}; "
                            f"font-weight:700; padding-top:8px;'>"
                            f"{formatar_brl(b['principal'])}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        "<hr style='margin:2px 0; border-color:#EEE;'>",
                        unsafe_allow_html=True,
                    )

            # FILTRA: só os marcados vão pro estado (usado no resto do wizard)
            boletos_selecionados = [
                b for b in todos_boletos
                if st.session_state[chave_sel].get(b["numero_unico"], False)
            ]
            estado["boletos_dict"] = boletos_selecionados

            # Aviso visual discreto se nenhum estiver marcado (sem bloquear nem ser
            # alarmista — o botão Avançar já fica desabilitado naturalmente).
            # Validação real fica no botão de finalizar.

            # Detectar parceiros distintos (no Sankhya, cada cód parceiro = 1 CNPJ)
            codigos_parceiro = set()
            clientes_por_codigo = {}
            for b in todos_boletos:
                cod = b.get("codigo_parceiro") or ""
                if cod:
                    codigos_parceiro.add(cod)
                    if cod not in clientes_por_codigo:
                        clientes_por_codigo[cod] = b.get("razao_social_parceiro", "?")

            arquivos_validos = [a for a in arquivos_imp if not a.get("erros_bloqueantes")]
            st.markdown("<br>", unsafe_allow_html=True)
            st.success(
                f"✅ **{len(arquivos_validos)} arquivo(s)** importado(s) · "
                f"**{len(todos_boletos)} título(s)** no total"
            )

            if len(codigos_parceiro) > 1:
                st.info(
                    f"🏢 **GRUPO ECONÔMICO detectado** — {len(codigos_parceiro)} parceiros diferentes:"
                )

                # Lista candidatos pro cliente principal do acordo
                opcoes_principais = list(clientes_por_codigo.items())
                opcoes_labels = ["Não usar nenhum (manter o que digitei no Passo 1)"] + [
                    f"{nome} — Cód {cod}"
                    for cod, nome in opcoes_principais
                ]
                idx_sel = st.selectbox(
                    "💡 Quer usar um desses como cliente principal do acordo? "
                    "(você pode voltar ao Passo 1 pra ajustar manualmente também)",
                    options=range(len(opcoes_labels)),
                    format_func=lambda i: opcoes_labels[i],
                    key="wiz_escolha_principal",
                )
                if idx_sel > 0:
                    cod_esc, nome_esc = opcoes_principais[idx_sel - 1]
                    if estado.get("cliente_nome") != nome_esc:
                        if st.button(
                            f"📝 Atualizar Passo 1 com '{nome_esc}'",
                            type="primary", use_container_width=True,
                        ):
                            estado["cliente_nome"] = nome_esc
                            st.success(
                                f"✓ Cliente principal atualizado: {nome_esc}. "
                                f"Você pode voltar ao Passo 1 pra preencher CNPJ e telefone."
                            )
                            st.rerun()
                else:
                    for cod, nome in clientes_por_codigo.items():
                        st.caption(f"  • {nome} — Cód parceiro {cod}")

    with tab_tpl:
        st.download_button(
            "📥 Baixar template .xlsx",
            data=gerar_template_xlsx(),
            file_name="template_titulos_lle.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tab_atual:
        if estado["boletos_dict"]:
            # Verifica se vieram pré-carregados do perfil do cliente
            arquivos_imp_atual = st.session_state.get("wiz_arquivos_importados", [])
            tem_pre = any(a.get("chave_uploader") == "pre_titulos_cliente" for a in arquivos_imp_atual)
            if tem_pre:
                st.success(
                    f"✅ **{len(estado['boletos_dict'])} título(s)** carregados automaticamente "
                    f"do cadastro do cliente. Você pode adicionar mais arquivos na aba 'Enviar' "
                    f"ou prosseguir com estes."
                )

            df = pd.DataFrame([
                {
                    "Cód Parc": b["codigo_parceiro"],
                    "Razão": b["razao_social_parceiro"],
                    "Emp": b["empresa"],
                    "Vendedor": b["nome_vendedor"],
                    "Vencimento": b["vencimento"],
                    "Nota": b["numero_nota"],
                    "Único": b["numero_unico"],
                    "Principal": formatar_brl(b["principal"]),
                }
                for b in estado["boletos_dict"]
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
            total = sum(b["principal"] for b in estado["boletos_dict"])
            st.markdown(f"**Total Principal: {formatar_brl(total)}** · {len(estado['boletos_dict'])} títulos")
            if st.button("🗑 Limpar títulos", type="secondary", key="btn_limpar_atuais"):
                estado["boletos_dict"] = []
                st.session_state["wiz_arquivos_importados"] = []
                st.session_state["wiz_qtd_slots_upload"] = 1
                if "wiz_titulos_selecionados" in st.session_state:
                    del st.session_state["wiz_titulos_selecionados"]
                st.rerun()
        else:
            st.caption("Nenhum título carregado ainda. Use a aba '📤 Enviar' para importar um arquivo.")

    pode_avancar = len(estado["boletos_dict"]) > 0
    _navegacao(usuario, pode_avancar=pode_avancar)


def _passo_3_parametros(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 3. Parâmetros financeiros")
    st.caption(
        "Os 4 percentuais abaixo são INDEPENDENTES: os dois primeiros se aplicam "
        "aos títulos no momento de criar o acordo (CASO 1); os dois últimos se "
        "aplicam se uma parcela atrasar (CASO 2)."
    )

    col_d, _ = st.columns([1, 2])
    with col_d:
        d_acordo = st.date_input(
            "Data do acordo",
            value=datetime.fromisoformat(estado["data_acordo"]).date(),
            format="DD/MM/YYYY",
        )
        estado["data_acordo"] = d_acordo.isoformat()

    st.markdown("**Juros e multa dos TÍTULOS (CASO 1)**")
    c1, c2 = st.columns(2)
    with c1:
        estado["pct_juros_titulos"] = st.number_input(
            "% Juros ao mês dos títulos",
            min_value=0.0, max_value=50.0, value=float(estado["pct_juros_titulos"]),
            step=0.1, format="%.2f",
        )
    with c2:
        estado["pct_multa_titulos"] = st.number_input(
            "% Multa fixa dos títulos",
            min_value=0.0, max_value=50.0, value=float(estado["pct_multa_titulos"]),
            step=0.1, format="%.2f",
        )

    st.markdown("**Juros e multa de MORA (CASO 2 — quando uma parcela atrasa)**")
    c3, c4 = st.columns(2)
    with c3:
        estado["pct_juros_mora"] = st.number_input(
            "% Juros de mora ao mês",
            min_value=0.0, max_value=50.0, value=float(estado["pct_juros_mora"]),
            step=0.1, format="%.2f",
        )
    with c4:
        estado["pct_multa_mora"] = st.number_input(
            "% Multa de mora (fixa)",
            min_value=0.0, max_value=50.0, value=float(estado["pct_multa_mora"]),
            step=0.1, format="%.2f",
        )

    st.markdown("---")
    st.markdown("**Desconto sobre o valor principal**")
    st.caption(
        "Desconto aplicado diretamente sobre o principal dos títulos, antes do cálculo "
        "de juros e multa. Qualquer desconto acima de 0% exige aprovação do administrador."
    )
    col_desc, col_desc_info = st.columns([1, 2])
    with col_desc:
        pct_desconto = st.number_input(
            "% Desconto sobre o principal",
            min_value=0.0, max_value=100.0,
            value=float(estado.get("pct_desconto", 0.0)),
            step=0.5, format="%.2f",
            help="0% = sem desconto. Qualquer valor acima exige aprovação do admin.",
        )
        estado["pct_desconto"] = pct_desconto
    with col_desc_info:
        if pct_desconto > 0:
            total_principal = sum(b["principal"] for b in estado.get("boletos_dict", []))
            valor_desconto = total_principal * pct_desconto / 100
            principal_com_desconto = total_principal - valor_desconto
            st.markdown(
                f"<div style='background:#FFF3CD; border-left:4px solid #FAC318; "
                f"padding:12px; border-radius:6px; margin-top:4px;'>"
                f"<b>⚠ Requer aprovação do administrador</b><br>"
                f"Principal original: <b>{formatar_brl(total_principal)}</b><br>"
                f"Desconto ({pct_desconto:.2f}%): <b style='color:#DC3545;'>- {formatar_brl(valor_desconto)}</b><br>"
                f"Principal com desconto: <b style='color:#0F8C3B;'>{formatar_brl(principal_com_desconto)}</b>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("Sem desconto aplicado.")

    _navegacao(usuario)


def _passo_4_calculadora(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 4. Preview com juros e multa (CASO 1)")

    boletos = [_dict_para_boleto(d) for d in estado["boletos_dict"]]
    data_acordo = datetime.fromisoformat(estado["data_acordo"]).date()
    pct_juros = estado["pct_juros_titulos"]
    pct_multa = estado["pct_multa_titulos"]
    pct_desconto = float(estado.get("pct_desconto", 0.0))

    # Aplica desconto sobre o principal antes do cálculo de juros
    if pct_desconto > 0:
        for b in boletos:
            b.principal = round(b.principal * (1 - pct_desconto / 100), 2)
        st.info(f"💡 Desconto de **{pct_desconto:.2f}%** aplicado sobre o principal dos títulos.")

    # Aplica CASO 1 com data_acordo como aproximação (refinamento real é no passo 6)
    for b in boletos:
        calcular_boleto_caso1(b, data_acordo, pct_juros, pct_multa, data_acordo)

    rows = []
    for b in boletos:
        rows.append({
            "Cód Parc": b.codigo_parceiro,
            "Razão": b.razao_social_parceiro,
            "Emp": int(b.empresa),
            "Vencimento": formatar_data(b.vencimento),
            "Atraso (d)": b.dias_atraso,
            "Principal": formatar_brl(b.principal),
            "Juros": formatar_brl(b.juros),
            "Multa": formatar_brl(b.multa),
            "Total": formatar_brl(b.total),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    t_p = sum(b.principal for b in boletos)
    t_j = sum(b.juros for b in boletos)
    t_m = sum(b.multa for b in boletos)
    t_t = sum(b.total for b in boletos)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Principal", formatar_brl(t_p))
    c2.metric("Juros (estimativa)", formatar_brl(t_j))
    c3.metric("Multa", formatar_brl(t_m))
    c4.metric("Total", formatar_brl(t_t))

    st.info(
        "💡 No próximo passo você configura o parcelamento. O cálculo dos juros "
        "será refinado iterativamente: cada título terá seu juros recalculado até "
        "a data exata da parcela que o quita."
    )

    _navegacao(usuario)


def _passo_5_parcelamento(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 5. Configuração do parcelamento")

    col1, col2 = st.columns(2)
    with col1:
        tipo = st.selectbox(
            "Tipo de cobrança", options=["BOLETO", "PIX"],
            index=["BOLETO", "PIX"].index(estado["tipo_cobranca"]),
        )
        estado["tipo_cobranca"] = tipo

        periodicidade = st.selectbox(
            "Periodicidade",
            options=["MENSAL", "QUINZENAL", "SEMANAL", "PERSONALIZADA"],
            index=["MENSAL", "QUINZENAL", "SEMANAL", "PERSONALIZADA"].index(estado["periodicidade"]),
        )
        estado["periodicidade"] = periodicidade

        if periodicidade == "PERSONALIZADA":
            estado["intervalo_personalizado_dias"] = st.number_input(
                "A cada quantos dias?",
                min_value=1, max_value=365,
                value=int(estado["intervalo_personalizado_dias"]),
            )

        d_primeira = st.date_input(
            "Data do primeiro pagamento",
            value=datetime.fromisoformat(estado["data_primeira_parcela"]).date(),
            format="DD/MM/YYYY",
        )
        estado["data_primeira_parcela"] = d_primeira.isoformat()

    with col2:
        # 3 modos disponíveis
        opcoes_modo = ["Quantidade de parcelas", "Valor da parcela", "Personalizado (Qtd + Valor)"]
        modo_atual = estado.get("modo_parcelamento", "QTD")
        idx_default = {"QTD": 0, "VALOR": 1, "LIVRE": 2}.get(modo_atual, 0)

        modo = st.radio(
            "Definir parcelamento por:",
            options=opcoes_modo,
            index=idx_default,
            horizontal=True,
        )
        if modo.startswith("Quantidade"):
            estado["modo_parcelamento"] = "QTD"
        elif modo.startswith("Valor"):
            estado["modo_parcelamento"] = "VALOR"
        else:
            estado["modo_parcelamento"] = "LIVRE"

        if estado["modo_parcelamento"] == "QTD":
            estado["qtd_parcelas"] = st.number_input(
                "Quantidade de parcelas",
                min_value=1, max_value=240,
                value=int(estado["qtd_parcelas"]),
            )
        elif estado["modo_parcelamento"] == "VALOR":
            estado["valor_parcela"] = st.number_input(
                "Valor de cada parcela (R$)",
                min_value=0.01, value=float(estado["valor_parcela"] or 2400.0),
                step=100.0, format="%.2f",
            )
        else:  # LIVRE
            st.caption(
                "💡 **Modo livre:** o total pode ultrapassar a dívida calculada com juros."
            )
            estado["qtd_parcelas"] = st.number_input(
                "Quantidade de parcelas",
                min_value=1, max_value=240,
                value=int(estado["qtd_parcelas"]),
                key="wiz_qtd_livre",
            )
            estado["valor_parcela"] = st.number_input(
                "Valor de cada parcela (R$)",
                min_value=0.01, value=float(estado["valor_parcela"] or 2400.0),
                step=100.0, format="%.2f",
                key="wiz_valor_livre",
            )

    # Validação de aprovação (P5) — desconto também exige aprovação
    aviso = _verificar_necessidade_aprovacao(estado)
    if aviso:
        st.warning(f"⚠ {aviso}")
        estado["precisa_aprovacao"] = True
    elif float(estado.get("pct_desconto", 0.0)) > 0:
        st.warning(
            f"⚠ Desconto de **{estado['pct_desconto']:.2f}%** aplicado — "
            f"este acordo requer aprovação do administrador."
        )
        estado["precisa_aprovacao"] = True
    else:
        estado["precisa_aprovacao"] = False

    _navegacao(usuario)


def _passo_6_preview(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 6. Preview do cronograma")

    # Calcula tudo com FIFO + refinamento
    boletos = [_dict_para_boleto(d) for d in estado["boletos_dict"]]
    data_acordo = datetime.fromisoformat(estado["data_acordo"]).date()
    data_primeira = datetime.fromisoformat(estado["data_primeira_parcela"]).date()

    # Aplica desconto sobre o principal antes do FIFO
    pct_desconto = float(estado.get("pct_desconto", 0.0))
    if pct_desconto > 0:
        for b in boletos:
            b.principal = round(b.principal * (1 - pct_desconto / 100), 2)
        st.info(f"💡 Desconto de **{pct_desconto:.2f}%** aplicado sobre o principal.")

    try:
        if estado["modo_parcelamento"] == "QTD":
            parcelas = montar_acordo_qtd_fixa(
                boletos=boletos,
                data_acordo=data_acordo,
                pct_juros_mes=estado["pct_juros_titulos"],
                pct_multa=estado["pct_multa_titulos"],
                qtd_parcelas=int(estado["qtd_parcelas"]),
                data_primeira_parcela=data_primeira,
                periodicidade=Periodicidade(estado["periodicidade"]),
                intervalo_personalizado_dias=int(estado["intervalo_personalizado_dias"]),
            )
        elif estado["modo_parcelamento"] == "VALOR":
            parcelas = montar_acordo_valor_fixo(
                boletos=boletos,
                data_acordo=data_acordo,
                pct_juros_mes=estado["pct_juros_titulos"],
                pct_multa=estado["pct_multa_titulos"],
                valor_parcela=float(estado["valor_parcela"]),
                data_primeira_parcela=data_primeira,
                periodicidade=Periodicidade(estado["periodicidade"]),
                intervalo_personalizado_dias=int(estado["intervalo_personalizado_dias"]),
            )
        else:  # LIVRE
            from src.servicos.fifo import montar_acordo_qtd_e_valor_livre
            parcelas = montar_acordo_qtd_e_valor_livre(
                boletos=boletos,
                data_acordo=data_acordo,
                pct_juros_mes=estado["pct_juros_titulos"],
                pct_multa=estado["pct_multa_titulos"],
                qtd_parcelas=int(estado["qtd_parcelas"]),
                valor_parcela=float(estado["valor_parcela"]),
                data_primeira_parcela=data_primeira,
                periodicidade=Periodicidade(estado["periodicidade"]),
                intervalo_personalizado_dias=int(estado["intervalo_personalizado_dias"]),
            )
    except Exception as e:
        st.error(f"Erro no cálculo: {e}")
        return

    # Valida consistência (no modo livre, pode ter diferença grande — aviso ao invés de erro)
    if estado["modo_parcelamento"] == "LIVRE":
        total_boletos = sum(b.total for b in boletos)
        total_parcelas = sum(p.valor_original for p in parcelas)
        if abs(total_parcelas - total_boletos) > 0.01:
            diff = total_parcelas - total_boletos
            if diff > 0:
                st.info(
                    f"💡 Modo livre: total das parcelas (R$ {total_parcelas:,.2f}) "
                    f"está R$ {diff:,.2f} **acima** do calculado com juros."
                )
            else:
                st.warning(
                    f"⚠️ Modo livre: total das parcelas (R$ {total_parcelas:,.2f}) "
                    f"está R$ {abs(diff):,.2f} **abaixo** do calculado — vai sobrar saldo nos boletos."
                )

    # Valida consistência
    erros = validar_consistencia(boletos, parcelas, tolerancia=0.05)
    if erros:
        st.warning(
            "⚠ Foram detectadas inconsistências de centavos no cálculo (normais por "
            "arredondamento, mas vou listar abaixo):\n" + "\n".join(f"- {e}" for e in erros)
        )

    # Tabela de parcelas
    rows = []
    for p in parcelas:
        rows.append({
            "Nº": p.numero,
            "Vencimento": formatar_data(p.vencimento_atual),
            "Valor": formatar_brl(p.valor_original),
            "Saldo": formatar_brl(p.saldo_apos),
            "Principal": formatar_brl(p.principal),
            "Juros": formatar_brl(p.juros),
            "Multa": formatar_brl(p.multa),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    total_geral = sum(p.valor_original for p in parcelas)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total a parcelar", formatar_brl(total_geral))
    c2.metric("Nº de parcelas", str(len(parcelas)))
    c3.metric("Valor médio", formatar_brl(total_geral / len(parcelas)) if parcelas else "—")

    # Guarda no estado
    estado["boletos_calculados"] = [_boleto_para_dict(b) for b in boletos]
    estado["parcelas_calculadas"] = [_parcela_para_dict(p) for p in parcelas]

    _navegacao(usuario)


def _passo_7_confirmar(usuario):
    estado = st.session_state[CHAVE_ESTADO]
    st.markdown("### 7. Revisão e confirmação")

    qtd_p = len(estado["parcelas_calculadas"])
    total = sum(p["valor_original"] for p in estado["parcelas_calculadas"])

    st.markdown(
        f"""
        - **Cliente:** {estado['cliente_nome']}
        - **Negociador:** {repo_usuario.buscar_por_id(estado['negociador_id']).nome if estado.get('negociador_id') else '—'}
        - **Títulos:** {len(estado['boletos_calculados'])}
        - **Desconto aplicado:** {estado.get('pct_desconto', 0.0):.2f}% {"⚠ Requer aprovação" if estado.get('pct_desconto', 0.0) > 0 else "✓ Sem desconto"}
        - **Parcelas:** {qtd_p}
        - **Valor total:** {formatar_brl(total)}
        - **Cobrança:** {estado['tipo_cobranca']} · **Periodicidade:** {estado['periodicidade']}
        - **Data 1ª parcela:** {formatar_data(estado['data_primeira_parcela'])}
        """
    )

    estado["observacoes"] = st.text_area("Observações (opcional)", value=estado.get("observacoes", ""))

    # Fluxo P5: se precisa aprovação, mostra campo de justificativa
    if estado.get("precisa_aprovacao"):
        st.warning(
            "⚠ Esta configuração de parcelamento **requer aprovação de administrador** "
            "antes de virar acordo ATIVO. Escreva uma justificativa:"
        )
        estado["justificativa_aprovacao"] = st.text_area(
            "Justificativa para o admin",
            value=estado.get("justificativa_aprovacao", ""),
            height=100,
        )

    # ============ PROPOSTA DE ACORDO (PDF) ============
    st.markdown("---")
    st.markdown("### 📄 Proposta de Acordo")
    st.caption(
        "Antes de confirmar o acordo, você pode gerar uma **Proposta de Acordo** em PDF "
        "pra enviar ao cliente. A proposta NÃO formaliza o acordo — é só pra ele "
        "ver e aprovar antes de você clicar em 'Salvar Acordo'."
    )

    col_btn, _ = st.columns([2, 3])
    with col_btn:
        if st.button(
            "📥 Gerar Proposta de Acordo (PDF)",
            use_container_width=True,
            key="wizard_proposta_btn",
        ):
            with st.spinner("⏳ Processando..."):
                try:
                    from src.servicos.exportador_pdf import gerar_pdf_proposta_acordo
                    from src.utils.formatadores import slugificar
                    from datetime import datetime as _dt

                    # Monta as parcelas como objetos simples pra alimentar o PDF
                    class _ParcelaSimples:
                        pass
                    parcelas_pdf = []
                    for p_dict in estado["parcelas_calculadas"]:
                        p = _ParcelaSimples()
                        p.numero = p_dict["numero"]
                        p.vencimento_atual = date.fromisoformat(p_dict["vencimento_atual"]) if isinstance(p_dict["vencimento_atual"], str) else p_dict["vencimento_atual"]
                        p.valor_original = p_dict["valor_original"]
                        parcelas_pdf.append(p)

                    pdf_bytes = gerar_pdf_proposta_acordo(
                        cliente_nome=estado["cliente_nome"],
                        cliente_cnpj=estado.get("cliente_cnpj") or None,
                        cliente_endereco=None,
                        cliente_bairro=None,
                        cliente_cidade=None,
                        cliente_uf=None,
                        parcelas=parcelas_pdf,
                    )
                    st.session_state["wizard_proposta_pdf"] = pdf_bytes
                    st.session_state["wizard_proposta_nome"] = (
                        f"PropostaAcordo_{slugificar(estado['cliente_nome'])}_"
                        f"{_dt.now().strftime('%Y%m%d')}.pdf"
                    )
                except Exception as _e_acao:
                    st.error(f"❌ Erro: {type(_e_acao).__name__}: {_e_acao}")
                    with st.expander("🔍 Detalhes técnicos", expanded=False):
                        st.exception(_e_acao)

    if "wizard_proposta_pdf" in st.session_state:
        col_dl, _ = st.columns([2, 3])
        with col_dl:
            st.download_button(
                "⬇ Baixar Proposta de Acordo",
                data=st.session_state["wizard_proposta_pdf"],
                file_name=st.session_state["wizard_proposta_nome"],
                mime="application/pdf",
                use_container_width=True,
                key="wizard_proposta_dl",
            )

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("← Voltar", use_container_width=True):
            estado["passo_atual"] -= 1
            st.rerun()
    with col2:
        if st.button("💾 Salvar como Rascunho", use_container_width=True):
            _salvar_rascunho(usuario)
    with col3:
        rotulo = (
            "📝 Enviar para Aprovação" if estado.get("precisa_aprovacao")
            else "✅ Salvar Acordo"
        )
        # Trava anti-duplicação: se já tentou salvar, desabilita o botão
        ja_salvando = st.session_state.get("wizard_salvando", False)
        if st.button(
            rotulo,
            type="primary",
            use_container_width=True,
            disabled=ja_salvando,
            key="btn_salvar_acordo_final",
        ):
            # Marca a flag IMEDIATAMENTE — qualquer rerun depois disso
            # vai desabilitar o botão
            st.session_state["wizard_salvando"] = True
            # Limpa o PDF da proposta pra não ficar pendurado
            for k in ("wizard_proposta_pdf", "wizard_proposta_nome"):
                if k in st.session_state:
                    del st.session_state[k]
            try:
                _salvar_acordo_final(usuario)
            finally:
                # Limpa a flag (se chegou aqui sem switch_page, é erro)
                if "wizard_salvando" in st.session_state:
                    del st.session_state["wizard_salvando"]


# ============================================================
# REGRAS DE NEGÓCIO
# ============================================================

def _verificar_necessidade_aprovacao(estado) -> Optional[str]:
    """P5: regras de aprovação."""
    p = estado["periodicidade"]
    qtd = int(estado["qtd_parcelas"])
    if estado["modo_parcelamento"] == "VALOR":
        return None  # Em modo VALOR, qtd é calculada; aprovação depende de outras regras
    if p == "MENSAL":
        return "Periodicidade MENSAL sempre exige aprovação do administrador."
    if p == "QUINZENAL" and qtd > 20:
        return f"Quinzenal com {qtd} parcelas (>20) exige aprovação."
    if p == "SEMANAL" and qtd > 40:
        return f"Semanal com {qtd} parcelas (>40) exige aprovação."
    return None


def _salvar_acordo_final(usuario):
    estado = st.session_state[CHAVE_ESTADO]

    # VALIDAÇÕES CRÍTICAS antes de salvar (evita acordos "fantasma")
    nome_cliente = (estado.get("cliente_nome") or "").strip()
    if not nome_cliente:
        st.error("❌ Nome do cliente não pode estar vazio.")
        return

    boletos_dicts = estado.get("boletos_calculados") or []
    parcelas_dicts = estado.get("parcelas_calculadas") or []

    if not boletos_dicts:
        st.error(
            "❌ Nenhum boleto calculado. Volte ao Passo 6 (preview) "
            "pra recalcular antes de salvar."
        )
        return
    if not parcelas_dicts:
        st.error(
            "❌ Nenhuma parcela calculada. Volte ao Passo 6 (preview) "
            "pra recalcular antes de salvar."
        )
        return

    # Cria/encontra cliente
    cliente = repo_cliente.buscar_ou_criar(
        nome_principal=nome_cliente,
        cnpj=estado.get("cliente_cnpj") or None,
        contato=estado.get("cliente_contato") or None,
        email_cobranca=estado.get("cliente_email") or None,
        telefone=estado.get("cliente_telefone") or None,
        tem_whatsapp=estado.get("cliente_tem_whatsapp", False),
    )

    boletos = [_dict_para_boleto(d) for d in boletos_dicts]
    parcelas = [_dict_para_parcela(d) for d in parcelas_dicts]

    status_inicial = (
        StatusAcordo.PENDENTE_APROVACAO if estado.get("precisa_aprovacao")
        else StatusAcordo.ATIVO
    )

    try:
        acordo_id = salvar_acordo_completo(
            cliente_id=cliente.id,
            negociador_id=estado["negociador_id"],
            criado_por_id=usuario.id,
            data_acordo=datetime.fromisoformat(estado["data_acordo"]).date(),
            pct_juros_mes_titulos=estado["pct_juros_titulos"],
            pct_multa_titulos=estado["pct_multa_titulos"],
            pct_juros_mora_mes=estado["pct_juros_mora"],
            pct_multa_mora=estado["pct_multa_mora"],
            pct_desconto=float(estado.get("pct_desconto", 0.0)),
            tipo_cobranca=TipoCobranca(estado["tipo_cobranca"]),
            periodicidade=Periodicidade(estado["periodicidade"]),
            intervalo_personalizado_dias=int(estado["intervalo_personalizado_dias"]),
            boletos=boletos,
            parcelas=parcelas,
            status_inicial=status_inicial,
            observacoes=estado.get("observacoes") or None,
        )
    except Exception as e:
        st.error(f"❌ Erro ao salvar acordo: {e}")
        st.exception(e)
        return

    # Cria solicitação de aprovação se for o caso
    if status_inicial == StatusAcordo.PENDENTE_APROVACAO:
        repos_auxiliares.criar_solicitacao_aprovacao(
            acordo_id=acordo_id,
            solicitado_por_id=usuario.id,
            justificativa=estado.get("justificativa_aprovacao", "") or "Sem justificativa",
        )

    # Auditoria
    repos_auxiliares.registrar_log(
        usuario_id=usuario.id, usuario_nome=usuario.nome,
        acao="CRIAR_ACORDO", entidade="acordo", entidade_id=acordo_id,
        contexto=estado["cliente_nome"],
        depois={"status": status_inicial.value, "valor_total": sum(p.valor_original for p in parcelas)},
    )

    # Limpa rascunho se houver
    if estado.get("rascunho_id"):
        eh_admin = usuario.perfil == PerfilUsuario.ADMIN
        repos_auxiliares.excluir_rascunho(
            estado["rascunho_id"], usuario.id, eh_admin=eh_admin,
        )

    # Limpa estado COMPLETAMENTE (impede salvar duplicado)
    _descartar_wizard()

    # Marca acordo recém-criado pra mostrar mensagem no Início
    st.session_state["acordo_recem_criado"] = {
        "id": acordo_id,
        "numero_interno": None,  # será buscado no Início
        "cliente_nome": estado.get("cliente_nome", ""),
        "status": status_inicial.value,
    }

    # IMPORTANTE: redirecionar pro Início pra impedir o usuário de clicar
    # "Salvar" várias vezes (Erick - 13/05/2026, bug crítico de duplicação)
    st.success("✅ Acordo criado com sucesso! Redirecionando...")
    st.balloons()
    import time
    time.sleep(1.2)  # tempinho pra ver a mensagem
    st.switch_page("pages/1_🏠_Início.py")


# ============================================================
# SERIALIZAÇÃO (boletos/parcelas <-> dict)
# ============================================================

def _boleto_para_dict(b) -> dict:
    return {
        "codigo_parceiro": b.codigo_parceiro,
        "razao_social_parceiro": b.razao_social_parceiro,
        "empresa": int(b.empresa) if hasattr(b.empresa, "value") else int(b.empresa),
        "codigo_vendedor": b.codigo_vendedor,
        "nome_vendedor": b.nome_vendedor,
        "vencimento": b.vencimento.isoformat() if hasattr(b.vencimento, "isoformat") else b.vencimento,
        "numero_nota": b.numero_nota,
        "numero_unico": b.numero_unico,
        "principal": float(b.principal),
        "dias_atraso": int(b.dias_atraso),
        "fim_juros": b.fim_juros.isoformat() if b.fim_juros and hasattr(b.fim_juros, "isoformat") else None,
        "juros": float(b.juros),
        "multa": float(b.multa),
        "total": float(b.total),
        "parcelas_alocadas": list(b.parcelas_alocadas),
        "distribuicao": list(b.distribuicao),
    }


def _dict_para_boleto(d):
    from src.modelos.tipos import Boleto, Empresa, OrigemDado
    return Boleto(
        codigo_parceiro=d["codigo_parceiro"],
        razao_social_parceiro=d["razao_social_parceiro"],
        empresa=Empresa(int(d["empresa"])),
        codigo_vendedor=d["codigo_vendedor"],
        nome_vendedor=d["nome_vendedor"],
        vencimento=datetime.fromisoformat(d["vencimento"]).date()
            if isinstance(d["vencimento"], str) else d["vencimento"],
        numero_nota=d["numero_nota"],
        numero_unico=d["numero_unico"],
        principal=float(d["principal"]),
        dias_atraso=int(d.get("dias_atraso", 0)),
        fim_juros=(
            datetime.fromisoformat(d["fim_juros"]).date()
            if d.get("fim_juros") else date.today()
        ),
        juros=float(d.get("juros", 0.0)),
        multa=float(d.get("multa", 0.0)),
        total=float(d.get("total", 0.0)),
        parcelas_alocadas=list(d.get("parcelas_alocadas", [])),
        distribuicao=list(d.get("distribuicao", [])),
        origem=OrigemDado.MANUAL,
    )


def _parcela_para_dict(p) -> dict:
    return {
        "numero": p.numero,
        "vencimento_original": p.vencimento_original.isoformat(),
        "vencimento_atual": p.vencimento_atual.isoformat(),
        "valor_original": float(p.valor_original),
        "principal": float(p.principal),
        "juros": float(p.juros),
        "multa": float(p.multa),
        "saldo_apos": float(p.saldo_apos),
    }


def _dict_para_parcela(d):
    from src.modelos.tipos import Parcela, StatusParcela
    return Parcela(
        numero=int(d["numero"]),
        vencimento_original=datetime.fromisoformat(d["vencimento_original"]).date(),
        vencimento_atual=datetime.fromisoformat(d["vencimento_atual"]).date(),
        valor_original=float(d["valor_original"]),
        principal=float(d.get("principal", 0.0)),
        juros=float(d.get("juros", 0.0)),
        multa=float(d.get("multa", 0.0)),
        saldo_apos=float(d.get("saldo_apos", 0.0)),
        status=StatusParcela.EM_ABERTO,
    )
