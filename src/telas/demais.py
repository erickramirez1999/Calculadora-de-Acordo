"""
Telas restantes do briefing — agrupadas para entrega completa.
Cada função renderiza uma página inteira.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from src.banco import repo_acordo, repo_usuario, repos_auxiliares
from src.modelos.tipos import PerfilUsuario, StatusAcordo
from src.utils.estilo import badge_status_acordo
from src.utils.formatadores import formatar_brl, formatar_data, normalizar_busca
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE
from src.utils.traducoes import traduzir_acao, traduzir_perfil, traduzir_status_acordo


# ============================================================
# 1) FINALIZADOS (Seção 26)
# ============================================================

def renderizar_finalizados(usuario):
    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>📁 Acordos Finalizados</h1>", unsafe_allow_html=True)

    finalizados = repo_acordo.listar_resumos(
        status_em=[StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO]
    )

    if not finalizados:
        st.info("Ainda não há acordos encerrados.")
        return

    # Indicadores
    qtd_quitados = sum(1 for a in finalizados if a.status == StatusAcordo.QUITADO)
    qtd_quebrados = sum(1 for a in finalizados if a.status == StatusAcordo.QUEBRADO)
    qtd_cancelados = sum(1 for a in finalizados if a.status == StatusAcordo.CANCELADO)
    valor_quitado = sum(a.valor_total for a in finalizados if a.status == StatusAcordo.QUITADO)
    valor_perdido = sum(a.saldo_devedor for a in finalizados if a.status == StatusAcordo.QUEBRADO)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total encerrados", str(len(finalizados)))
    c2.metric("Quitados", str(qtd_quitados))
    c3.metric("Quebrados", str(qtd_quebrados))
    c4.metric("Valor quitado", formatar_brl(valor_quitado))
    c5.metric("Perdido (quebra)", formatar_brl(valor_perdido))

    st.markdown("---")

    # Filtros
    col_b, col_s = st.columns([3, 1])
    with col_b:
        termo = st.text_input("🔍 Buscar", placeholder="Parceiro, Negociador, NF, número do acordo...")
    with col_s:
        filtro_status = st.selectbox(
            "Status", ["Todos", "Quitado", "Quebrado", "Cancelado"]
        )

    lista = finalizados
    if filtro_status != "Todos":
        mapa = {"Quitado": StatusAcordo.QUITADO, "Quebrado": StatusAcordo.QUEBRADO, "Cancelado": StatusAcordo.CANCELADO}
        lista = [a for a in lista if a.status == mapa[filtro_status]]
    if termo.strip():
        t = normalizar_busca(termo)
        lista = [
            a for a in lista
            if t in normalizar_busca(a.cliente_nome)
               or t in normalizar_busca(a.negociador_nome)
               or t in normalizar_busca(a.numero_interno)
        ]

    st.markdown(f"### Resultados ({len(lista)})")
    for a in lista:
        col_d, col_v, col_st, col_btn = st.columns([3, 1.5, 1.2, 1])
        with col_d:
            st.markdown(f"**{a.numero_interno}** · {a.cliente_nome}")
            st.caption(f"Negociador: {a.negociador_nome} · Encerrado em: {formatar_data(a.data_encerramento) if a.data_encerramento else '—'}")
        with col_v:
            st.markdown(f"Valor: **{formatar_brl(a.valor_total)}**")
        with col_st:
            st.markdown(badge_status_acordo(a.status.value), unsafe_allow_html=True)
        with col_btn:
            if st.button("Abrir", key=f"fin_{a.id}", use_container_width=True):
                st.session_state["acordo_id_aberto"] = a.id
                st.rerun()
        st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)


# ============================================================
# 2) NEGOCIADORES (Seção 24)
# ============================================================

def renderizar_negociadores(usuario):
    if usuario.perfil not in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
        st.error("Acesso restrito a Administradores e Diretoria.")
        return

    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>👥 Usuários do Sistema</h1>", unsafe_allow_html=True)
    st.caption(
        "Quando alguém se cadastra no sistema, fica em **status pendente** até "
        "você aprovar. Clique em **✅ Aprovar** ao lado de cada usuário pendente "
        "pra liberar o acesso imediatamente."
    )

    busca = st.text_input("🔍 Buscar por nome ou e-mail")
    usuarios = repo_usuario.listar_todos()
    if busca.strip():
        t = normalizar_busca(busca)
        usuarios = [u for u in usuarios if t in normalizar_busca(u.nome) or t in normalizar_busca(u.email)]

    # Pendentes em destaque
    pendentes = [u for u in usuarios if not u.aprovado and u.ativo]
    if pendentes:
        st.warning(
            f"⏳ **{len(pendentes)} usuário(s) aguardando aprovação.** "
            "Use o botão verde **Aprovar** ao lado de cada nome."
        )

    st.markdown("---")

    for u in usuarios:
        qtd_acordos = repo_usuario.contar_acordos_do_negociador(u.id)
        if not u.ativo:
            status_label = "⚫ Inativo"
            status_cor = "#6C757D"
        elif not u.aprovado:
            status_label = "⏳ Pendente aprovação"
            status_cor = "#856404"
        else:
            status_label = "🟢 Ativo"
            status_cor = "#155724"

        # Layout: dados + status + ações
        col_dados, col_status, col_acoes = st.columns([4, 1.5, 2.5])

        with col_dados:
            st.markdown(f"**{u.nome}**")
            st.caption(f"{u.email} · `{traduzir_perfil(u.perfil.value)}` · {qtd_acordos} acordo(s)")
            st.caption(f"Cadastro: {formatar_data(u.criado_em)}")

        with col_status:
            st.markdown(
                f"<div style='padding-top:8px;'>"
                f"<span style='color:{status_cor}; font-weight:600;'>{status_label}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_acoes:
            # ============ Usuário PENDENTE ============
            if not u.aprovado and u.ativo:
                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button(
                        "✅ Aprovar", key=f"apr_{u.id}",
                        type="primary", use_container_width=True,
                    ):
                        repo_usuario.aprovar_usuario(u.id)
                        repos_auxiliares.registrar_log(
                            usuario_id=usuario.id, usuario_nome=usuario.nome,
                            acao="APROVAR_USUARIO", entidade="usuario",
                            entidade_id=u.id,
                            contexto=u.nome,
                            antes={"aprovado": False},
                            depois={"aprovado": True},
                        )
                        st.success(f"✅ {u.nome.split()[0]} aprovado!")
                        st.rerun()
                with col_r:
                    if st.button(
                        "❌ Recusar", key=f"rec_{u.id}",
                        use_container_width=True,
                    ):
                        st.session_state[f"conf_recusar_{u.id}"] = True

            # ============ Usuário JÁ APROVADO ============
            elif u.aprovado and u.ativo:
                # 4 botões em 2 linhas: Inativar, Revogar, Senha, Nome
                col_b, col_c = st.columns(2)
                with col_b:
                    # Não permite o próprio admin inativar a si mesmo
                    if u.id == usuario.id:
                        st.caption("(você)")
                    else:
                        if st.button(
                            "Inativar", key=f"inat_{u.id}",
                            use_container_width=True,
                        ):
                            repo_usuario.inativar_usuario(u.id)
                            repos_auxiliares.registrar_log(
                                usuario_id=usuario.id, usuario_nome=usuario.nome,
                                acao="INATIVAR_USUARIO", entidade="usuario",
                                entidade_id=u.id, contexto=u.nome,
                            )
                            st.rerun()
                with col_c:
                    if u.id != usuario.id:
                        if st.button(
                            "🔒 Revogar", key=f"rev_{u.id}",
                            use_container_width=True,
                            help="Volta usuário pra status pendente",
                        ):
                            repo_usuario.revogar_aprovacao(u.id)
                            repos_auxiliares.registrar_log(
                                usuario_id=usuario.id, usuario_nome=usuario.nome,
                                acao="REVOGAR_APROVACAO", entidade="usuario",
                                entidade_id=u.id, contexto=u.nome,
                            )
                            st.rerun()
                # 2ª linha
                col_d, col_e, col_f = st.columns(3)
                with col_d:
                    if st.button(
                        "🔑 Senha", key=f"reset_pwd_{u.id}",
                        use_container_width=True,
                        help="Redefinir senha desse usuário",
                    ):
                        st.session_state[f"reset_pwd_form_{u.id}"] = True
                with col_e:
                    if st.button(
                        "✏ Nome", key=f"edit_nome_{u.id}",
                        use_container_width=True,
                        help="Alterar o nome do usuário",
                    ):
                        st.session_state[f"edit_nome_form_{u.id}"] = True
                with col_f:
                    if st.button(
                        "🎖 Cargo", key=f"edit_perfil_{u.id}",
                        use_container_width=True,
                        help="Promover ou rebaixar o cargo do usuário",
                    ):
                        st.session_state[f"edit_perfil_form_{u.id}"] = True

            # ============ Usuário INATIVO ============
            else:
                if st.button(
                    "🔄 Reativar", key=f"react_{u.id}",
                    use_container_width=True,
                ):
                    repo_usuario.reativar_usuario(u.id)
                    repos_auxiliares.registrar_log(
                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                        acao="REATIVAR_USUARIO", entidade="usuario",
                        entidade_id=u.id, contexto=u.nome,
                    )
                    st.rerun()

        # ============ Formulário de alterar CARGO/PERFIL ============
        if st.session_state.get(f"edit_perfil_form_{u.id}"):
            # Avisa quando for o próprio admin se rebaixando (deixa passar mas com cuidado)
            aviso_proprio = ""
            if u.id == usuario.id:
                aviso_proprio = (
                    "<br><b style='color:#856404;'>⚠ Atenção:</b> você está alterando "
                    "o SEU PRÓPRIO cargo. Se rebaixar, vai perder acesso à área de "
                    "administração."
                )

            st.markdown(
                f"""
