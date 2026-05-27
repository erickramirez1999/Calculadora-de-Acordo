"""
Tela Detalhe do Acordo (Seção 5b + 18).

3 abas: Cronograma · Títulos · Histórico
Cabeçalho com infos + botões PDF/XLSX.
Pagamento parcial suportado.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import streamlit as st

from src.banco import repo_acordo, repos_auxiliares
from src.modelos.tipos import (
    PerfilUsuario, StatusAcordo, StatusParcela,
)
from src.servicos.juros import calcular_valor_atualizado_parcela
from src.utils.estilo import badge_status_acordo, barra_progresso
from src.utils.formatadores import (
    formatar_brl, formatar_data, formatar_hora, normalizar_busca,
)
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE


def renderizar_detalhe(usuario, acordo_id: int):
    acordo = repo_acordo.buscar_completo(acordo_id)
    if acordo is None:
        st.error("Acordo não encontrado.")
        return

    # Mensagem persistente de ações anteriores (reabrir/quitar/etc)
    msg = st.session_state.pop("detalhe_acordo_msg", None)
    if msg:
        tipo, texto = msg
        if tipo == "sucesso":
            st.success(texto)
        elif tipo == "aviso":
            st.warning(texto)
        else:
            st.error(texto)

    # Modo somente leitura: só pra acordos finalizados
    # (Diretoria agora opera igual ADMIN - decisão Erick 13/05/2026,
    # exceto confirmar pagamento que continua sendo só do ADMIN)
    modo_leitura = acordo.status in (
        StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO,
    )

    # ============ CABEÇALHO ============
    col_back, col_titulo, col_xlsx = st.columns([1, 6, 1.5])
    with col_back:
        if st.button("← Voltar"):
            if "acordo_id_aberto" in st.session_state:
                del st.session_state["acordo_id_aberto"]
            st.rerun()
    with col_titulo:
        st.markdown(
            f"<h2 style='color:{AZUL_ESCURO}; margin: 0;'>{acordo.numero_interno}</h2>",
            unsafe_allow_html=True,
        )
    with col_xlsx:
        _botao_exportar_xlsx(acordo, usuario)

    # ============ DOCUMENTOS OFICIAIS ============
    with st.expander("📄 Documentos oficiais", expanded=False):
        st.caption(
            "Gere os documentos formais para enviar ao cliente. "
            "A Carta de Quitação só fica disponível quando o acordo estiver totalmente quitado."
        )
        _botoes_exportar_documentos(acordo, usuario)

    # Bloco de informações
    st.markdown(
        f"""
<div style="background: #F8F9FA; padding: 16px 20px; border-radius: 8px;
            margin-top: 12px; margin-bottom: 16px;">
