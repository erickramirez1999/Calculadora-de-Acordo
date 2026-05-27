"""
Tela Clientes — Erick features 5 e 7:
  - Lista de clientes (cadastrados pelo sistema, com ou sem acordo)
  - Cadastrar novo cliente independente do acordo
  - Editar cliente
  - Ver histórico completo do cliente (todos acordos + métricas)
"""
from __future__ import annotations

import streamlit as st

from src.banco import repo_cliente, repo_extras, repos_auxiliares
from src.utils.formatadores import formatar_brl, formatar_data, normalizar_busca
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE
from src.utils.estilo import badge_status_acordo


def renderizar_clientes(usuario):
    # Detecta se já está vendo histórico de um cliente específico
    cliente_id_aberto = st.session_state.get("cliente_aberto_id")
    if cliente_id_aberto:
        _tela_historico_cliente(cliente_id_aberto, usuario)
        return

    # Detecta modo cadastro
    if st.session_state.get("modo_cadastro_cliente"):
        _form_novo_cliente(usuario)
        return

    # Lista padrão
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>🏢 Clientes</h1>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Cadastro completo dos clientes — independente de ter acordo ou não. "
        "Clique em um cliente pra ver o histórico de acordos."
    )

    col_busca, col_novo = st.columns([4, 1])
    with col_busca:
        termo = st.text_input(
            "🔍 Buscar por nome ou CNPJ",
            placeholder="LLE Ferragens, 12.345.678/0001...",
        )
    with col_novo:
        if st.button("➕ Novo cliente", type="primary", use_container_width=True):
            st.session_state["modo_cadastro_cliente"] = True
            st.rerun()

    clientes = repo_cliente.listar_todos()
    if termo.strip():
        t = normalizar_busca(termo)
        clientes = [
            c for c in clientes
            if t in normalizar_busca(c.nome_principal)
            or (c.cnpj and t in c.cnpj)
        ]

    if not clientes:
        st.info("Nenhum cliente cadastrado ainda. Clique em **+ Novo cliente** pra começar.")
        return

    st.markdown(f"**{len(clientes)} cliente(s)**")
    st.markdown("---")

    for c in clientes:
        metricas = repo_extras.metricas_cliente(c.id)
        wpp_label = " 📱" if c.tem_whatsapp else ""

        col_info, col_kpi1, col_kpi2, col_btn = st.columns([4, 1.2, 1.5, 1.2])
        with col_info:
            st.markdown(f"**{c.nome_principal}**")
            st.caption(
                f"{c.cnpj or 'sem CNPJ'} · {c.contato or 'sem contato'} · "
                f"{c.telefone or 'sem tel'}{wpp_label}"
            )
        with col_kpi1:
            st.markdown(f"**{metricas['total']}** acordos")
            st.caption(f"{metricas['ativos']} ativo(s)")
        with col_kpi2:
            st.markdown(f"**{formatar_brl(metricas['valor_total_negociado'])}**")
            st.caption("total negociado")
        with col_btn:
            if st.button("Ver histórico", key=f"hist_{c.id}", use_container_width=True):
                st.session_state["cliente_aberto_id"] = c.id
                st.rerun()
        st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)


def _form_novo_cliente(usuario):
    """Formulário pra cadastrar cliente novo (feature 5)."""
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>➕ Cadastrar Novo Cliente</h1>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Você pode cadastrar um cliente aqui mesmo sem precisar criar um acordo. "
        "Útil pra ter o cadastro pronto quando o acordo for criado depois."
    )

    with st.form("form_novo_cliente_indep"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Razão Social *", placeholder="Ex: LLE Ferragens LTDA")
            cnpj = st.text_input("CNPJ", placeholder="00.000.000/0001-00")
            contato = st.text_input("Contato (nome)")
        with col2:
            email = st.text_input("E-mail de cobrança")
            col_tel, col_wpp = st.columns([3, 1])
            with col_tel:
                telefone = st.text_input("Telefone", placeholder="(21) 99999-9999")
            with col_wpp:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                tem_wpp = st.checkbox("📱 WhatsApp")

        st.markdown("---")
        col_ok, col_x = st.columns(2)
        with col_ok:
            salvar = st.form_submit_button(
                "💾 Cadastrar cliente",
                type="primary",
                use_container_width=True,
            )
        with col_x:
            cancelar = st.form_submit_button("Cancelar", use_container_width=True)

        if salvar:
            if not nome.strip():
                st.error("❌ Razão Social é obrigatória.")
                return
            try:
                cliente = repo_cliente.criar(
                    nome_principal=nome,
                    cnpj=cnpj or None,
                    contato=contato or None,
                    email_cobranca=email or None,
                    telefone=telefone or None,
                    tem_whatsapp=tem_wpp,
                )
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                    acao="CRIAR_CLIENTE_INDEPENDENTE",
                    entidade="cliente", entidade_id=cliente.id,
                    contexto=cliente.nome_principal,
                )
                del st.session_state["modo_cadastro_cliente"]
                st.success(f"✓ Cliente {cliente.nome_principal} cadastrado!")
                st.rerun()
            except ValueError as e:
                st.error(f"❌ {e}")

        if cancelar:
            del st.session_state["modo_cadastro_cliente"]
            st.rerun()