<div style="background:#E7F1FF; border-left:4px solid #0071FE;
            padding:12px 16px; margin:8px 0; border-radius:6px;">
    <b>🎖 Alterar cargo de {u.nome}</b><br>
    <span style="font-size:13px; color:#444;">
        Cargo atual: <b>{traduzir_perfil(u.perfil.value)}</b>{aviso_proprio}
    </span>
</div>

<div style="background:#F8F9FA; padding:10px 14px; margin:4px 0 12px 0;
            font-size:13px; color:#555; border-radius:4px;">
    <b>O que cada cargo pode fazer:</b><br>
    • <b>ADMIN</b> — pode tudo (acordos, usuários, parâmetros, auditoria)<br>
    • <b>COBRANCA</b> — uso operacional do sistema (criar acordos, baixar parcelas)<br>
    • <b>DIRETORIA</b> — só leitura (Dashboard, Auditoria, consultas)
</div>
                """,
                unsafe_allow_html=True,
            )
            with st.form(f"form_edit_perfil_{u.id}"):
                # Opções de cargo
                opcoes_perfil = ["ADMIN", "COBRANCA", "DIRETORIA"]
                novo_perfil_str = st.selectbox(
                    "Novo cargo",
                    options=opcoes_perfil,
                    index=opcoes_perfil.index(u.perfil.value),
                    format_func=traduzir_perfil,
                )
                col_ok, col_cancel = st.columns(2)
                with col_ok:
                    confirmar = st.form_submit_button(
                        "✓ Salvar cargo",
                        type="primary", use_container_width=True,
                    )
                with col_cancel:
                    cancelar = st.form_submit_button(
                        "Cancelar", use_container_width=True,
                    )
                if confirmar:
                    try:
                        perfil_antigo = u.perfil.value
                        repo_usuario.alterar_perfil(
                            u.id, PerfilUsuario(novo_perfil_str)
                        )
                        repos_auxiliares.registrar_log(
                            usuario_id=usuario.id, usuario_nome=usuario.nome,
                            acao="ALTERAR_PERFIL_USUARIO",
                            entidade="usuario", entidade_id=u.id,
                            contexto=f"{u.nome}: {perfil_antigo} → {novo_perfil_str}",
                            antes={"perfil": perfil_antigo},
                            depois={"perfil": novo_perfil_str},
                        )
                        # Se admin alterou o próprio cargo, atualiza session
                        if u.id == usuario.id:
                            usuario_atualizado = repo_usuario.buscar_por_id(u.id)
                            if usuario_atualizado:
                                st.session_state["usuario_atual"] = usuario_atualizado
                        del st.session_state[f"edit_perfil_form_{u.id}"]
                        st.success(
                            f"✓ Cargo de {u.nome} alterado pra {novo_perfil_str}!"
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")
                if cancelar:
                    del st.session_state[f"edit_perfil_form_{u.id}"]
                    st.rerun()

        # ============ Formulário de editar NOME ============
        if st.session_state.get(f"edit_nome_form_{u.id}"):
            st.markdown(
                f"""