<div style="font-size:18px; font-weight:700; color:{AZUL_ESCURO};">
{acordo.cliente_nome}
</div>
<div style="margin-top: 4px; font-size:13px; color:#444;">
Negociador: <b>{acordo.negociador_nome}</b> ·
Criado em: {formatar_data(acordo.data_criacao)} ·
Data do acordo: {formatar_data(acordo.data_acordo)}
</div>
<div style="margin-top: 8px; font-size:13px; color:#444;">
Juros títulos: <b>{acordo.pct_juros_mes_titulos:.2f}% a.m.</b> ·
Multa títulos: <b>{acordo.pct_multa_titulos:.2f}%</b> ·
Juros mora: <b>{acordo.pct_juros_mora_mes:.2f}% a.m.</b> ·
Multa mora: <b>{acordo.pct_multa_mora:.2f}%</b> ·
{"<b style='color:#DC3545;'>Desconto: " + f"{acordo.pct_desconto:.2f}%</b> · " if acordo.pct_desconto > 0 else ""}
Cobrança: <b>{acordo.tipo_cobranca.value}</b>
</div>
<div style="margin-top: 10px;">{badge_status_acordo(acordo.status.value)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Bloco: alterar negociador (todos os perfis com edição podem)
    if not modo_leitura and usuario.perfil in (
        PerfilUsuario.COBRANCA, PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA,
    ):
        _bloco_alterar_negociador(acordo, usuario)

    # Botões de ação
    if not modo_leitura and usuario.perfil in (
        PerfilUsuario.COBRANCA, PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA,
    ):
        eh_admin_local = usuario.perfil == PerfilUsuario.ADMIN

        col_q, col_c, _ = st.columns([1.5, 1.5, 5])
        with col_q:
            if st.button("⚠ Quebrar acordo", use_container_width=True):
                st.session_state[f"confirmar_quebra_{acordo.id}"] = True
        with col_c:
            # CANCELAR é restrito ao ADMIN (decisão Erick - 13/05/2026)
            # Outros perfis veem o botão desabilitado com tooltip explicativo
            if st.button(
                "⊘ Cancelar acordo",
                use_container_width=True,
                disabled=not eh_admin_local,
                help=None if eh_admin_local else "Apenas administradores podem cancelar acordos.",
            ):
                st.session_state[f"confirmar_cancelar_{acordo.id}"] = True

        # Confirmação modal-like
        if st.session_state.get(f"confirmar_quebra_{acordo.id}"):
            _confirmar_mudanca_status(
                acordo, usuario, StatusAcordo.QUEBRADO,
                "QUEBRAR este acordo? Isso encerra os lembretes.",
            )
        if st.session_state.get(f"confirmar_cancelar_{acordo.id}"):
            # Validação extra de segurança: só admin pode cancelar
            if usuario.perfil != PerfilUsuario.ADMIN:
                st.error("⛔ Apenas administradores podem cancelar acordos.")
                del st.session_state[f"confirmar_cancelar_{acordo.id}"]
            else:
                _confirmar_mudanca_status(
                    acordo, usuario, StatusAcordo.CANCELADO,
                    "CANCELAR este acordo? Não há registros de pagamento ainda.",
                )

    # Acordos finalizados: botão de reabrir (P1)
    if acordo.status in (StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO):
        if usuario.perfil in (PerfilUsuario.COBRANCA, PerfilUsuario.ADMIN):
            col_r, _ = st.columns([2, 6])
            with col_r:
                if st.button("🔄 Reabrir acordo", type="secondary", use_container_width=True):
                    st.session_state[f"confirmar_reabrir_{acordo.id}"] = True
            if st.session_state.get(f"confirmar_reabrir_{acordo.id}"):
                st.warning(
                    "Reabrir mantém o estado exato do encerramento "
                    "(parcelas pagas continuam pagas). Confirma?"
                )
                cc1, cc2, _ = st.columns([1, 1, 4])
                with cc1:
                    if st.button("✓ Confirmar reabertura", type="primary", key=f"sim_reab_{acordo.id}"):
                        try:
                            from src.banco.repo_acordo import atualizar_status
                            atualizar_status(acordo.id, StatusAcordo.ATIVO)
                            repos_auxiliares.registrar_log(
                                usuario_id=usuario.id, usuario_nome=usuario.nome,
                                acao="REABRIR_ACORDO", entidade="acordo",
                                entidade_id=acordo.id,
                                contexto=f"{acordo.numero_interno}",
                                antes={"status": acordo.status.value},
                                depois={"status": "ATIVO"},
                            )
                            del st.session_state[f"confirmar_reabrir_{acordo.id}"]
                            st.session_state["detalhe_acordo_msg"] = (
                                "sucesso", f"✅ Acordo {acordo.numero_interno} reaberto com sucesso!"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao reabrir acordo: {e}")
                            st.exception(e)
                with cc2:
                    if st.button("Cancelar", key=f"nao_reab_{acordo.id}"):
                        del st.session_state[f"confirmar_reabrir_{acordo.id}"]
                        st.rerun()

    # ============ ABAS ============
    tab1, tab2, tab3, tab_com, tab_prom, tab4 = st.tabs([
        "📅 Cronograma", "📄 Títulos", "👤 Cadastro",
        "💬 Comentários", "🤝 Promessas", "📜 Histórico",
    ])

    with tab1:
        _aba_cronograma(acordo, usuario, modo_leitura)
    with tab2:
        _aba_titulos(acordo)
    with tab3:
        _aba_cadastro(acordo, usuario)
    with tab_com:
        _aba_comentarios(acordo, usuario)
    with tab_prom:
        _aba_promessas(acordo, usuario)
    with tab4:
        _aba_historico(acordo, usuario)


# ============================================================
# ABAS
# ============================================================

def _aba_cronograma(acordo, usuario, modo_leitura: bool):
    parcelas = acordo.parcelas
    pagas = sum(1 for p in parcelas if p.status == StatusParcela.QUITADA)
    saldo_total = sum(p.valor_restante for p in parcelas)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"**{pagas} de {len(parcelas)} parcelas pagas**")
    with col2:
        st.markdown(
            f"<div style='text-align:right;'>Saldo devedor: "
            f"<b style='color:{AZUL_ESCURO};font-size:18px;'>"
            f"{formatar_brl(saldo_total)}</b></div>",
            unsafe_allow_html=True,
        )

    st.markdown(barra_progresso(pagas, len(parcelas)), unsafe_allow_html=True)
    st.markdown("---")

    hoje = date.today()
    for p in parcelas:
        _linha_parcela(acordo, p, usuario, modo_leitura, hoje)


def _linha_parcela(acordo, parcela, usuario, modo_leitura: bool, hoje: date):
    em_atraso = (
        parcela.status != StatusParcela.QUITADA
        and parcela.vencimento_atual < hoje
    )
    dias_atraso = (hoje - parcela.vencimento_atual).days if em_atraso else 0

    # Calcula valor atualizado (mora P3 + P4.1)
    valor_atu, juros_mora, multa_mora, _ = calcular_valor_atualizado_parcela(
        parcela, hoje,
        acordo.pct_juros_mora_mes, acordo.pct_multa_mora,
    )

    # Estilo de fundo conforme status
    if parcela.status == StatusParcela.QUITADA:
        bg = "#D4EDDA"; texto = "#155724"; icone = "✓"
    elif parcela.status == StatusParcela.AGUARDANDO_CONFIRMACAO:
        # NOVO ESTADO: azul - cobrança confirmou, esperando admin
        bg = "#CCE5FF"; texto = "#004085"; icone = "🔵"
    elif parcela.status == StatusParcela.PARCIAL:
        bg = "#FFF3CD"; texto = "#856404"; icone = "◐"
    elif em_atraso:
        bg = "#F8D7DA"; texto = "#721C24"; icone = "⚠"
    else:
        bg = "#FFFFFF"; texto = "#222"; icone = "○"

    valor_pago = parcela.valor_pago
    valor_orig_str = formatar_brl(parcela.valor_original)

    if parcela.status == StatusParcela.QUITADA:
        info_valor = f"Pago integral: {valor_orig_str}"
    elif parcela.status == StatusParcela.AGUARDANDO_CONFIRMACAO:
        info_valor = (
            f"<b>{valor_orig_str}</b> · "
            f"<span style='font-size:11px;'>Aguardando confirmação do admin</span>"
        )
    elif parcela.status == StatusParcela.PARCIAL:
        info_valor = (
            f"Pago: {formatar_brl(valor_pago)} de {valor_orig_str} · "
            f"Restam: <b>{formatar_brl(parcela.valor_restante)}</b>"
        )
    elif em_atraso:
        info_valor = (
            f"Original: {valor_orig_str} · "
            f"Atualizado: <b>{formatar_brl(valor_atu)}</b> "
            f"<span style='font-size:11px;'>(mora {dias_atraso} dia{'s' if dias_atraso != 1 else ''})</span>"
        )
    else:
        info_valor = f"Valor: <b>{valor_orig_str}</b>"

    cont = st.container()
    with cont:
        st.markdown(
            f"""
<div style="background:{bg}; color:{texto}; padding:10px 16px;
            border-radius:6px; margin-bottom:6px;
            display:flex; justify-content:space-between; align-items:center;">
    <div>
        <span style="font-weight:700; margin-right:10px;">{icone} Parcela {parcela.numero}</span>
        <span>· Venc. {formatar_data(parcela.vencimento_atual)}</span>
    </div>
    <div style="text-align:right;">{info_valor}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

        if not modo_leitura:
            eh_admin = usuario.perfil == PerfilUsuario.ADMIN
            eh_cobranca = usuario.perfil == PerfilUsuario.COBRANCA

            # Busca o ID da parcela no banco (objeto Parcela não tem .id)
            parcela_id = repo_acordo.buscar_parcela_id(acordo.id, parcela.numero)

            # CASO 0: Parcela QUITADA ou PARCIAL - só admin pode estornar
            if parcela.status in (StatusParcela.QUITADA, StatusParcela.PARCIAL) and eh_admin:
                # Lista pagamentos confirmados pra mostrar opção de estornar
                pagamentos = repo_acordo.listar_pagamentos_da_parcela(parcela_id) if parcela_id else []
                pagamentos_confirmados = [p for p in pagamentos if p.get("confirmado_pelo_admin")]
                if pagamentos_confirmados:
                    with st.expander(
                        f"📋 Pagamentos registrados ({len(pagamentos_confirmados)})",
                        expanded=False,
                    ):
                        for pag in pagamentos_confirmados:
                            col_info, col_btn = st.columns([4, 1])
                            with col_info:
                                obs_str = f" · {pag['observacao']}" if pag.get('observacao') else ""
                                st.markdown(
                                    f"<div style='font-size:13px;'>"
                                    f"<b>{formatar_brl(pag['valor'])}</b> em "
                                    f"{formatar_data(pag['data_pagamento'])} · "
                                    f"<i>Confirmado por {pag.get('confirmado_por_nome') or '—'}</i>"
                                    f"{obs_str}</div>",
                                    unsafe_allow_html=True,
                                )
                            with col_btn:
                                if st.button(
                                    "❌ Estornar",
                                    key=f"estornar_quit_{pag['id']}_{acordo.id}",
                                    use_container_width=True,
                                ):
                                    repo_acordo.estornar_pagamento(pag["id"])
                                    repos_auxiliares.registrar_log(
                                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                                        acao="ESTORNAR_PAGAMENTO",
                                        entidade="parcela", entidade_id=parcela_id,
                                        contexto=f"{acordo.numero_interno} · Parcela {parcela.numero}",
                                        antes={"valor_estornado": pag["valor"]},
                                    )
                                    # Se o acordo estava QUITADO, reabre pra ATIVO
                                    if acordo.status == StatusAcordo.QUITADO:
                                        repo_acordo.alterar_status(
                                            acordo.id, StatusAcordo.ATIVO,
                                        )
                                        repos_auxiliares.registrar_log(
                                            usuario_id=usuario.id, usuario_nome=usuario.nome,
                                            acao="REABRIR_AUTO", entidade="acordo",
                                            entidade_id=acordo.id,
                                            contexto=acordo.numero_interno,
                                            antes={"status": "QUITADO"},
                                            depois={"status": "ATIVO"},
                                        )
                                    st.success("✓ Pagamento estornado!")
                                    st.rerun()

        if not modo_leitura and parcela.status != StatusParcela.QUITADA:
            eh_admin = usuario.perfil == PerfilUsuario.ADMIN
            eh_cobranca = usuario.perfil == PerfilUsuario.COBRANCA

            # CASO 1: Parcela aguardando confirmação (azul) - cobrança/admin podem desfazer; admin confirma
            if parcela.status == StatusParcela.AGUARDANDO_CONFIRMACAO:
                # Busca o pagamento pendente
                pagamentos_pendentes = repo_acordo.listar_pagamentos_da_parcela(parcela_id)
                pagamentos_pendentes = [p for p in pagamentos_pendentes if not p.get("confirmado_pelo_admin")]
                if pagamentos_pendentes:
                    pag = pagamentos_pendentes[-1]  # último registrado
                    col1, col2, col3 = st.columns([2, 2, 2])
                    with col1:
                        if eh_admin:
                            if st.button(
                                "✅ Confirmar pagamento",
                                key=f"conf_adm_{parcela.numero}_{acordo.id}",
                                type="primary", use_container_width=True,
                            ):
                                repo_acordo.confirmar_pagamento_admin(
                                    pag["id"], usuario.id,
                                )
                                repos_auxiliares.registrar_log(
                                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                                    acao="CONFIRMAR_PAGAMENTO_ADMIN", entidade="parcela",
                                    entidade_id=parcela_id,
                                    contexto=f"{acordo.numero_interno} · Parcela {parcela.numero}",
                                    depois={"valor": pag["valor"], "data": pag["data_pagamento"]},
                                )
                                _verificar_quitacao_acordo(acordo, usuario)
                                st.success("✅ Pagamento confirmado!")
                                st.rerun()
                        else:
                            st.caption("⏳ Aguardando admin confirmar")
                    with col2:
                        # Cobrança ou Admin podem desfazer
                        if st.button(
                            "↩ Desfazer confirmação",
                            key=f"desf_{parcela.numero}_{acordo.id}",
                            use_container_width=True,
                        ):
                            try:
                                repo_acordo.desfazer_confirmacao_cobranca(pag["id"])
                                repos_auxiliares.registrar_log(
                                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                                    acao="DESFAZER_CONFIRMACAO_COBRANCA",
                                    entidade="parcela", entidade_id=parcela_id,
                                    contexto=f"{acordo.numero_interno} · Parcela {parcela.numero}",
                                    antes={"valor": pag["valor"]},
                                )
                                st.success("✓ Confirmação desfeita.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col3:
                        if st.button(
                            "📅 Remarcar data",
                            key=f"remarc_{parcela.numero}_{acordo.id}",
                            use_container_width=True,
                        ):
                            st.session_state[f"form_remarc_{acordo.id}_{parcela.numero}"] = True
            else:
                # CASO 2: Parcela em aberto / parcial / atrasada
                col_pgto, col_remarc, _ = st.columns([2, 2, 4])
                with col_pgto:
                    # Cobrança vê "🔵 Confirmar parcela"; Admin vê "💰 Registrar pagamento" (que já confirma)
                    label_btn = "💰 Registrar pagamento" if eh_admin else "🔵 Confirmar parcela"
                    if st.button(
                        label_btn,
                        key=f"pgto_{parcela.numero}_{acordo.id}",
                        use_container_width=True,
                        type="primary" if eh_admin else "secondary",
                    ):
                        st.session_state[f"form_pgto_{acordo.id}_{parcela.numero}"] = True
                with col_remarc:
                    if st.button(
                        "📅 Remarcar data",
                        key=f"remarc_{parcela.numero}_{acordo.id}",
                        use_container_width=True,
                    ):
                        st.session_state[f"form_remarc_{acordo.id}_{parcela.numero}"] = True

            # Formulário de pagamento
            if st.session_state.get(f"form_pgto_{acordo.id}_{parcela.numero}"):
                _form_pagamento(acordo, parcela, usuario, valor_atu)
            if st.session_state.get(f"form_remarc_{acordo.id}_{parcela.numero}"):
                _form_remarcar(acordo, parcela, usuario)


def _form_pagamento(acordo, parcela, usuario, valor_atualizado: float):
    """Form pra registrar pagamento (total ou parcial - P4)."""
    chave = f"form_pgto_{acordo.id}_{parcela.numero}"
    with st.form(f"pgto_form_{acordo.id}_{parcela.numero}"):
        st.markdown(f"#### Registrar pagamento — Parcela {parcela.numero}")
        col_v, col_d = st.columns(2)
        with col_v:
            valor_sugerido = (
                parcela.valor_restante
                if parcela.valor_restante > 0
                else parcela.valor_original
            )
            # Se está atrasada, sugere valor atualizado
            if valor_atualizado > parcela.valor_restante:
                st.caption(
                    f"Valor atualizado (com mora): {formatar_brl(valor_atualizado)}"
                )
            valor = st.number_input(
                "Valor pago (R$)",
                min_value=0.01,
                value=float(valor_sugerido),
                step=0.01,
                format="%.2f",
            )
        with col_d:
            data_pgto = st.date_input("Data do pagamento", value=date.today(), format="DD/MM/YYYY")
        obs = st.text_input("Observação (opcional)", placeholder="ex: PIX recebido")

        col_ok, col_cancel = st.columns(2)
        with col_ok:
            confirmar = st.form_submit_button("✓ Registrar", type="primary", use_container_width=True)
        with col_cancel:
            cancelar = st.form_submit_button("Cancelar", use_container_width=True)

        if confirmar:
            try:
                parcela_id = repo_acordo.buscar_parcela_id(acordo.id, parcela.numero)
                if parcela_id:
                    # Se for admin, já registra e confirma de uma vez.
                    # Se for cobrança, registra como AGUARDANDO_CONFIRMACAO.
                    eh_admin = usuario.perfil == PerfilUsuario.ADMIN
                    novo_status = repo_acordo.registrar_pagamento(
                        parcela_id=parcela_id,
                        valor=valor,
                        data_pagamento=data_pgto,
                        registrado_por_id=usuario.id,
                        observacao=obs,
                        confirmado_pelo_admin=eh_admin,
                    )
                    repos_auxiliares.registrar_log(
                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                        acao="PAGAMENTO", entidade="parcela", entidade_id=parcela_id,
                        contexto=f"{acordo.numero_interno} · Parcela {parcela.numero}",
                        antes={"status_anterior": parcela.status.value},
                        depois={
                            "status_novo": novo_status.value,
                            "valor_pago": valor,
                            "data": data_pgto.isoformat(),
                            "obs": obs,
                            "confirmado_pelo_admin": eh_admin,
                        },
                    )
                    # Se TODAS parcelas quitadas → marca acordo como QUITADO
                    # (só faz sentido se foi admin que confirmou - cobrança não quita acordo)
                    if eh_admin:
                        _verificar_quitacao_acordo(acordo, usuario)
                    del st.session_state[chave]
                    if eh_admin:
                        st.session_state["detalhe_acordo_msg"] = (
                            "sucesso",
                            f"✅ Pagamento da parcela {parcela.numero} registrado e confirmado!"
                        )
                        st.toast("✅ Pagamento confirmado!", icon="✅")
                    else:
                        st.session_state["detalhe_acordo_msg"] = (
                            "sucesso",
                            f"🔵 Parcela {parcela.numero} confirmada! Aguardando admin validar."
                        )
                        st.toast("🔵 Aguardando admin", icon="🔵")
                    st.rerun()
                else:
                    st.error("❌ Parcela não encontrada.")
            except Exception as e:
                st.error(f"❌ Erro ao registrar pagamento: {e}")
                st.exception(e)
        if cancelar:
            del st.session_state[chave]
            st.rerun()


def _form_remarcar(acordo, parcela, usuario):
    """
    Form pra remarcar data de parcela (Seção 18b).

    Erick — alteração: ao remarcar, opcionalmente pode incluir juros e multa
    (mora) na nova parcela. Os percentuais aceitam 0 a infinito.
    """
    chave = f"form_remarc_{acordo.id}_{parcela.numero}"
    with st.form(f"remarc_form_{acordo.id}_{parcela.numero}"):
        st.markdown(f"#### Remarcar parcela {parcela.numero}")

        col_d, _ = st.columns([1, 1])
        with col_d:
            nova = st.date_input(
                "Nova data", value=parcela.vencimento_atual, format="DD/MM/YYYY"
            )

        st.markdown("---")
        # Checkbox: incluir juros nesta remarcação
        incluir_juros = st.checkbox(
            "💰 Incluir juros e multa nesta remarcação",
            value=False,
            help="Aplica os percentuais abaixo sobre o saldo restante da parcela. "
                 "Mesma fórmula da mora por atraso, mas você define os percentuais.",
        )

        col_j, col_m = st.columns(2)
        with col_j:
            pct_juros = st.number_input(
                "% Juros ao mês",
                min_value=0.0, max_value=10000.0,
                value=float(acordo.pct_juros_mora_mes),
                step=0.1, format="%.2f",
                disabled=not incluir_juros,
                help="Aceita 0 a ∞. Default vem do acordo.",
            )
        with col_m:
            pct_multa = st.number_input(
                "% Multa fixa",
                min_value=0.0, max_value=10000.0,
                value=float(acordo.pct_multa_mora),
                step=0.1, format="%.2f",
                disabled=not incluir_juros,
                help="Aceita 0 a ∞. Default vem do acordo.",
            )

        # Cálculo prévio (preview)
        dias_referencia = max(0, (nova - parcela.vencimento_atual).days)
        if incluir_juros and parcela.valor_restante > 0:
            saldo = parcela.valor_restante
            j = saldo * (pct_juros / 100) / 30 * dias_referencia
            m = saldo * (pct_multa / 100)
            total_novo = saldo + j + m
            st.markdown(
                f"""
<div style="background:#FFF3CD; padding:10px 14px; border-radius:6px;
            border-left:3px solid #FAC318; margin-top:8px;">
    <div style="font-size:12px; color:#666; margin-bottom:4px;">
        Pré-visualização — diferença em dias: {dias_referencia}
    </div>
    <div style="font-size:14px;">
        Saldo atual: <b>{formatar_brl(saldo)}</b><br>
        + Juros ({pct_juros:.2f}% × {dias_referencia} dias): <b>{formatar_brl(j)}</b><br>
        + Multa ({pct_multa:.2f}%): <b>{formatar_brl(m)}</b><br>
        <span style="font-size:16px; color:#041747;">
            <b>Novo valor da parcela: {formatar_brl(total_novo)}</b>
        </span>
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        col_ok, col_cancel = st.columns(2)
        with col_ok:
            confirmar = st.form_submit_button(
                "✓ Remarcar", type="primary", use_container_width=True,
            )
        with col_cancel:
            cancelar = st.form_submit_button("Cancelar", use_container_width=True)

        if confirmar:
            parcela_id = repo_acordo.buscar_parcela_id(acordo.id, parcela.numero)
            if parcela_id:
                # Calcula valor adicional se for o caso
                valor_juros_aplicado = 0.0
                valor_multa_aplicado = 0.0
                novo_valor_parcela = parcela.valor_original

                if incluir_juros and parcela.valor_restante > 0:
                    saldo = parcela.valor_restante
                    valor_juros_aplicado = round(
                        saldo * (pct_juros / 100) / 30 * dias_referencia, 2
                    )
                    valor_multa_aplicado = round(saldo * (pct_multa / 100), 2)
                    acrescimo = valor_juros_aplicado + valor_multa_aplicado
                    novo_valor_parcela = round(parcela.valor_original + acrescimo, 2)

                # Aplica no banco
                repo_acordo.remarcar_vencimento_parcela(
                    parcela_id, nova,
                    novo_valor_original=novo_valor_parcela if incluir_juros else None,
                    acrescimo_juros=valor_juros_aplicado,
                    acrescimo_multa=valor_multa_aplicado,
                )

                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                    acao="REMARCAR_PARCELA", entidade="parcela", entidade_id=parcela_id,
                    contexto=f"{acordo.numero_interno} · Parcela {parcela.numero}",
                    antes={
                        "vencimento_atual": parcela.vencimento_atual.isoformat(),
                        "valor_original": parcela.valor_original,
                    },
                    depois={
                        "vencimento_atual": nova.isoformat(),
                        "valor_original": novo_valor_parcela,
                        "juros_aplicado": valor_juros_aplicado,
                        "multa_aplicada": valor_multa_aplicado,
                        "pct_juros_usado": pct_juros if incluir_juros else None,
                        "pct_multa_usado": pct_multa if incluir_juros else None,
                    },
                )
            del st.session_state[chave]
            st.rerun()
        if cancelar:
            del st.session_state[chave]
            st.rerun()


def _verificar_quitacao_acordo(acordo, usuario):
    """Se todas parcelas estão QUITADAS, muda status do acordo pra QUITADO."""
    atual = repo_acordo.buscar_completo(acordo.id)
    if not atual:
        return
    todas_quitadas = all(p.status == StatusParcela.QUITADA for p in atual.parcelas)
    if todas_quitadas and atual.status == StatusAcordo.ATIVO:
        from src.banco.repo_acordo import atualizar_status
        atualizar_status(acordo.id, StatusAcordo.QUITADO)
        repos_auxiliares.registrar_log(
            usuario_id=usuario.id, usuario_nome=usuario.nome,
            acao="QUITAR_AUTO", entidade="acordo", entidade_id=acordo.id,
            contexto=f"{acordo.numero_interno}",
            antes={"status": "ATIVO"}, depois={"status": "QUITADO"},
        )


def _aba_titulos(acordo):
    """
    Lista de boletos do acordo, com agrupamento opcional.
    A informação de "como cada título é baixado" (parcelas alocadas + detalhe
    da distribuição P1: R$X, P2: R$Y...) só aparece para acordos JÁ FINALIZADOS,
    dentro de um "Detalhes" expansível por título.
    """
    if not acordo.boletos:
        st.info("Nenhum título registrado.")
        return

    # Só mostra info de baixa em acordos encerrados (briefing: ajuste do Erick)
    mostrar_baixa = acordo.status in (
        StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO,
    )

    agrupar = st.selectbox(
        "Agrupar por", ["Nenhum", "Parceiro", "Empresa", "Vendedor"], index=0
    )

    boletos = acordo.boletos

    def _linha(b):
        # Detalhe da baixa em texto formatado (só usado se mostrar_baixa=True)
        if mostrar_baixa and b.distribuicao:
            if len(b.distribuicao) == 1:
                detalhe_baixa = f"Baixado integralmente na parcela {b.distribuicao[0]['parcela']}"
            else:
                detalhe_baixa = "Baixa parcial em múltiplas parcelas:\n" + "\n".join(
                    f"  • Parcela {d['parcela']}: {formatar_brl(d['valor'])}"
                    for d in b.distribuicao
                )
            parc_str = " e ".join(str(n) for n in b.parcelas_alocadas)
        else:
            detalhe_baixa = None
            parc_str = ""

        # Linha resumo sempre visível
        st.markdown(
            f"""
<div style="border-bottom:1px solid #EEE; padding:8px 0; display:flex;
            justify-content:space-between; align-items:center;">
    <div style="flex:1;">
        <div style="font-weight:600;">{b.codigo_parceiro} · {b.razao_social_parceiro}</div>
        <div style="font-size:12px; color:#666;">
            E{int(b.empresa)} · {b.codigo_vendedor} {b.nome_vendedor} ·
            NF {b.numero_nota} · Nº Único {b.numero_unico}
        </div>
        <div style="font-size:12px; color:#666;">
            Venc. {formatar_data(b.vencimento)} · Atraso {b.dias_atraso} dia(s)
        </div>
    </div>
    <div style="text-align:right; min-width:180px;">
        <div>Total: <b>{formatar_brl(b.total)}</b></div>
        <div style="font-size:11px; color:#666;">
            P {formatar_brl(b.principal)} +
            J {formatar_brl(b.juros)} +
            M {formatar_brl(b.multa)}
        </div>
    </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        # "Detalhes" expansível só pra acordos encerrados (Erick - regra nova)
        if mostrar_baixa and detalhe_baixa:
            with st.expander(f"🔍 Detalhes da baixa — Parcela(s) {parc_str}", expanded=False):
                st.text(detalhe_baixa)

    if agrupar == "Nenhum":
        for b in boletos:
            _linha(b)
    else:
        chave_map = {
            "Parceiro": lambda b: f"{b.codigo_parceiro} — {b.razao_social_parceiro}",
            "Empresa": lambda b: f"Empresa {int(b.empresa)}",
            "Vendedor": lambda b: f"{b.codigo_vendedor} — {b.nome_vendedor}",
        }
        chave = chave_map[agrupar]
        grupos = {}
        for b in boletos:
            grupos.setdefault(chave(b), []).append(b)
        for nome_grupo, items in grupos.items():
            sub_p = sum(b.principal for b in items)
            sub_t = sum(b.total for b in items)
            st.markdown(
                f"<div style='background:#F2F2F2; padding:6px 12px; border-radius:4px; "
                f"font-weight:600; margin-top:10px;'>"
                f"{nome_grupo} — {len(items)} título(s) — "
                f"Principal {formatar_brl(sub_p)} · Total {formatar_brl(sub_t)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            for b in items:
                _linha(b)


def _aba_cadastro(acordo, usuario):
    """
    Aba Cadastro do Cliente.
    Mostra todos os dados do cliente do acordo. Permite edição (todos os perfis).
    Inclui campo 'Tem WhatsApp' ao lado do telefone.
    """
    from src.banco import repo_cliente
    from src.banco import repos_auxiliares

    cliente = repo_cliente.buscar_por_id(acordo.cliente_id)
    if cliente is None:
        st.error("Cliente não encontrado.")
        return

    # Flag de edição
    chave_edit = f"editando_cliente_{cliente.id}"
    em_edicao = st.session_state.get(chave_edit, False)

    # ====== MODO VISUALIZAÇÃO ======
    if not em_edicao:
        col_titulo, col_btn = st.columns([4, 1])
        with col_titulo:
            st.markdown("### Dados do Cliente")
        with col_btn:
            if st.button("✏ Editar", use_container_width=True, key=f"btn_edit_{cliente.id}"):
                st.session_state[chave_edit] = True
                st.rerun()

        # Campos em colunas
        col1, col2 = st.columns(2)
        with col1:
            _campo_visualizar("Razão Social", cliente.nome_principal)
            _campo_visualizar("CNPJ", cliente.cnpj or "—")
            _campo_visualizar("Contato (nome)", cliente.contato or "—")
        with col2:
            _campo_visualizar("E-mail de cobrança", cliente.email_cobranca or "—")
            # Telefone + WhatsApp
            telefone_str = cliente.telefone or "—"
            if cliente.telefone and cliente.tem_whatsapp:
                telefone_str = (
                    f"{cliente.telefone} "
                    f"<span style='background:#25D366; color:white; padding:2px 8px; "
                    f"border-radius:10px; font-size:11px; font-weight:600;'>"
                    f"📱 WhatsApp</span>"
                )
            _campo_visualizar("Telefone", telefone_str, html=True)
            _campo_visualizar("Cliente desde", formatar_data(cliente.criado_em))

        return

    # ====== MODO EDIÇÃO ======
    st.markdown("### Editar Cadastro do Cliente")
    st.caption("Altere os dados abaixo e clique em Salvar.")

    with st.form(f"form_edit_cliente_{cliente.id}"):
        col1, col2 = st.columns(2)
        with col1:
            novo_nome = st.text_input(
                "Razão Social *", value=cliente.nome_principal,
            )
            novo_cnpj = st.text_input("CNPJ", value=cliente.cnpj or "")
            novo_contato = st.text_input("Contato (nome)", value=cliente.contato or "")
        with col2:
            novo_email = st.text_input(
                "E-mail de cobrança", value=cliente.email_cobranca or "",
            )
            col_tel, col_wpp = st.columns([3, 1])
            with col_tel:
                novo_telefone = st.text_input(
                    "Telefone", value=cliente.telefone or "",
                    placeholder="(21) 99999-9999",
                )
            with col_wpp:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                novo_whatsapp = st.checkbox(
                    "📱 WhatsApp",
                    value=cliente.tem_whatsapp,
                    help="Marque se o telefone também é WhatsApp",
                )

        st.markdown("---")
        col_salvar, col_cancelar = st.columns([1, 1])
        with col_salvar:
            salvar = st.form_submit_button(
                "💾 Salvar alterações",
                type="primary", use_container_width=True,
            )
        with col_cancelar:
            cancelar = st.form_submit_button(
                "Cancelar", use_container_width=True,
            )

        if salvar:
            if not novo_nome.strip():
                st.error("Razão Social não pode ficar vazia.")
                return
            try:
                antes = {
                    "nome": cliente.nome_principal,
                    "cnpj": cliente.cnpj,
                    "contato": cliente.contato,
                    "email_cobranca": cliente.email_cobranca,
                    "telefone": cliente.telefone,
                    "tem_whatsapp": cliente.tem_whatsapp,
                }
                atualizado = repo_cliente.atualizar(
                    cliente_id=cliente.id,
                    nome_principal=novo_nome,
                    cnpj=novo_cnpj,
                    contato=novo_contato,
                    email_cobranca=novo_email,
                    telefone=novo_telefone,
                    tem_whatsapp=novo_whatsapp,
                )
                depois = {
                    "nome": atualizado.nome_principal,
                    "cnpj": atualizado.cnpj,
                    "contato": atualizado.contato,
                    "email_cobranca": atualizado.email_cobranca,
                    "telefone": atualizado.telefone,
                    "tem_whatsapp": atualizado.tem_whatsapp,
                }
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id,
                    usuario_nome=usuario.nome,
                    acao="EDITAR_CLIENTE",
                    entidade="cliente",
                    entidade_id=cliente.id,
                    contexto=atualizado.nome_principal,
                    antes=antes,
                    depois=depois,
                )
                st.session_state[chave_edit] = False
                st.success("✓ Cadastro atualizado com sucesso!")
                st.rerun()
            except ValueError as e:
                st.error(f"❌ {e}")

        if cancelar:
            st.session_state[chave_edit] = False
            st.rerun()


def _campo_visualizar(label: str, valor: str, html: bool = False):
    """Renderiza um campo em modo visualização (label + valor)."""
    valor_renderizado = valor if html else (valor or "—")
    st.markdown(
        f"""
<div style="margin-bottom: 16px;">
    <div style="font-size: 11px; color: #888;
                letter-spacing: 0.5px; text-transform: uppercase;
                margin-bottom: 4px;">
        {label}
    </div>
    <div style="font-size: 15px; color: #222; font-weight: 500;">
        {valor_renderizado}
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _aba_comentarios(acordo, usuario):
    """
    Histórico de anotações e tentativas de contato no acordo.
    Cada usuário pode criar comentários. Excluir só o próprio.
    """
    from src.banco import repo_extras, repo_cliente

    st.markdown("### Anotações e contatos")
    st.caption(
        "Use pra registrar tentativas de contato, conversas e observações "
        "importantes sobre este acordo."
    )

    # Buscar cliente pra montar link de WhatsApp se aplicável
    cliente = repo_cliente.buscar_por_id(acordo.cliente_id)

    # ============ Formulário pra novo comentário ============
    with st.expander("➕ Adicionar novo comentário", expanded=False):
        with st.form(f"form_comentario_{acordo.id}", clear_on_submit=True):
            col1, col2 = st.columns([1, 3])
            with col1:
                tipo = st.selectbox(
                    "Tipo",
                    options=["NOTA", "LIGACAO", "WHATSAPP", "EMAIL", "VISITA", "OUTRO"],
                    format_func=lambda t: {
                        "NOTA": "📝 Nota",
                        "LIGACAO": "📞 Ligação",
                        "WHATSAPP": "💬 WhatsApp",
                        "EMAIL": "📧 E-mail",
                        "VISITA": "🚪 Visita",
                        "OUTRO": "📎 Outro",
                    }[t],
                )
            with col2:
                texto = st.text_area(
                    "Texto",
                    placeholder="Ex: Liguei e prometeu pagar dia 15. Falar com Maria.",
                    height=80,
                )
            salvar = st.form_submit_button(
                "💾 Salvar comentário",
                type="primary",
                use_container_width=True,
            )

            if salvar:
                if not texto.strip():
                    st.error("❌ Escreva o texto do comentário.")
                else:
                    try:
                        repo_extras.adicionar_comentario(
                            acordo_id=acordo.id,
                            usuario_id=usuario.id,
                            usuario_nome=usuario.nome,
                            tipo=tipo,
                            texto=texto,
                        )
                        st.success("✓ Comentário adicionado!")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")

    # ============ Botão WhatsApp pronto (Erick - feature 2) ============
    if cliente and cliente.telefone and cliente.tem_whatsapp:
        # Limpa o telefone pra ficar só números
        tel_limpo = "".join(c for c in cliente.telefone if c.isdigit())
        if not tel_limpo.startswith("55") and len(tel_limpo) >= 10:
            tel_limpo = "55" + tel_limpo

        # Encontra próxima parcela em aberto
        prox = None
        for p in sorted(acordo.parcelas, key=lambda x: x.vencimento_atual):
            if p.status != StatusParcela.QUITADA:
                prox = p
                break

        if prox:
            mensagem = (
                f"Olá! Estamos entrando em contato sobre o acordo "
                f"{acordo.numero_interno} da {cliente.nome_principal}. "
                f"Lembrando que a parcela {prox.numero} no valor de "
                f"R$ {prox.valor_original:,.2f} vence em "
                f"{formatar_data(prox.vencimento_atual)}. "
                f"Qualquer dúvida estou à disposição."
            ).replace(",", "X").replace(".", ",").replace("X", ".")  # formato BR

            import urllib.parse
            url_whatsapp = (
                f"https://wa.me/{tel_limpo}?text={urllib.parse.quote(mensagem)}"
            )

            st.markdown(
                f"""
<a href="{url_whatsapp}" target="_blank" style="text-decoration:none;">
    <div style="background:#25D366; color:white; padding:12px 18px;
                border-radius:6px; text-align:center; margin:12px 0;
                font-weight:600;">
        💬 Abrir WhatsApp com mensagem pronta de cobrança
    </div>
</a>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ============ Lista de comentários ============
    comentarios = repo_extras.listar_comentarios(acordo.id)
    if not comentarios:
        st.info("Nenhum comentário ainda. Use o formulário acima pra adicionar o primeiro.")
        return

    icones = {
        "NOTA": "📝", "LIGACAO": "📞", "WHATSAPP": "💬",
        "EMAIL": "📧", "VISITA": "🚪", "OUTRO": "📎",
    }
    labels = {
        "NOTA": "Nota", "LIGACAO": "Ligação", "WHATSAPP": "WhatsApp",
        "EMAIL": "E-mail", "VISITA": "Visita", "OUTRO": "Outro",
    }

    for c in comentarios:
        icone = icones.get(c["tipo"], "📝")
        label = labels.get(c["tipo"], "Comentário")
        data_str = formatar_data(c["criado_em"])
        hora_str = formatar_hora(c["criado_em"])

        col_card, col_btn = st.columns([5, 1])
        with col_card:
            st.markdown(
                f"""
<div style="background:#F8F9FA; border-left:3px solid #041747;
            padding:10px 14px; margin-bottom:8px; border-radius:4px;">
    <div style="font-size:12px; color:#666; margin-bottom:4px;">
        {icone} <b>{label}</b> · {c.get('usuario_nome_snapshot') or 'Sistema'}
        · {data_str} {hora_str}
    </div>
    <div style="font-size:14px; color:#222; white-space:pre-wrap;">
        {c['texto']}
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
        with col_btn:
            # Só permite excluir o próprio comentário
            if c["usuario_id"] == usuario.id:
                if st.button("🗑", key=f"del_com_{c['id']}", help="Excluir comentário"):
                    try:
                        repo_extras.excluir_comentario(c["id"], usuario.id)
                        st.toast("✅ Comentário excluído", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao excluir: {e}")


def _aba_promessas(acordo, usuario):
    """
    Promessas de pagamento. Cliente prometeu pagar tal dia →
    cadastra aqui e depois confirma se cumpriu ou quebrou.
    """
    from src.banco import repo_extras
    from datetime import date as _date

    st.markdown("### Promessas de pagamento")
    st.caption(
        "Quando o cliente prometer pagar em uma data, registre aqui. "
        "A promessa aparece no Início no dia certo, e fica destacada se for "
        "quebrada."
    )

    # ============ Formulário ============
    with st.expander("➕ Registrar nova promessa", expanded=False):
        with st.form(f"form_promessa_{acordo.id}", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                data_prometida = st.date_input(
                    "Data prometida *",
                    value=_date.today(),
                    format="DD/MM/YYYY",
                )
            with col2:
                valor_prometido = st.number_input(
                    "Valor prometido (R$)",
                    min_value=0.0, value=0.0, step=100.0, format="%.2f",
                    help="Opcional. Deixe 0 se não souber o valor exato.",
                )

            observacao = st.text_area(
                "Observação",
                placeholder="Ex: Cliente disse que recebe pagamento de cliente dele dia 14",
                height=80,
            )

            salvar = st.form_submit_button(
                "💾 Registrar promessa",
                type="primary",
                use_container_width=True,
            )

            if salvar:
                try:
                    repo_extras.criar_promessa(
                        acordo_id=acordo.id,
                        data_prometida=data_prometida,
                        valor_prometido=valor_prometido if valor_prometido > 0 else None,
                        observacao=observacao.strip() or None,
                        usuario_id=usuario.id,
                        usuario_nome=usuario.nome,
                    )
                    st.success("✓ Promessa registrada!")
                    st.rerun()
                except ValueError as e:
                    st.error(f"❌ {e}")

    # ============ Lista ============
    promessas = repo_extras.listar_promessas_do_acordo(acordo.id)
    if not promessas:
        st.info("Nenhuma promessa registrada ainda.")
        return

    hoje = _date.today().isoformat()
    for p in promessas:
        data_p = p["data_prometida"][:10]
        status = p["status"]
        eh_quebrada = (status == "AGUARDANDO" and data_p < hoje)

        # Cor e ícone por status
        if status == "CUMPRIDA":
            cor = "#28A745"; icone = "✅"; label = "Cumprida"
        elif status == "QUEBRADA" or eh_quebrada:
            cor = "#DC3545"; icone = "❌"; label = "Quebrada"
        elif status == "CANCELADA":
            cor = "#6C757D"; icone = "🚫"; label = "Cancelada"
        else:
            cor = "#FFC107"; icone = "⏳"; label = "Aguardando"

        valor_str = (
            f"R$ {p['valor_prometido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if p.get("valor_prometido") else "Sem valor definido"
        )
        obs_str = p.get("observacao") or ""

        col_p, col_acoes = st.columns([4, 2])
        with col_p:
            st.markdown(
                f"""
<div style="background:#F8F9FA; border-left:3px solid {cor};
            padding:10px 14px; margin-bottom:8px; border-radius:4px;">
    <div style="font-weight:600;">
        {icone} {label} · {formatar_data(data_p)} · {valor_str}
    </div>
    <div style="font-size:12px; color:#666;">
        Registrada por {p.get('usuario_nome_snapshot') or '—'}
        em {formatar_data(p['criado_em'])}
    </div>
    {f'<div style="font-size:13px; color:#444; margin-top:6px;">"{obs_str}"</div>' if obs_str else ''}
</div>
                """,
                unsafe_allow_html=True,
            )
        with col_acoes:
            if status == "AGUARDANDO":
                col_ok, col_no = st.columns(2)
                with col_ok:
                    if st.button("✅ Cumpriu", key=f"prom_ok_{p['id']}", use_container_width=True):
                        repo_extras.atualizar_status_promessa(p["id"], "CUMPRIDA")
                        st.rerun()
                with col_no:
                    if st.button("❌ Quebrou", key=f"prom_no_{p['id']}", use_container_width=True):
                        repo_extras.atualizar_status_promessa(p["id"], "QUEBRADA")
                        st.rerun()


def _aba_historico(acordo, usuario):
    """Lista dos logs de auditoria desse acordo."""
    if usuario.perfil == PerfilUsuario.COBRANCA:
        st.info(
            "A aba de Histórico Detalhado é restrita a Administradores e Diretoria. "
            "Você pode ver os pagamentos individuais clicando nas parcelas."
        )
        return

    from src.banco.conexao import obter_conexao
    cur = obter_conexao().execute(
        """
        SELECT * FROM log_auditoria
        WHERE (entidade = 'acordo' AND entidade_id = ?)
           OR (entidade IN ('parcela', 'pagamento_parcela')
               AND entidade_id IN (SELECT id FROM parcela WHERE acordo_id = ?))
        ORDER BY timestamp DESC
        LIMIT 200;
        """,
        (acordo.id, acordo.id),
    )
    logs = [dict(r) for r in cur.fetchall()]
    if not logs:
        st.caption("Sem eventos registrados ainda.")
        return

    for l in logs:
        with st.container():
            st.markdown(
                f"""
<div style="border-left:3px solid {AZUL_ESCURO}; padding:6px 12px; margin-bottom:6px;">
    <div style="font-size:13px;">
        <b>{l['acao']}</b> · {l['entidade']}
        <span style="color:#666;"> · por {l['usuario_nome_snapshot'] or '—'}</span>
    </div>
    <div style="font-size:11px; color:#666;">
        {l['timestamp']} · {l['contexto'] or ''}
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )


def _confirmar_mudanca_status(acordo, usuario, novo: StatusAcordo, msg: str):
    chave = f"confirmar_{'quebra' if novo == StatusAcordo.QUEBRADO else 'cancelar'}_{acordo.id}"
    st.warning(msg)
    cc1, cc2, _ = st.columns([1, 1, 4])
    with cc1:
        if st.button(
            f"✓ Sim, {novo.value.lower()}",
            type="primary",
            key=f"sim_{chave}",
        ):
            try:
                from src.banco.repo_acordo import atualizar_status
                atualizar_status(acordo.id, novo)
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                    acao=f"ALTERAR_STATUS_{novo.value}",
                    entidade="acordo", entidade_id=acordo.id,
                    contexto=acordo.numero_interno,
                    antes={"status": acordo.status.value},
                    depois={"status": novo.value},
                )
                del st.session_state[chave]
                st.session_state["detalhe_acordo_msg"] = (
                    "sucesso",
                    f"✅ Acordo {acordo.numero_interno} marcado como {novo.value}!"
                )
                st.toast(f"✅ Status alterado pra {novo.value}", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao alterar status: {e}")
                st.exception(e)
    with cc2:
        if st.button("Não", key=f"nao_{chave}"):
            del st.session_state[chave]
            st.rerun()


# ============================================================
# EXPORTADORES — 4 PDFs oficiais LLE
# ============================================================
# - Proposta de Acordo: gerada na Calculadora (não aqui)
# - Termo de Acordo: aqui, sempre disponível
# - Termo de Confissão: aqui, sempre disponível
# - Carta de Quitação: aqui, só se acordo QUITADO

def _botoes_exportar_documentos(acordo, usuario):
    """Renderiza os 3 botões de PDFs disponíveis no detalhe do acordo."""
    from src.servicos.exportador_pdf import (
        gerar_pdf_termo_acordo,
        gerar_pdf_termo_confissao,
        gerar_pdf_carta_quitacao,
    )
    from src.utils.formatadores import slugificar
    from src.banco.repo_cliente import buscar_por_id

    cliente = buscar_por_id(acordo.cliente_id)
    cli_endereco = None
    cli_bairro = None
    cli_cidade = None
    cli_uf = None
    cli_cnpj = cliente.cnpj if cliente else None
    # No banco atual o cliente só tem endereço como string única, simplificado
    # (poderia ser separado por campos no futuro)

    slug = slugificar(acordo.cliente_nome)
    data_str = datetime.now().strftime("%Y%m%d")

    is_quitado = acordo.status == StatusAcordo.QUITADO

    # Layout: 3 colunas (Termo · Confissão · Quitação se quitado)
    if is_quitado:
        c1, c2, c3 = st.columns(3)
    else:
        c1, c2 = st.columns(2)

    with c1:
        if st.button("📋 Termo de Acordo", use_container_width=True,
                     key=f"btn_termo_{acordo.id}"):
            pdf = gerar_pdf_termo_acordo(
                cliente_nome=acordo.cliente_nome,
                cliente_cnpj=cli_cnpj,
                cliente_endereco=cli_endereco,
                cliente_bairro=cli_bairro,
                cliente_cidade=cli_cidade,
                cliente_uf=cli_uf,
                boletos=acordo.boletos,
                parcelas=acordo.parcelas,
                tipo_cobranca=acordo.tipo_cobranca.value,
            )
            st.session_state[f"pdf_termo_bytes_{acordo.id}"] = pdf
            st.session_state[f"pdf_termo_nome_{acordo.id}"] = (
                f"TermoAcordo_{slug}_{data_str}.pdf"
            )
            repos_auxiliares.registrar_log(
                usuario_id=usuario.id, usuario_nome=usuario.nome,
                acao="EXPORTAR_TERMO_ACORDO", entidade="acordo",
                entidade_id=acordo.id, contexto=acordo.numero_interno,
            )

        if f"pdf_termo_bytes_{acordo.id}" in st.session_state:
            st.download_button(
                "⬇ Baixar Termo",
                data=st.session_state[f"pdf_termo_bytes_{acordo.id}"],
                file_name=st.session_state[f"pdf_termo_nome_{acordo.id}"],
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_termo_{acordo.id}",
            )

    with c2:
        if st.button("📜 Termo de Confissão", use_container_width=True,
                     key=f"btn_conf_{acordo.id}"):
            pdf = gerar_pdf_termo_confissao(
                cliente_nome=acordo.cliente_nome,
                cliente_cnpj=cli_cnpj,
                cliente_endereco=cli_endereco,
                cliente_bairro=cli_bairro,
                cliente_cidade=cli_cidade,
                cliente_uf=cli_uf,
                boletos=acordo.boletos,
                parcelas=acordo.parcelas,
                tipo_cobranca="Boleto Bancário",
            )
            st.session_state[f"pdf_conf_bytes_{acordo.id}"] = pdf
            st.session_state[f"pdf_conf_nome_{acordo.id}"] = (
                f"TermoConfissao_{slug}_{data_str}.pdf"
            )
            repos_auxiliares.registrar_log(
                usuario_id=usuario.id, usuario_nome=usuario.nome,
                acao="EXPORTAR_TERMO_CONFISSAO", entidade="acordo",
                entidade_id=acordo.id, contexto=acordo.numero_interno,
            )

        if f"pdf_conf_bytes_{acordo.id}" in st.session_state:
            st.download_button(
                "⬇ Baixar Confissão",
                data=st.session_state[f"pdf_conf_bytes_{acordo.id}"],
                file_name=st.session_state[f"pdf_conf_nome_{acordo.id}"],
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_conf_{acordo.id}",
            )

    if is_quitado:
        with c3:
            if st.button("✅ Carta de Quitação", use_container_width=True,
                         key=f"btn_quit_{acordo.id}", type="primary"):
                pdf = gerar_pdf_carta_quitacao(
                    cliente_nome=acordo.cliente_nome,
                    cliente_cnpj=cli_cnpj,
                    boletos=acordo.boletos,
                    nome_signatario=usuario.nome,
                )
                st.session_state[f"pdf_quit_bytes_{acordo.id}"] = pdf
                st.session_state[f"pdf_quit_nome_{acordo.id}"] = (
                    f"CartaQuitacao_{slug}_{data_str}.pdf"
                )
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                    acao="EXPORTAR_CARTA_QUITACAO", entidade="acordo",
                    entidade_id=acordo.id, contexto=acordo.numero_interno,
                )

            if f"pdf_quit_bytes_{acordo.id}" in st.session_state:
                st.download_button(
                    "⬇ Baixar Quitação",
                    data=st.session_state[f"pdf_quit_bytes_{acordo.id}"],
                    file_name=st.session_state[f"pdf_quit_nome_{acordo.id}"],
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_quit_{acordo.id}",
                )


def _botao_exportar_xlsx(acordo, usuario):
    from src.servicos.exportador_xlsx import gerar_xlsx_acordo
    from src.utils.formatadores import slugificar

    nome_arq = f"Acordo_{slugificar(acordo.cliente_nome)}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    if st.button("📊 XLSX", use_container_width=True):
        xlsx = gerar_xlsx_acordo(
            numero_acordo=acordo.numero_interno,
            cliente_nome=acordo.cliente_nome,
            negociador_nome=acordo.negociador_nome,
            data_acordo=acordo.data_acordo,
            data_emissao=date.today(),
            pct_juros_titulos=acordo.pct_juros_mes_titulos,
            pct_multa_titulos=acordo.pct_multa_titulos,
            pct_juros_mora=acordo.pct_juros_mora_mes,
            pct_multa_mora=acordo.pct_multa_mora,
            tipo_cobranca=acordo.tipo_cobranca.value,
            boletos=acordo.boletos,
            parcelas=acordo.parcelas,
        )
        st.session_state[f"xlsx_bytes_{acordo.id}"] = xlsx
        st.session_state[f"xlsx_nome_{acordo.id}"] = nome_arq
        repos_auxiliares.registrar_log(
            usuario_id=usuario.id, usuario_nome=usuario.nome,
            acao="EXPORTAR_XLSX", entidade="acordo",
            entidade_id=acordo.id, contexto=acordo.numero_interno,
        )

    if f"xlsx_bytes_{acordo.id}" in st.session_state:
        st.download_button(
            "⬇ Baixar XLSX",
            data=st.session_state[f"xlsx_bytes_{acordo.id}"],
            file_name=st.session_state[f"xlsx_nome_{acordo.id}"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_xlsx_{acordo.id}",
        )


def _bloco_alterar_negociador(acordo, usuario):
    """
    Bloco compacto pra alterar o negociador responsável pelo acordo.
    Funciona como dropdown que abre, mostra lista de negociadores ativos,
    e ao confirmar atualiza no banco + registra log.
    """
    from src.banco import repo_usuario, repo_acordo as _rep_ac
    from src.banco import repos_auxiliares as _aux

    chave_aberto = f"alterar_neg_{acordo.id}"

    if not st.session_state.get(chave_aberto):
        col_a, _ = st.columns([2, 6])
        with col_a:
            if st.button(
                f"🔄 Alterar negociador",
                use_container_width=True,
                key=f"btn_alterar_neg_{acordo.id}",
                help=f"Atual: {acordo.negociador_nome}",
            ):
                st.session_state[chave_aberto] = True
                st.rerun()
        return

    # Aberto — mostra dropdown e botões
    st.info(f"**Negociador atual:** {acordo.negociador_nome}")

    try:
        negociadores = repo_usuario.listar_negociadores_ativos()
    except Exception as e:
        st.error(f"❌ Erro ao listar negociadores: {e}")
        del st.session_state[chave_aberto]
        return

    if not negociadores:
        st.error("❌ Nenhum negociador ativo encontrado.")
        del st.session_state[chave_aberto]
        return

    opcoes = {f"{n.nome} ({n.perfil.value})": n.id for n in negociadores}
    # Identifica o índice do atual pra default
    nome_atual = next(
        (k for k, v in opcoes.items() if v == acordo.negociador_id),
        list(opcoes.keys())[0]
    )
    novo_label = st.selectbox(
        "Novo negociador:",
        list(opcoes.keys()),
        index=list(opcoes.keys()).index(nome_atual),
        key=f"sel_novo_neg_{acordo.id}",
    )
    novo_id = opcoes[novo_label]

    col_ok, col_cancel, _ = st.columns([1, 1, 4])
    with col_ok:
        if st.button(
            "✓ Confirmar alteração",
            type="primary",
            use_container_width=True,
            key=f"conf_alterar_neg_{acordo.id}",
        ):
            try:
                resultado = _rep_ac.alterar_negociador_acordo(acordo.id, novo_id)

                if resultado.get("sem_mudanca"):
                    st.session_state["detalhe_acordo_msg"] = (
                        "aviso",
                        "ℹ️ Nenhuma mudança — o negociador escolhido já é o atual."
                    )
                else:
                    # Registra log
                    _aux.registrar_log(
                        usuario_id=usuario.id,
                        usuario_nome=usuario.nome,
                        acao="ALTERAR_NEGOCIADOR",
                        entidade="acordo",
                        entidade_id=acordo.id,
                        contexto=acordo.numero_interno,
                        antes={
                            "negociador_id": resultado["negociador_anterior_id"],
                            "negociador_nome": resultado["negociador_anterior_nome"],
                        },
                        depois={
                            "negociador_id": resultado["negociador_novo_id"],
                            "negociador_nome": resultado["negociador_novo_nome"],
                        },
                    )
                    st.session_state["detalhe_acordo_msg"] = (
                        "sucesso",
                        f"✅ Negociador alterado de **{resultado['negociador_anterior_nome']}** "
                        f"para **{resultado['negociador_novo_nome']}**."
                    )
                    st.toast("✅ Negociador alterado!", icon="✅")

                del st.session_state[chave_aberto]
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao alterar negociador: {e}")
                st.exception(e)
    with col_cancel:
        if st.button(
            "Cancelar",
            use_container_width=True,
            key=f"cancel_alterar_neg_{acordo.id}",
        ):
            del st.session_state[chave_aberto]
            st.rerun()