def _tela_historico_cliente(cliente_id: int, usuario):
    """Histórico completo do cliente: todos os acordos + KPIs (feature 7)."""
    cliente = repo_cliente.buscar_por_id(cliente_id)
    if cliente is None:
        st.error("Cliente não encontrado.")
        if st.button("← Voltar"):
            del st.session_state["cliente_aberto_id"]
            st.rerun()
        return

    # Aviso de proposta aceita (vindo do dashboard)
    aviso = st.session_state.pop("proposta_aceita_aviso", None)
    if aviso:
        st.success(
            f"✅ Proposta aceita! Crie o acordo formal abaixo com base na proposta do cliente: "
            f"**{aviso['parcelas']}x {aviso['periodicidade']}** de "
            f"**{formatar_brl(aviso['valor_parcela'])}** · "
            f"1ª parcela em **{formatar_data(aviso['data_primeira'])}**"
        )

    # =============================================================
    # HEADER (compacto: só título + voltar na primeira linha)
    # =============================================================
    col_titulo, col_voltar = st.columns([7, 1])
    with col_titulo:
        st.markdown(
            f"<h1 style='color:{AZUL_ESCURO}; margin-bottom:0;'>"
            f"🏢 {cliente.nome_principal}</h1>",
            unsafe_allow_html=True,
        )
        wpp_str = " · 📱 WhatsApp" if cliente.tem_whatsapp else ""
        st.caption(
            f"{cliente.cnpj or 'sem CNPJ'} · "
            f"{cliente.contato or 'sem contato'} · "
            f"{cliente.telefone or 'sem tel'}{wpp_str}"
        )
    with col_voltar:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Voltar", use_container_width=True, key="btn_voltar_cli"):
            del st.session_state["cliente_aberto_id"]
            st.rerun()

    # Linha de botões de ação (segunda linha)
    col_novo, col_titulos, col_portal, col_excluir, _ = st.columns([1.5, 1.5, 1.5, 1.5, 2])
    with col_novo:
        if st.button(
            "➕ Novo Acordo",
            use_container_width=True,
            type="primary",
            help="Cria um novo acordo já com os dados deste cliente preenchidos",
            key="btn_novo_acordo_cliente",
        ):
            st.session_state["novo_acordo_cliente_preset"] = {
                "cliente_id": cliente.id,
                "cliente_nome": cliente.nome_principal,
                "cliente_cnpj": cliente.cnpj or "",
                "cliente_contato": cliente.contato or "",
                "cliente_email": cliente.email_cobranca or "",
                "cliente_telefone": cliente.telefone or "",
                "cliente_tem_whatsapp": bool(cliente.tem_whatsapp),
            }

            # Pré-carrega os títulos avulsos em aberto do cliente
            titulos = repo_portal.buscar_titulos_disponiveis(cliente.id)
            if titulos:
                boletos_pre = []
                for t in titulos:
                    boletos_pre.append({
                        "codigo_parceiro": t.get("codigo_parceiro", 0) or 0,
                        "razao_social_parceiro": t.get("razao_social_parceiro", "") or "",
                        "empresa": t.get("empresa", 1) or 1,
                        "codigo_vendedor": t.get("codigo_vendedor", 0) or 0,
                        "nome_vendedor": t.get("nome_vendedor", "") or "",
                        "vencimento": t.get("vencimento", "") or "",
                        "numero_nota": t.get("numero_nota", "") or "",
                        "numero_unico": t.get("numero_unico", 0) or 0,
                        "principal": float(t.get("principal", 0) or 0),
                        "dias_atraso": 0,
                        "fim_juros": "",
                        "juros": 0.0,
                        "multa": 0.0,
                        "total": float(t.get("principal", 0) or 0),
                        "parcelas_alocadas": [],
                        "distribuicao": [],
                        "origem": "MANUAL",
                    })
                if boletos_pre:
                    st.session_state["pre_titulos_cliente"] = boletos_pre

            del st.session_state["cliente_aberto_id"]
            st.switch_page("pages/2_➕_Novo_Acordo.py")
    with col_titulos:
        if st.button(
            "📥 Cadastrar títulos",
            use_container_width=True,
            help="Cadastra títulos do cliente sem criar acordo (pra usar no portal depois)",
            key="btn_cad_titulos",
        ):
            st.session_state["cliente_modal_cadastrar_titulos"] = True
            st.rerun()
    with col_portal:
        if st.button(
            "🔗 Link do Portal",
            use_container_width=True,
            help="Gera um link único pro cliente acessar o portal de auto-acordo",
            key="btn_gerar_link",
        ):
            st.session_state["cliente_modal_gerar_link"] = True
            st.rerun()
    with col_excluir:
        from src.modelos.tipos import PerfilUsuario
        if usuario.perfil == PerfilUsuario.ADMIN:
            if st.button(
                "🗑 Excluir cliente",
                use_container_width=True,
                help="Exclui permanentemente o cliente e todo o histórico",
                key="btn_excluir_cliente",
            ):
                st.session_state["cliente_modal_excluir"] = True
                st.rerun()

    # === MODAIS ===
    if st.session_state.get("cliente_modal_excluir"):
        _modal_excluir_cliente(cliente, usuario)
        return

    if st.session_state.get("cliente_modal_cadastrar_titulos"):
        _modal_cadastrar_titulos(cliente, usuario)
        return  # não renderiza o resto enquanto modal aberto

    if st.session_state.get("cliente_modal_gerar_link"):
        _modal_gerar_link_portal(cliente, usuario)
        return

    st.markdown("---")

    # =============================================================
    # TABS DO CLIENTE: Resumo · Acordos · Títulos · Anexos
    # =============================================================
    from src.banco import repo_portal as _rp
    acordos = repo_extras.listar_acordos_do_cliente(cliente.id)
    titulos_avulsos = _rp.listar_todos_titulos_avulsos_do_cliente(cliente.id)
    from src.banco import repo_anexos as _ra
    qtd_anexos = _ra.contar_anexos_do_cliente(cliente.id)
    qtd_propostas_pend = _rp.contar_propostas_pendentes_do_cliente(cliente.id)

    label_resumo = "📊 Resumo"
    if qtd_propostas_pend > 0:
        label_resumo = f"📊 Resumo · 📨 {qtd_propostas_pend} proposta(s)"

    tab_resumo, tab_acordos, tab_titulos, tab_anexos = st.tabs([
        label_resumo,
        f"📋 Acordos ({len(acordos)})",
        f"📥 Títulos ({len(titulos_avulsos)})",
        f"📎 Anexos ({qtd_anexos})",
    ])

    # ----- TAB RESUMO -----
    with tab_resumo:
        # === PROPOSTAS DO PORTAL (se tiver pendentes) ===
        propostas_pendentes = _rp.listar_propostas_do_cliente(
            cliente.id, apenas_pendentes=True,
        )
        if propostas_pendentes:
            st.markdown(
                f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
                f"📨 Propostas do Portal · {len(propostas_pendentes)} aguardando análise</h3>",
                unsafe_allow_html=True,
            )
            st.caption("Propostas enviadas por este cliente via Portal de Acordos.")

            # Import da função render do inicio (evita duplicar código)
            from src.telas.inicio import _render_proposta_item
            for p in propostas_pendentes:
                _render_proposta_item(
                    p, usuario,
                    key_prefix=f"cli{cliente.id}_prop",
                    mostrar_btn_cliente=False,  # já está no perfil dele
                )
                st.markdown(
                    "<hr style='margin:4px 0; border-color:#EEE;'>",
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)

        # === HISTÓRICO DE PROPOSTAS ANALISADAS (expander) ===
        propostas_todas = _rp.listar_propostas_do_cliente(cliente.id)
        propostas_analisadas = [p for p in propostas_todas if p["status"] != "PENDENTE"]
        if propostas_analisadas:
            with st.expander(
                f"📜 Histórico de propostas analisadas · {len(propostas_analisadas)}",
                expanded=False,
            ):
                for p in propostas_analisadas[:20]:
                    cor_status = "#0F8C3B" if p["status"] == "ACEITA" else "#DC3545"
                    obs_str = ""
                    if p.get("observacao_cliente"):
                        obs_str = (
                            f"<br><span style='font-size:11px; color:#666; font-style:italic;'>"
                            f"💬 \"{p['observacao_cliente'][:80]}\"</span>"
                        )
                    st.markdown(
                        f"<b style='color:{cor_status}'>{p['status']}</b> · "
                        f"{p['qtd_parcelas']}x {p['periodicidade'].lower()} de "
                        f"<b>{formatar_brl(p['valor_parcela'])}</b><br>"
                        f"<span style='font-size:11px; color:#666;'>"
                        f"Enviada em {formatar_data(p['enviado_em'])} · "
                        f"Analisada em {formatar_data(p.get('analisado_em') or p['enviado_em'])}"
                        f"</span>{obs_str}",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        "<hr style='margin:4px 0; border-color:#EEE;'>",
                        unsafe_allow_html=True,
                    )

            st.markdown("<br>", unsafe_allow_html=True)

        # === KPIs ===
        metricas = repo_extras.metricas_cliente(cliente.id)

        st.markdown("### 📊 Indicadores")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Total acordos", metricas["total"])
        with c2:
            st.metric("Ativos", metricas["ativos"])
        with c3:
            st.metric("Quitados", metricas["quitados"],
                      delta=f"{metricas['taxa_quitacao']:.1f}%",
                      delta_color="normal")
        with c4:
            st.metric("Quebrados", metricas["quebrados"],
                      delta=f"{metricas['taxa_quebra']:.1f}%",
                      delta_color="inverse")
        with c5:
            st.metric("Saldo pendente",
                      formatar_brl(metricas["valor_pendente"]))

        st.markdown(
            f"<div style='color:#666; font-size:13px; margin-top:8px;'>"
            f"Total já negociado: <b>{formatar_brl(metricas['valor_total_negociado'])}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ----- TAB ACORDOS -----
    with tab_acordos:
        if not acordos:
            st.info("Esse cliente ainda não tem nenhum acordo registrado.")
        else:
            st.markdown(f"### 📋 Histórico de acordos ({len(acordos)})")

            for a in acordos:
                col_info, col_progresso, col_btn = st.columns([3, 2, 1])
                with col_info:
                    st.markdown(f"**{a['numero_interno']}** · {a['tipo_cobranca']}")
                    data_str = formatar_data(a['data_acordo'])
                    enc_str = (
                        f" · encerrado em {formatar_data(a['data_encerramento'])}"
                        if a.get("data_encerramento") else ""
                    )
                    st.caption(
                        f"Negociador: {a['negociador_nome']} · Criado em {data_str}{enc_str}"
                    )
                    st.markdown(
                        badge_status_acordo(a["status"]),
                        unsafe_allow_html=True,
                    )
                with col_progresso:
                    qtd = a["quantidade_parcelas"]
                    pagas = a.get("qtd_pagas", 0) or 0
                    st.markdown(
                        f"<b>{pagas}/{qtd}</b> parcelas pagas",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<small>{formatar_brl(a['valor_total'])} total · "
                        f"{formatar_brl(a.get('saldo', 0))} restante</small>",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    if st.button("Abrir →", key=f"hist_open_{a['id']}", use_container_width=True):
                        st.session_state["acordo_id_aberto"] = a["id"]
                        st.switch_page("pages/1_🏠_Início.py")
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

    # ----- TAB TÍTULOS -----
    with tab_titulos:
        if not titulos_avulsos:
            st.info(
                "Esse cliente ainda não tem títulos cadastrados (sem acordo). "
                "Clique em **📥 Cadastrar títulos** acima pra adicionar."
            )
        else:
            total_avulsos = sum(t["principal"] for t in titulos_avulsos)
            qtd_em_aberto = sum(
                1 for t in titulos_avulsos
                if (t["status"] or "EM_ABERTO") == "EM_ABERTO"
            )
            qtd_em_proposta = sum(1 for t in titulos_avulsos if t["status"] == "EM_PROPOSTA")

            status_str = ""
            if qtd_em_aberto and qtd_em_proposta:
                status_str = f" · {qtd_em_aberto} aberto(s), {qtd_em_proposta} em proposta"
            elif qtd_em_proposta:
                status_str = f" · {qtd_em_proposta} em proposta"

            st.markdown(
                f"### 📥 Títulos sem acordo · {len(titulos_avulsos)} · "
                f"Total {formatar_brl(total_avulsos)}{status_str}"
            )
            st.caption(
                "Títulos disponíveis pro cliente ver no Portal e propor acordo. "
                "Você também pode usá-los no fluxo de Novo Acordo manualmente."
            )

            # Botão de atalho pra gerar link
            col_atalho_link, _ = st.columns([2, 5])
            with col_atalho_link:
                if st.button(
                    "🔗 Gerar link do Portal",
                    use_container_width=True,
                    help="Abre o modal pra criar um link único pro cliente",
                    key=f"atalho_link_{cliente.id}",
                ):
                    st.session_state["cliente_modal_gerar_link"] = True
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            for t in titulos_avulsos:
                col_info, col_val, col_acao = st.columns([5, 2, 1])
                with col_info:
                    status_atual = t['status'] or 'EM_ABERTO'
                    cor_status = "#0F8C3B" if status_atual == 'EM_ABERTO' else "#FAC318"
                    st.markdown(
                        f"<b>{t['codigo_parceiro']}</b> · {t['razao_social_parceiro'][:40]}<br>"
                        f"<span style='font-size:11px; color:#666;'>"
                        f"Venc: {formatar_data(t['vencimento'])} · "
                        f"Nota {t['numero_nota']} · Único {t['numero_unico']} · "
                        f"Status: <b style='color:{cor_status}'>{status_atual}</b>"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
                with col_val:
                    st.markdown(
                        f"<div style='text-align:right; font-weight:700;'>"
                        f"{formatar_brl(t['principal'])}</div>",
                        unsafe_allow_html=True,
                    )
                with col_acao:
                    status_atual = t['status'] or 'EM_ABERTO'
                    if status_atual == 'EM_ABERTO':
                        if st.button("🗑", key=f"hist_del_tit_{t['id']}", help="Remover título"):
                            try:
                                _rp.remover_titulo_avulso(t['id'])
                                st.toast("✅ Título removido", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro ao remover: {e}")
                st.markdown("<hr style='margin:2px 0; border-color:#EEE;'>", unsafe_allow_html=True)

    # ----- TAB ANEXOS -----
    with tab_anexos:
        _bloco_anexos_cliente(cliente, usuario)


# ============================================================
# MODAL EXCLUSÃO DO CLIENTE (só Admin)
# ============================================================

def _modal_excluir_cliente(cliente, usuario):
    """Modal de confirmação de exclusão permanente do cliente.
    
    Exige que o admin digite a própria senha antes de confirmar.
    """
    from src.banco import repo_usuario
    from src.utils.marca import AZUL_ESCURO

    st.markdown("---")
    st.markdown(
        f"<div style='background:#FFF0F0; border-left:5px solid #DC3545; "
        f"padding:16px; border-radius:6px; margin-bottom:16px;'>"
        f"<div style='font-size:16px; font-weight:700; color:#DC3545;'>"
        f"⚠️ Exclusão permanente</div>"
        f"<div style='color:#444; margin-top:6px;'>"
        f"Você está prestes a excluir <b>{cliente.nome_principal}</b> e "
        f"<b>todo o histórico</b> vinculado: acordos, parcelas, pagamentos, "
        f"títulos, anexos, propostas e tokens do portal.<br>"
        f"<b>Essa ação não pode ser desfeita.</b>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    col_close, _ = st.columns([1, 8])
    with col_close:
        if st.button("✕ Cancelar", key="close_excluir_cliente"):
            del st.session_state["cliente_modal_excluir"]
            st.rerun()

    with st.form("form_excluir_cliente"):
        senha = st.text_input(
            "Digite sua senha para confirmar a exclusão",
            type="password",
            placeholder="Sua senha de acesso ao sistema",
        )
        confirmar = st.form_submit_button(
            "🗑 Confirmar exclusão permanente",
            use_container_width=True,
        )

        if confirmar:
            if not senha:
                st.error("❌ Digite sua senha para confirmar.")
                return

            # Valida senha do admin logado
            usuario_validado = repo_usuario.autenticar(usuario.email, senha)
            if usuario_validado is None:
                st.error("❌ Senha incorreta. Exclusão cancelada.")
                return

            # Executa exclusão
            try:
                nome_cliente = cliente.nome_principal
                contagens = repo_cliente.excluir_cliente_completo(cliente.id)

                # Registra no log de auditoria
                from src.banco import repos_auxiliares
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id,
                    usuario_nome=usuario.nome,
                    acao="EXCLUIR_CLIENTE_COMPLETO",
                    entidade="cliente",
                    entidade_id=cliente.id,
                    contexto=nome_cliente,
                    antes={
                        "nome": nome_cliente,
                        "cnpj": cliente.cnpj,
                        **contagens,
                    },
                )

                del st.session_state["cliente_modal_excluir"]
                del st.session_state["cliente_aberto_id"]
                st.success(
                    f"✓ Cliente **{nome_cliente}** excluído permanentemente. "
                    f"{contagens.get('acordos', 0)} acordo(s), "
                    f"{contagens.get('parcelas', 0)} parcela(s) e "
                    f"{contagens.get('anexos', 0)} anexo(s) removidos."
                )
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao excluir: {str(e)[:300]}")


# ============================================================
# MODAIS DO PORTAL DO CLIENTE (Erick - 13/05/2026)
# ============================================================

def _modal_cadastrar_titulos(cliente, usuario):
    """Modal pra cadastrar títulos avulsos do cliente (sem criar acordo)."""
    from src.banco import repo_portal
    from src.servicos.leitor_xlsx import importar_xlsx_titulos
    from src.utils.formatadores import formatar_brl, formatar_data

    st.markdown("---")
    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}'>📥 Cadastrar títulos sem acordo</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Use isso pra deixar os títulos do cliente cadastrados no sistema, "
        "sem precisar criar um acordo agora. Esses títulos ficam disponíveis "
        "no Portal do Cliente."
    )

    col_close, _ = st.columns([1, 8])
    with col_close:
        if st.button("✕ Fechar", key="close_cad_titulos"):
            del st.session_state["cliente_modal_cadastrar_titulos"]
            st.rerun()

    # Upload de arquivo
    arq = st.file_uploader(
        "Selecione o arquivo BASE_CRUA do Sankhya (.xls ou .xlsx)",
        type=["xls", "xlsx"],
        key="upload_titulos_avulsos",
    )

    if arq:
        bytes_arq = arq.read()
        res = importar_xlsx_titulos(bytes_arq, arq.name)

        from src.telas.calculadora import _mostrar_feedback_upload
        _mostrar_feedback_upload(res)

        if not res.tem_erros_bloqueantes and res.boletos:
            st.markdown(
                f"<h4>📋 Preview ({len(res.boletos)} título(s) prontos)</h4>",
                unsafe_allow_html=True,
            )

            # Tabela preview
            df_data = []
            for b in res.boletos[:20]:
                df_data.append({
                    "Cód Parc": b.codigo_parceiro,
                    "Razão": b.razao_social_parceiro[:30],
                    "Venc": formatar_data(b.vencimento),
                    "Nota": b.numero_nota,
                    "Único": b.numero_unico,
                    "Valor": formatar_brl(b.principal),
                })
            st.dataframe(df_data, use_container_width=True, hide_index=True)
            if len(res.boletos) > 20:
                st.caption(f"... e mais {len(res.boletos) - 20} título(s)")

            total = sum(b.principal for b in res.boletos)
            st.markdown(
                f"<b>Total:</b> {formatar_brl(total)} · "
                f"<b>{len(res.boletos)}</b> título(s)",
                unsafe_allow_html=True,
            )

            if st.button(
                f"✅ Confirmar cadastro de {len(res.boletos)} título(s)",
                type="primary", use_container_width=True,
            ):
                qtd_ok = 0
                qtd_duplicado = 0
                erros_outros = []
                for b in res.boletos:
                    try:
                        repo_portal.cadastrar_titulo_avulso(
                            cliente_id=cliente.id,
                            codigo_parceiro=b.codigo_parceiro,
                            razao_social_parceiro=b.razao_social_parceiro,
                            empresa=int(b.empresa),
                            codigo_vendedor=b.codigo_vendedor,
                            nome_vendedor=b.nome_vendedor,
                            vencimento=b.vencimento.isoformat(),
                            numero_nota=b.numero_nota,
                            numero_unico=b.numero_unico,
                            principal=b.principal,
                            cadastrado_por_id=usuario.id,
                        )
                        qtd_ok += 1
                    except Exception as e:
                        msg = str(e).lower()
                        # Só silencia se for duplicidade conhecida
                        if "unique" in msg or "duplicate" in msg or "duplicat" in msg or "numero_unico" in msg:
                            qtd_duplicado += 1
                        else:
                            erros_outros.append(f"{b.numero_unico}: {str(e)[:200]}")
                        continue

                if qtd_ok > 0:
                    st.success(
                        f"✓ {qtd_ok} título(s) cadastrado(s) com sucesso."
                        + (f" ({qtd_duplicado} duplicado(s) ignorado(s))" if qtd_duplicado else "")
                    )
                else:
                    st.error(
                        f"⛔ Nenhum título cadastrado. "
                        f"{qtd_duplicado} duplicado(s) e {len(erros_outros)} erro(s)."
                    )

                # Mostra erros não-duplicidade pro Erick poder me reportar
                if erros_outros:
                    with st.expander(f"⚠ Ver {len(erros_outros)} erro(s) técnico(s)"):
                        for err in erros_outros[:10]:
                            st.code(err)

                # Só fecha se cadastrou pelo menos 1
                if qtd_ok > 0:
                    del st.session_state["cliente_modal_cadastrar_titulos"]
                    st.rerun()

    # Lista de títulos já cadastrados
    st.markdown("<hr>", unsafe_allow_html=True)
    titulos = repo_portal.listar_titulos_avulsos_do_cliente(cliente.id)
    if titulos:
        st.markdown(
            f"<h4>📋 Títulos já cadastrados ({len(titulos)})</h4>",
            unsafe_allow_html=True,
        )
        for t in titulos[:20]:
            col_info, col_val, col_acao = st.columns([5, 2, 1])
            with col_info:
                st.markdown(
                    f"<b>{t['codigo_parceiro']}</b> · {t['razao_social_parceiro'][:35]}<br>"
                    f"<span style='font-size:11px; color:#666;'>"
                    f"Venc: {formatar_data(t['vencimento'])} · "
                    f"Nota {t['numero_nota']} · Único {t['numero_unico']}"
                    f"</span>",
                    unsafe_allow_html=True,
                )
            with col_val:
                st.markdown(
                    f"<div style='text-align:right; font-weight:700;'>"
                    f"{formatar_brl(t['principal'])}</div>",
                    unsafe_allow_html=True,
                )
            with col_acao:
                if st.button("🗑", key=f"del_tit_{t['id']}", help="Remover"):
                    try:
                        repo_portal.remover_titulo_avulso(t['id'])
                        st.toast("✅ Título removido", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao remover: {e}")


def _modal_gerar_link_portal(cliente, usuario):
    """Modal pra gerar link único do portal."""
    from src.banco import repo_portal
    from src.utils.formatadores import formatar_data

    st.markdown("---")
    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}'>🔗 Link do Portal do Cliente</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Gere um link único pro cliente. Ele acessa, vê os títulos cadastrados, "
        "monta uma proposta de acordo e envia pra equipe analisar."
    )

    col_close, _ = st.columns([1, 8])
    with col_close:
        if st.button("✕ Fechar", key="close_gerar_link"):
            del st.session_state["cliente_modal_gerar_link"]
            st.rerun()

    # Validação: cliente tem algum título avulso cadastrado?
    qtd_disponiveis = repo_portal.contar_titulos_avulsos_do_cliente(cliente.id)
    todos_titulos = repo_portal.listar_todos_titulos_avulsos_do_cliente(cliente.id)
    qtd_total = len(todos_titulos)

    if qtd_total == 0:
        st.warning(
            "⚠ Esse cliente ainda não tem títulos cadastrados. "
            "Cadastre os títulos antes de gerar o link, "
            "senão o cliente não terá nada pra visualizar."
        )
        return

    if qtd_disponiveis == 0:
        # Verifica se há proposta ACEITA sem acordo gerado
        propostas_aceitas = repo_portal.listar_propostas_aceitas_sem_acordo(cliente.id)
        if propostas_aceitas:
            st.warning(
                f"⚠ Cliente tem {qtd_total} título(s) em proposta aceita. "
                f"Gere o acordo abaixo antes de criar um novo link."
            )
            for prop in propostas_aceitas:
                st.markdown(
                    f"**Proposta aceita:** {prop['qtd_parcelas']}x "
                    f"{prop['periodicidade'].lower()} · "
                    f"1ª parcela {prop['data_primeira_parcela']}"
                )
                if st.button(
                    "✅ Gerar acordo desta proposta",
                    key=f"gerar_acordo_prop_{prop['id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    from src.telas.inicio import _criar_acordo_da_proposta
                    _criar_acordo_da_proposta(prop, usuario)
                    st.rerun()
        else:
            st.info(
                f"ℹ️ Cliente tem {qtd_total} título(s) mas nenhum em aberto. "
                f"Você ainda pode gerar um novo link se quiser."
            )
    else:
        st.info(f"📋 Cliente tem **{qtd_disponiveis}** título(s) cadastrado(s) em aberto.")

    # Admin não tem limite. Demais perfis: 3 links/dia/cliente.
    from src.modelos.tipos import PerfilUsuario
    eh_admin = (usuario.perfil == PerfilUsuario.ADMIN)
    LIMITE_DIARIO = 3
    qtd_hoje = repo_portal.contar_tokens_gerados_hoje(cliente.id)

    if eh_admin:
        # Admin: sem limite
        st.caption(
            f"🛡 **Admin** · Você pode gerar links ilimitados. "
            f"Hoje já foram gerados {qtd_hoje} link(s) pra este cliente."
        )
        if st.button("🔗 Gerar novo link", type="primary", use_container_width=True):
            try:
                token = repo_portal.gerar_token(cliente.id, usuario.id, dias_validade=30)
                st.session_state["portal_token_recem_gerado"] = token
                st.toast("✅ Link gerado!", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao gerar link: {e}")
                st.exception(e)
    else:
        # Diretoria / Cobrança: limite de 3/dia
        qtd_restantes = LIMITE_DIARIO - qtd_hoje
        if qtd_hoje >= LIMITE_DIARIO:
            st.error(
                f"⛔ Limite atingido: já foram gerados **{qtd_hoje} link(s)** hoje "
                f"para este cliente. O limite é de **{LIMITE_DIARIO} links por dia**. "
                f"Tente novamente amanhã ou peça pra um admin gerar."
            )
        else:
            st.caption(
                f"Você pode gerar mais **{qtd_restantes}** link(s) hoje "
                f"para este cliente (limite diário: {LIMITE_DIARIO})."
            )
            if st.button("🔗 Gerar novo link", type="primary", use_container_width=True):
                try:
                    token = repo_portal.gerar_token(cliente.id, usuario.id, dias_validade=30)
                    st.session_state["portal_token_recem_gerado"] = token
                    st.toast("✅ Link gerado!", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao gerar link: {e}")
                    st.exception(e)

    # Mostrar token recém-gerado
    if st.session_state.get("portal_token_recem_gerado"):
        token = st.session_state["portal_token_recem_gerado"]

        # Pega URL base do parâmetro (admin pode configurar)
        from src.banco import repos_auxiliares
        try:
            url_base = repos_auxiliares.get_parametro("portal.url_base") or ""
        except Exception:
            url_base = ""

        # Se não tem URL configurada, pede pro admin colar
        if not url_base:
            st.warning(
                "⚠ Antes de mostrar o link, configure a URL do seu app. "
                "É a URL que aparece na barra do navegador quando você acessa o sistema "
                "(ex: `https://calculadoradeacordo.streamlit.app` ou outro nome configurado)."
            )
            nova_url = st.text_input(
                "URL base do seu app Streamlit",
                placeholder="https://seu-app.streamlit.app",
                key="port_url_input",
            )
            if st.button("💾 Salvar URL", key="salvar_url"):
                if nova_url.startswith("http"):
                    try:
                        repos_auxiliares.set_parametro(
                            "portal.url_base", nova_url.rstrip("/"),
                        )
                        st.toast("✅ URL salva!", icon="✅")
                        st.success("URL salva! Recarregando...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar URL: {e}")
                        st.exception(e)
                else:
                    st.error("URL precisa começar com http:// ou https://")
            return

        url_completa = f"{url_base}/Portal?token={token}"

        st.success("✅ Link gerado com sucesso!")
        st.markdown("**Copie e envie pelo WhatsApp:**")
        st.code(url_completa, language=None)
        st.caption(
            "Esse link é único, válido por 30 dias e será invalidado "
            "automaticamente quando o cliente enviar a proposta."
        )

        # Botão pra reconfigurar URL caso esteja errada
        with st.expander("⚙ Configurar URL do app"):
            st.text_input(
                "URL atual",
                value=url_base,
                key="port_url_atual",
                disabled=True,
            )
            nova_url = st.text_input(
                "Nova URL (caso queira mudar)",
                placeholder="https://seu-app.streamlit.app",
                key="port_url_reconf",
            )
            if st.button("💾 Atualizar URL", key="atualizar_url"):
                if nova_url.startswith("http"):
                    try:
                        repos_auxiliares.set_parametro(
                            "portal.url_base", nova_url.rstrip("/"),
                        )
                        st.toast("✅ URL atualizada!", icon="✅")
                        st.success("URL atualizada!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao atualizar URL: {e}")
                        st.exception(e)
                else:
                    st.error("URL precisa começar com http:// ou https://")

        # Token separado (caso o link não funcione)
        with st.expander("🔑 Token isolado (uso avançado)"):
            st.caption(
                "Se o link completo não funcionar, use o token abaixo. "
                "O cliente pode abrir o app e adicionar `?token=...` na URL."
            )
            st.code(token, language=None)

        # Mensagem pronta pra WhatsApp
        mensagem_wpp = (
            f"Olá! Aqui está seu link de acordo personalizado da LLE:\n\n"
            f"{url_completa}\n\n"
            f"Acesse pelo celular, escolha como quer parcelar e nos envie sua proposta. "
            f"Nossa equipe analisará rapidamente."
        )
        with st.expander("📱 Texto pronto pra WhatsApp"):
            st.text_area(
                "Copie esse texto e envie:",
                value=mensagem_wpp, height=150,
                key="wpp_text", label_visibility="collapsed",
            )

    # Histórico de links
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h4>🔗 Links anteriores</h4>", unsafe_allow_html=True)
    tokens = repo_portal.listar_tokens_do_cliente(cliente.id)
    if not tokens:
        st.caption("Nenhum link gerado ainda.")
    else:
        for t in tokens[:10]:
            ativo_str = "🟢 Ativo" if t["ativo"] else "⚫ Inativo"
            usado_str = ""
            if t.get("usado_em"):
                usado_str = f" · ✓ Usado em {formatar_data(t['usado_em'])}"
            st.markdown(
                f"<div style='background:#F8F9FA; padding:8px 12px; "
                f"border-radius:4px; margin-bottom:6px; font-size:12px;'>"
                f"{ativo_str} · Criado em {formatar_data(t['criado_em'])} · "
                f"Expira em {formatar_data(t['expira_em'])}{usado_str}<br>"
                f"<span style='color:#666; font-family:monospace;'>"
                f"token: {t['token'][:30]}...</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ============================================================
# BLOCO DE ANEXOS DO CLIENTE (Erick - 13/05/2026)
# ============================================================

def _bloco_anexos_cliente(cliente, usuario):
    """Bloco de anexos no perfil do cliente.
    
    Permite upload de PDFs (comprovantes bancários) que ficam vinculados
    ao cliente. Limite de 5 MB por arquivo. Salvos em Base64 no banco.
    """
    from src.banco import repo_anexos

    anexos = repo_anexos.listar_anexos_do_cliente(cliente.id)
    qtd = len(anexos)

    titulo_expander = (
        f"📎 Anexos · {qtd} arquivo(s)" if qtd > 0
        else "📎 Anexos · nenhum arquivo"
    )

    with st.expander(titulo_expander, expanded=False):
        st.caption(
            "Anexe comprovantes bancários (PDF) deste cliente. "
            "Limite: 5 MB por arquivo."
        )

        # Upload
        arq = st.file_uploader(
            "Selecione um PDF",
            type=["pdf"],
            key=f"anx_upload_{cliente.id}",
            accept_multiple_files=False,
        )

        if arq is not None:
            descricao = st.text_input(
                "Descrição (opcional)",
                placeholder="Ex: Comprovante PIX 13/05/2026 R$ 500,00",
                key=f"anx_desc_{cliente.id}",
                max_chars=200,
            )

            col_ok, col_cancel = st.columns([1, 4])
            with col_ok:
                if st.button(
                    "⬆ Enviar",
                    type="primary",
                    use_container_width=True,
                    key=f"anx_btn_send_{cliente.id}",
                ):
                    try:
                        conteudo = arq.getvalue()
                        repo_anexos.adicionar_anexo(
                            cliente_id=cliente.id,
                            nome_arquivo=arq.name,
                            conteudo_bytes=conteudo,
                            upload_por_id=usuario.id,
                            descricao=descricao if descricao else None,
                            mime_type=arq.type or "application/pdf",
                        )
                        st.success(f"✓ {arq.name} anexado.")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"⛔ {str(e)}")
                    except Exception as e:
                        st.error(f"⛔ Erro: {str(e)[:200]}")

        if anexos:
            st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)
            st.markdown("**Arquivos anexados:**")

            for a in anexos:
                col_nome, col_meta, col_btns = st.columns([4, 3, 2])
                with col_nome:
                    tam_kb = a["tamanho_bytes"] / 1024
                    tam_str = (
                        f"{tam_kb:.0f} KB" if tam_kb < 1024
                        else f"{tam_kb / 1024:.1f} MB"
                    )
                    desc_str = f"<br><i>{a['descricao']}</i>" if a.get("descricao") else ""
                    st.markdown(
                        f"📄 <b>{a['nome_arquivo']}</b><br>"
                        f"<span style='font-size:11px; color:#666;'>"
                        f"{tam_str} · {a.get('upload_por_nome') or 'desconhecido'} · "
                        f"{formatar_data(a['upload_em'])}"
                        f"</span>{desc_str}",
                        unsafe_allow_html=True,
                    )
                with col_meta:
                    pass  # espaço
                with col_btns:
                    cb1, cb2 = st.columns(2)
                    with cb1:
                        # Botão de download
                        conteudo = repo_anexos.buscar_conteudo_anexo(a["id"])
                        if conteudo:
                            st.download_button(
                                "⬇",
                                data=conteudo["conteudo_bytes"],
                                file_name=conteudo["nome_arquivo"],
                                mime=conteudo["mime_type"],
                                key=f"anx_dl_{a['id']}",
                                use_container_width=True,
                                help="Baixar",
                            )
                    with cb2:
                        # Remover (só admin pode)
                        from src.modelos.tipos import PerfilUsuario
                        if usuario.perfil == PerfilUsuario.ADMIN:
                            if st.button(
                                "🗑",
                                key=f"anx_del_{a['id']}",
                                use_container_width=True,
                                help="Remover (só admin)",
                            ):
                                repo_anexos.remover_anexo(a["id"])
                                st.rerun()
                st.markdown(
                    "<hr style='margin:4px 0; border-color:#EEE;'>",
                    unsafe_allow_html=True,
                )