<div style="background:#E7F1FF; border-left:4px solid #0071FE;
            padding:12px 16px; margin:8px 0; border-radius:6px;">
    <b>✏ Alterar nome de {u.nome}</b><br>
    <span style="font-size:13px; color:#444;">
        Use isso pra corrigir erros de cadastro (ex: usuário que
        botou e-mail no campo nome). Após a edição, o nome novo
        aparece em toda lugar do sistema.
    </span>
</div>
                """,
                unsafe_allow_html=True,
            )
            with st.form(f"form_edit_nome_{u.id}"):
                novo_nome = st.text_input(
                    "Novo nome completo",
                    value=u.nome,
                    placeholder="Ex: João Silva Santos",
                )
                col_ok, col_cancel = st.columns(2)
                with col_ok:
                    confirmar = st.form_submit_button(
                        "✓ Salvar",
                        type="primary", use_container_width=True,
                    )
                with col_cancel:
                    cancelar = st.form_submit_button(
                        "Cancelar", use_container_width=True,
                    )
                if confirmar:
                    try:
                        nome_antigo = u.nome
                        repo_usuario.alterar_nome(u.id, novo_nome)
                        repos_auxiliares.registrar_log(
                            usuario_id=usuario.id, usuario_nome=usuario.nome,
                            acao="ALTERAR_NOME_USUARIO",
                            entidade="usuario", entidade_id=u.id,
                            contexto=novo_nome,
                            antes={"nome": nome_antigo},
                            depois={"nome": novo_nome.strip()},
                        )
                        del st.session_state[f"edit_nome_form_{u.id}"]
                        st.success(f"✓ Nome alterado pra '{novo_nome}'!")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")
                if cancelar:
                    del st.session_state[f"edit_nome_form_{u.id}"]
                    st.rerun()

        # ============ Formulário de redefinir senha ============
        if st.session_state.get(f"reset_pwd_form_{u.id}"):
            st.markdown(
                f"""
