"""
Tela Meu Perfil — usuário consulta seus dados e troca a senha.

Regras (decididas pelo Erick):
  - Qualquer usuário pode TROCAR A PRÓPRIA SENHA (digitando a atual).
  - APENAS ADMIN pode editar o próprio nome aqui.
  - Usuário comum que quer mudar o nome precisa pedir ao admin
    (admin altera pela tela Negociadores → botão "✏ Nome").
"""
from __future__ import annotations

import streamlit as st

from src.banco import repo_usuario, repos_auxiliares
from src.modelos.tipos import PerfilUsuario
from src.utils.feedback import drenar_mensagens
from src.utils.formatadores import formatar_data
from src.utils.marca import AZUL_ESCURO, AMARELO


def renderizar_meu_perfil(usuario):
    drenar_mensagens()
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO}'>👤 Meu Perfil</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Aqui você consulta seus dados e pode alterar sua senha.")

    # Recarrega o usuário do banco pra pegar nome atualizado
    usuario_atual = repo_usuario.buscar_por_id(usuario.id) or usuario

    eh_admin = usuario_atual.perfil == PerfilUsuario.ADMIN

    # ============ Dados do usuário ============
    st.markdown("### Seus dados")

    # Se admin estiver em modo edição de nome
    if eh_admin and st.session_state.get("editando_meu_nome"):
        _form_editar_meu_nome(usuario_atual)
    else:
        col1, col2 = st.columns(2)
        with col1:
            _campo("Nome", usuario_atual.nome)
            _campo("E-mail", usuario_atual.email)
        with col2:
            _campo("Perfil", usuario_atual.perfil.value)
            _campo("Cadastro", formatar_data(usuario_atual.criado_em))

        if eh_admin:
            col_btn, _ = st.columns([2, 4])
            with col_btn:
                if st.button(
                    "✏ Alterar meu nome",
                    use_container_width=True,
                    key="btn_editar_meu_nome",
                ):
                    st.session_state["editando_meu_nome"] = True
                    st.rerun()
        else:
            st.markdown(
                f"""
<div style="background:#FFF3CD; border-left:4px solid {AMARELO};
            padding:10px 14px; margin:8px 0; border-radius:6px;
            font-size:13px;">
    ℹ Apenas o administrador pode alterar o seu nome. Se precisa
    corrigir, fale com o administrador do sistema.
</div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ============ Alterar senha ============
    st.markdown("### Alterar senha")
    st.caption(
        "Use uma senha forte (mínimo 8 caracteres). "
        "Ninguém mais sabe sua senha — só você."
    )

    with st.form("alterar_minha_senha"):
        senha_atual = st.text_input(
            "Senha atual *", type="password",
            autocomplete="current-password",
        )
        nova_senha = st.text_input(
            "Nova senha *", type="password",
            help="Mínimo 8 caracteres",
            autocomplete="new-password",
        )
        confirma_senha = st.text_input(
            "Confirme a nova senha *", type="password",
            autocomplete="new-password",
        )

        col_a, col_b = st.columns([1, 3])
        with col_a:
            salvar = st.form_submit_button(
                "💾 Alterar senha",
                type="primary",
                use_container_width=True,
            )

        if salvar:
            # Confere senha atual
            auth = repo_usuario.autenticar(usuario_atual.email, senha_atual)
            if auth is None:
                st.error("❌ Senha atual incorreta.")
                return

            if nova_senha != confirma_senha:
                st.error("❌ As novas senhas não conferem.")
                return

            if nova_senha == senha_atual:
                st.warning("⚠ A nova senha é igual à atual. Escolha uma diferente.")
                return

            try:
                repo_usuario.alterar_senha(
                    usuario_atual.id,
                    nova_senha,
                    deve_trocar_no_proximo_login=False,
                )
                repos_auxiliares.registrar_log(
                    usuario_id=usuario_atual.id,
                    usuario_nome=usuario_atual.nome,
                    acao="TROCAR_PROPRIA_SENHA",
                    entidade="usuario",
                    entidade_id=usuario_atual.id,
                    contexto=usuario_atual.nome,
                )
                st.success("✓ Senha alterada com sucesso!")
            except ValueError as e:
                st.error(f"❌ {e}")


def _form_editar_meu_nome(usuario):
    """Form de editar próprio nome (só admin acessa)."""
    st.markdown(
        f"""
<div style="background:#E7F1FF; border-left:4px solid #0071FE;
            padding:12px 16px; margin:8px 0; border-radius:6px;">
    <b>✏ Alterar meu nome</b><br>
    <span style="font-size:13px; color:#444;">
        Como administrador, você pode alterar o próprio nome.
        O nome será atualizado em toda lista do sistema.
    </span>
</div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("form_edit_meu_nome"):
        novo_nome = st.text_input(
            "Novo nome completo",
            value=usuario.nome,
            placeholder="Ex: João Silva Santos",
        )
        col_ok, col_cancel = st.columns(2)
        with col_ok:
            confirmar = st.form_submit_button(
                "✓ Salvar", type="primary", use_container_width=True,
            )
        with col_cancel:
            cancelar = st.form_submit_button("Cancelar", use_container_width=True)
        if confirmar:
            try:
                nome_antigo = usuario.nome
                repo_usuario.alterar_nome(usuario.id, novo_nome)
                # Atualiza o usuário na sessão pra refletir imediatamente
                usuario_atualizado = repo_usuario.buscar_por_id(usuario.id)
                if usuario_atualizado:
                    st.session_state["usuario_atual"] = usuario_atualizado
                repos_auxiliares.registrar_log(
                    usuario_id=usuario.id, usuario_nome=usuario.nome,
                    acao="ALTERAR_PROPRIO_NOME",
                    entidade="usuario", entidade_id=usuario.id,
                    contexto=novo_nome,
                    antes={"nome": nome_antigo},
                    depois={"nome": novo_nome.strip()},
                )
                del st.session_state["editando_meu_nome"]
                st.success(f"✓ Nome alterado pra '{novo_nome}'!")
                st.rerun()
            except ValueError as e:
                st.error(f"❌ {e}")
        if cancelar:
            del st.session_state["editando_meu_nome"]
            st.rerun()


def _campo(label: str, valor: str):
    st.markdown(
        f"""
<div style="margin-bottom: 16px;">
    <div style="font-size: 11px; color: #888;
                letter-spacing: 0.5px; text-transform: uppercase;
                margin-bottom: 4px;">
        {label}
    </div>
    <div style="font-size: 15px; color: #222; font-weight: 500;">
        {valor or '—'}
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