<div style="background:#E7F1FF; border-left:4px solid #0071FE;
            padding:12px 16px; margin:8px 0; border-radius:6px;">
    <b>🔑 Redefinir senha de {u.nome}</b><br>
    <span style="font-size:13px; color:#444;">
        Digite uma senha temporária. Você vai precisar avisar
        o usuário (por WhatsApp ou e-mail). Na primeira vez
        que ele entrar, o sistema vai pedir pra ele criar uma
        nova senha pessoal.
    </span>
</div>
                """,
                unsafe_allow_html=True,
            )
            with st.form(f"form_reset_pwd_{u.id}"):
                temp_senha = st.text_input(
                    f"Senha temporária pra {u.nome} (mín. 8 caracteres)",
                    type="text",  # texto exposto pro admin copiar pro WhatsApp
                    placeholder="Ex: LLE2026@temp",
                    help="O admin vê a senha aqui pra copiar e enviar pro usuário",
                )
                col_ok, col_cancel = st.columns(2)
                with col_ok:
                    confirmar = st.form_submit_button(
                        "✓ Redefinir e forçar troca",
                        type="primary",
                        use_container_width=True,
                    )
                with col_cancel:
                    cancelar = st.form_submit_button(
                        "Cancelar", use_container_width=True,
                    )

                if confirmar:
                    try:
                        repo_usuario.alterar_senha(
                            u.id,
                            temp_senha,
                            deve_trocar_no_proximo_login=True,
                        )
                        repos_auxiliares.registrar_log(
                            usuario_id=usuario.id, usuario_nome=usuario.nome,
                            acao="REDEFINIR_SENHA_USUARIO",
                            entidade="usuario", entidade_id=u.id,
                            contexto=u.nome,
                        )
                        del st.session_state[f"reset_pwd_form_{u.id}"]
                        st.success(
                            f"✓ Senha de {u.nome.split()[0]} redefinida! "
                            "Avise ele pra entrar com essa senha — vai ter que "
                            "criar uma nova no primeiro login."
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")
                if cancelar:
                    del st.session_state[f"reset_pwd_form_{u.id}"]
                    st.rerun()

        # ============ Confirmação de recusa ============
        if st.session_state.get(f"conf_recusar_{u.id}"):
            st.warning(
                f"⚠ Recusar **{u.nome}**? O usuário vai ser bloqueado e não "
                "vai conseguir entrar. Você pode reativá-lo depois."
            )
            col_sim, col_nao, _ = st.columns([1, 1, 4])
            with col_sim:
                if st.button("Sim, recusar", type="primary", key=f"sim_rec_{u.id}"):
                    repo_usuario.recusar_usuario(u.id)
                    repos_auxiliares.registrar_log(
                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                        acao="RECUSAR_USUARIO", entidade="usuario",
                        entidade_id=u.id, contexto=u.nome,
                    )
                    del st.session_state[f"conf_recusar_{u.id}"]
                    st.rerun()
            with col_nao:
                if st.button("Cancelar", key=f"nao_rec_{u.id}"):
                    del st.session_state[f"conf_recusar_{u.id}"]
                    st.rerun()

        st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)


# ============================================================
# 3) DASHBOARD (Seção 25)
# ============================================================

def renderizar_dashboard(usuario):
    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>📊 Dashboard</h1>", unsafe_allow_html=True)

    todos = repo_acordo.listar_resumos(
        status_em=[
            StatusAcordo.ATIVO, StatusAcordo.PENDENTE_APROVACAO,
            StatusAcordo.QUITADO, StatusAcordo.QUEBRADO, StatusAcordo.CANCELADO,
        ]
    )

    if not todos:
        st.info("Sem dados ainda. Crie alguns acordos para ver o dashboard.")
        return

    # ============ BLOCO 1: VISÃO GERAL ============
    st.markdown("### 📈 Visão geral da carteira")
    total_carteira = sum(a.valor_total for a in todos)
    total_recebido = sum(a.valor_total - a.saldo_devedor for a in todos)
    saldo = sum(a.saldo_devedor for a in todos if a.status == StatusAcordo.ATIVO)
    ticket = total_carteira / len(todos) if todos else 0
    parcelas_atraso = sum(a.parcelas_em_atraso for a in todos)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Carteira total", formatar_brl(total_carteira))
    c2.metric("Recebido", formatar_brl(total_recebido))
    c3.metric("Saldo (ativos)", formatar_brl(saldo))
    c4.metric("Ticket médio", formatar_brl(ticket))
    c5.metric("Parcelas atrasadas", str(parcelas_atraso))

    # Pizza status
    df_status = pd.DataFrame([
        {"Status": s.value, "Quantidade": sum(1 for a in todos if a.status == s)}
        for s in StatusAcordo
    ])
    df_status = df_status[df_status["Quantidade"] > 0]
    if not df_status.empty:
        try:
            import plotly.express as px
            cores = {
                "ATIVO": VERDE, "PENDENTE_APROVACAO": AMARELO,
                "QUITADO": "#28A745", "QUEBRADO": "#DC3545",
                "CANCELADO": "#6C757D", "RASCUNHO": "#ADB5BD",
            }
            fig = px.pie(
                df_status, names="Status", values="Quantidade",
                color="Status", color_discrete_map=cores,
                title="Acordos por status",
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.dataframe(df_status, hide_index=True)

    # ============ BLOCO 2: PERFORMANCE POR NEGOCIADOR ============
    st.markdown("### 👥 Performance por negociador")
    by_neg = {}
    for a in todos:
        d = by_neg.setdefault(a.negociador_nome, {
            "acordos": 0, "negociado": 0, "recebido": 0, "atraso": 0, "quebrados": 0,
        })
        d["acordos"] += 1
        d["negociado"] += a.valor_total
        d["recebido"] += a.valor_total - a.saldo_devedor
        if a.status == StatusAcordo.QUEBRADO:
            d["quebrados"] += 1

    rows_neg = []
    for nome, d in by_neg.items():
        pct = (d["recebido"] / d["negociado"] * 100) if d["negociado"] > 0 else 0
        rows_neg.append({
            "Negociador": nome,
            "Acordos": d["acordos"],
            "Negociado": formatar_brl(d["negociado"]),
            "Recebido": formatar_brl(d["recebido"]),
            "% recebido": f"{pct:.1f}%",
            "Quebrados": d["quebrados"],
        })
    st.dataframe(pd.DataFrame(rows_neg), use_container_width=True, hide_index=True)

    # ============ BLOCO 4: PARCELAS EM ATRASO ============
    st.markdown("### ⚠ Parcelas em atraso (operacional)")
    from src.banco.conexao import obter_conexao
    cur = obter_conexao().execute(
        """
        SELECT p.id AS pid, p.numero, p.vencimento_atual, p.valor_original,
               p.status AS p_status,
               julianday('now') - julianday(p.vencimento_atual) AS dias_atraso,
               a.numero_interno, a.id AS aid, a.pct_juros_mora_mes, a.pct_multa_mora,
               c.nome_principal, u.nome AS negociador
        FROM parcela p
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE p.status != 'QUITADA'
          AND DATE(p.vencimento_atual) < DATE('now')
          AND a.status = 'ATIVO'
        ORDER BY dias_atraso DESC
        LIMIT 100;
        """
    )
    rows_atr = []
    for r in cur.fetchall():
        dias = int(r["dias_atraso"])
        # Calcula mora simples
        mora_juros = r["valor_original"] * (r["pct_juros_mora_mes"] / 100) / 30 * dias
        mora_multa = r["valor_original"] * (r["pct_multa_mora"] / 100)
        valor_atu = r["valor_original"] + mora_juros + mora_multa
        rows_atr.append({
            "Acordo": r["numero_interno"],
            "Cliente": r["nome_principal"],
            "Negociador": r["negociador"],
            "Parcela": r["numero"],
            "Vencimento": formatar_data(r["vencimento_atual"]),
            "Dias atraso": dias,
            "Original": formatar_brl(r["valor_original"]),
            "Atualizado": formatar_brl(valor_atu),
        })
    if rows_atr:
        st.dataframe(pd.DataFrame(rows_atr), use_container_width=True, hide_index=True)
    else:
        st.success("🎉 Nenhuma parcela em atraso no momento.")


# ============================================================
# 4) AUDITORIA (Seção 18e + P9)
# ============================================================

def renderizar_auditoria(usuario):
    if usuario.perfil not in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
        st.error("Acesso restrito a Administradores e Diretoria.")
        return

    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>📜 Auditoria</h1>", unsafe_allow_html=True)
    st.caption(
        "Registro de todas as ações importantes feitas no sistema. "
        "Use os filtros pra encontrar uma ação específica."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        users = repo_usuario.listar_todos()
        ops = {0: "Todos"}
        for u in users:
            ops[u.id] = u.nome
        sel = st.selectbox("Usuário", list(ops.keys()), format_func=lambda i: ops[i])
        usuario_id = sel if sel != 0 else None
    with col2:
        # Entidades com nomes amigáveis
        entidades_map = {
            "Todas": None, "Acordo": "acordo", "Parcela": "parcela",
            "Usuário": "usuario", "Pagamento": "pagamento_parcela",
            "Cliente": "cliente",
        }
        ent_label = st.selectbox("Entidade", list(entidades_map.keys()))
        entidade = entidades_map[ent_label]
    with col3:
        dias = st.selectbox("Período", [7, 30, 90, 365], index=1, format_func=lambda d: f"Últimos {d} dias")

    desde = (datetime.now() - timedelta(days=dias)).isoformat()
    logs = repos_auxiliares.listar_logs(
        usuario_id=usuario_id, entidade=entidade, desde=desde, limite=500
    )

    st.markdown(f"### {len(logs)} registro(s)")
    if not logs:
        st.info("Nenhum registro encontrado com esses filtros.")
        return

    for l in logs:
        acao_amigavel = traduzir_acao(l['acao'])
        # Data formatada — timestamp pode vir como string (SQLite) ou datetime (Postgres)
        ts = l['timestamp']
        try:
            if isinstance(ts, datetime):
                ts_fmt = ts.strftime('%d/%m/%Y %H:%M')
            elif isinstance(ts, str):
                ts_fmt = datetime.fromisoformat(ts.replace('Z', '')[:19]).strftime('%d/%m/%Y %H:%M')
            else:
                ts_fmt = str(ts)
        except Exception:
            ts_fmt = str(ts)[:16].replace('T', ' ')

        titulo = (
            f"**{acao_amigavel}** · "
            f"{l['usuario_nome_snapshot'] or '—'} · "
            f"{ts_fmt}"
        )
        if l.get('contexto'):
            titulo += f" · _{l['contexto']}_"

        with st.expander(titulo):
            if l.get("antes"):
                st.markdown("**Antes da alteração:**")
                st.json(l["antes"])
            if l.get("depois"):
                st.markdown("**Depois da alteração:**")
                st.json(l["depois"])
            if not l.get("antes") and not l.get("depois"):
                st.caption("(sem detalhes adicionais — ação simples)")


# ============================================================
# 5) PARÂMETROS (Seção 10)
# ============================================================

def renderizar_parametros(usuario):
    if usuario.perfil not in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
        st.error("Acesso restrito a Administradores e Diretoria.")
        return

    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>⚙ Parâmetros</h1>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["📬 Lembretes", "✉ Template", "📊 Padrões de cálculo"])

    with tab1:
        st.markdown("#### Gatilhos automáticos")
        atuais_g = repos_auxiliares.get_parametro("lembrete.gatilhos") or '["D-5", "D-2", "D0", "D+1"]'
        import json
        atuais_list = json.loads(atuais_g)
        c1, c2, c3, c4 = st.columns(4)
        opts = []
        with c1:
            if st.checkbox("D-5 (5 dias antes)", value="D-5" in atuais_list):
                opts.append("D-5")
        with c2:
            if st.checkbox("D-2 (2 dias antes)", value="D-2" in atuais_list):
                opts.append("D-2")
        with c3:
            if st.checkbox("D0 (no dia)", value="D0" in atuais_list):
                opts.append("D0")
        with c4:
            if st.checkbox("D+1 (1 dia após)", value="D+1" in atuais_list):
                opts.append("D+1")
        hr = st.text_input(
            "Horário de envio (HH:MM)",
            value=repos_auxiliares.get_parametro("lembrete.horario_envio") or "09:00",
        )
        if st.button("💾 Salvar lembretes", type="primary"):
            try:
                repos_auxiliares.set_parametro("lembrete.gatilhos", json.dumps(opts), usuario.id)
                repos_auxiliares.set_parametro("lembrete.horario_envio", hr, usuario.id)
                st.toast("✅ Configurações salvas!", icon="✅")
                st.success("✅ Configurações salvas.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao salvar: {e}")
                st.exception(e)

    with tab2:
        st.markdown("#### Template do lembrete (e-mail)")
        st.caption("Variáveis disponíveis: " + ", ".join([
            "{{cliente}}", "{{negociador}}", "{{numero_parcela}}", "{{valor}}",
            "{{valor_atualizado}}", "{{data_vencimento}}", "{{dias_para_vencimento}}",
            "{{tipo_cobranca}}", "{{instrucoes_pagamento}}", "{{dias_atraso}}", "{{numero_acordo}}",
        ]))
        assunto = st.text_input(
            "Assunto",
            value=repos_auxiliares.get_parametro("lembrete.template_assunto") or "",
        )
        corpo = st.text_area(
            "Corpo",
            value=repos_auxiliares.get_parametro("lembrete.template_corpo") or "",
            height=300,
        )
        instr = st.text_area(
            "Instruções de pagamento (PIX/Boleto)",
            value=repos_auxiliares.get_parametro("lembrete.instrucoes_pagamento") or "",
            height=80,
        )
        if st.button("💾 Salvar template", type="primary"):
            try:
                repos_auxiliares.set_parametro("lembrete.template_assunto", assunto, usuario.id)
                repos_auxiliares.set_parametro("lembrete.template_corpo", corpo, usuario.id)
                repos_auxiliares.set_parametro("lembrete.instrucoes_pagamento", instr, usuario.id)
                st.toast("✅ Template salvo!", icon="✅")
                st.success("✅ Template salvo.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao salvar: {e}")
                st.exception(e)

    with tab3:
        st.markdown("#### Padrões de cálculo (defaults da Calculadora e Wizard)")
        c1, c2 = st.columns(2)
        with c1:
            pj_t = st.number_input(
                "Juros títulos % a.m. (default)",
                value=float(repos_auxiliares.get_parametro("calculo.pct_juros_titulos_default") or 8.0),
                step=0.1, format="%.2f",
            )
            pj_m = st.number_input(
                "Juros mora % a.m. (default)",
                value=float(repos_auxiliares.get_parametro("calculo.pct_juros_mora_default") or 5.0),
                step=0.1, format="%.2f",
            )
        with c2:
            pm_t = st.number_input(
                "Multa títulos % (default)",
                value=float(repos_auxiliares.get_parametro("calculo.pct_multa_titulos_default") or 2.0),
                step=0.1, format="%.2f",
            )
            pm_m = st.number_input(
                "Multa mora % (default)",
                value=float(repos_auxiliares.get_parametro("calculo.pct_multa_mora_default") or 2.0),
                step=0.1, format="%.2f",
            )
        if st.button("💾 Salvar padrões", type="primary"):
            try:
                repos_auxiliares.set_parametro("calculo.pct_juros_titulos_default", str(pj_t), usuario.id)
                repos_auxiliares.set_parametro("calculo.pct_multa_titulos_default", str(pm_t), usuario.id)
                repos_auxiliares.set_parametro("calculo.pct_juros_mora_default", str(pj_m), usuario.id)
                repos_auxiliares.set_parametro("calculo.pct_multa_mora_default", str(pm_m), usuario.id)
                st.toast("✅ Padrões salvos!", icon="✅")
                st.success("✅ Padrões salvos.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao salvar: {e}")
                st.exception(e)


# ============================================================
# 6) APROVAÇÕES PENDENTES (P5)
# ============================================================

def renderizar_aprovacoes(usuario):
    if usuario.perfil not in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
        st.error("Acesso restrito a Administradores e Diretoria.")
        return

    st.markdown(f"<h1 style='color:{AZUL_ESCURO}'>✅ Aprovações Pendentes</h1>", unsafe_allow_html=True)

    # Mensagem persistente da última ação
    msg = st.session_state.pop("aprovacoes_msg", None)
    if msg:
        tipo, texto = msg
        if tipo == "sucesso":
            st.success(texto)
        elif tipo == "aviso":
            st.warning(texto)
        else:
            st.error(texto)

    pendentes = repos_auxiliares.listar_aprovacoes_pendentes()
    if not pendentes:
        st.success("🎉 Sem aprovações pendentes no momento.")
        return

    st.markdown(f"### {len(pendentes)} solicitação(ões) aguardando")

    for ap in pendentes:
        with st.container():
            st.markdown(
                f"""
<div class="lle-card">
    <div style="font-size:14px;color:#666;">{ap['numero_interno']}</div>
    <div style="font-size:17px;font-weight:700;color:{AZUL_ESCURO};">
        {ap['cliente_nome']}
    </div>
    <div style="font-size:13px;color:#444;margin-top:4px;">
        Solicitante: <b>{ap['solicitante_nome']}</b> ·
        {ap['quantidade_parcelas']} parcelas {ap['periodicidade'].lower()} ·
        Total: <b>{formatar_brl(ap['valor_total'])}</b>
    </div>
    <div style="margin-top:8px;padding:8px;background:#F8F9FA;border-radius:4px;
                font-size:13px;font-style:italic;">
        "{ap['justificativa_solicitacao']}"
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
            col_ver, col_apr, col_rec = st.columns([1, 1.5, 1.5])
            with col_ver:
                if st.button("Ver acordo", key=f"ver_{ap['id']}", use_container_width=True):
                    st.session_state["acordo_id_aberto"] = ap["acordo_id"]
                    st.rerun()
            with col_apr:
                if st.button("✅ Aprovar", type="primary", key=f"apr_{ap['id']}", use_container_width=True):
                    st.session_state[f"rev_apr_{ap['id']}"] = "aprovar"
            with col_rec:
                if st.button("❌ Recusar", key=f"rec_{ap['id']}", use_container_width=True):
                    st.session_state[f"rev_apr_{ap['id']}"] = "recusar"

            if st.session_state.get(f"rev_apr_{ap['id']}"):
                acao = st.session_state[f"rev_apr_{ap['id']}"]
                with st.form(f"form_rev_{ap['id']}"):
                    just = st.text_area(
                        f"Justificativa para {'aprovação' if acao == 'aprovar' else 'recusa'}",
                        height=80,
                    )
                    col_o, col_x = st.columns(2)
                    with col_o:
                        if st.form_submit_button("✓ Confirmar", type="primary", use_container_width=True):
                            try:
                                aprovado = (acao == "aprovar")
                                repos_auxiliares.revisar_aprovacao(
                                    aprovacao_id=ap["id"], revisor_id=usuario.id,
                                    aprovado=aprovado, justificativa=just,
                                )
                                # Muda status do acordo
                                from src.banco.repo_acordo import atualizar_status
                                novo = StatusAcordo.ATIVO if aprovado else StatusAcordo.CANCELADO
                                atualizar_status(ap["acordo_id"], novo)
                                repos_auxiliares.registrar_log(
                                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                                    acao=f"APROVACAO_{novo.value}",
                                    entidade="acordo", entidade_id=ap["acordo_id"],
                                    contexto=ap["numero_interno"],
                                    depois={"justificativa": just, "novo_status": novo.value},
                                )
                                del st.session_state[f"rev_apr_{ap['id']}"]
                                # Persiste mensagem pro próximo rerun
                                acao_txt = "aprovado" if aprovado else "recusado"
                                st.session_state["aprovacoes_msg"] = (
                                    "sucesso",
                                    f"✅ Acordo {ap['numero_interno']} {acao_txt} com sucesso!"
                                )
                                st.toast(f"✅ Acordo {acao_txt}!", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro ao processar: {e}")
                                st.exception(e)
                    with col_x:
                        if st.form_submit_button("Cancelar", use_container_width=True):
                            del st.session_state[f"rev_apr_{ap['id']}"]
                            st.rerun()

            st.markdown("<hr style='margin:12px 0;'>", unsafe_allow_html=True)
