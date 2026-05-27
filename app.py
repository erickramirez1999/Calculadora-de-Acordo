"""
LLE Acordos — App principal Streamlit.

Fluxo de acesso (decidido com Erick):
  1. Usuário se cadastra (nome, e-mail, senha). Senha NUNCA é compartilhada.
  2. Sistema gera uma "chave de aprovação" única (ex: K7P4-N2X9-B5M1).
  3. Usuário copia a chave e manda pro Erick por outro canal (WhatsApp/e-mail).
  4. Erick joga a chave nos Streamlit Secrets:
        [usuarios_aprovados]
        chaves = ["K7P4-N2X9-B5M1"]
  5. O app sincroniza no próximo carregamento e libera o login.
  6. O usuário entra normalmente com e-mail + senha (que só ele sabe).

Para rodar localmente:
    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Permite imports do src/
sys.path.insert(0, str(Path(__file__).parent))

from src.banco import repo_usuario
from src.banco.schema import inicializar_banco
from src.modelos.tipos import PerfilUsuario
from src.utils.estilo import aplicar_css_lle
from src.utils.marca import AZUL_ESCURO, AMARELO

# ============================================================
# CONFIG DA PÁGINA — precisa ser o PRIMEIRO comando do Streamlit
# ============================================================

st.set_page_config(
    page_title="LLE Acordos",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inicializa o banco e sincroniza aprovações com os Secrets
if "banco_inicializado" not in st.session_state:
    inicializar_banco()
    st.session_state["banco_inicializado"] = True

# Sincroniza chaves do Secrets a cada execução do app (rápido)
try:
    repo_usuario.sincronizar_aprovacoes_com_secrets()
except Exception as e:
    # Não trava o app se houver erro no Secrets
    pass

aplicar_css_lle()


# ============================================================
# CSS PARA ESCONDER NAVEGAÇÃO NA TELA DE LOGIN
# ============================================================

def _esconder_navegacao():
    st.markdown(
        """
        <style>
            section[data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarNav"] { display: none !important; }
            button[kind="header"] { display: none !important; }
            button[data-testid="collapsedControl"] { display: none !important; }
            header[data-testid="stHeader"] { display: none !important; }
            div[data-testid="stToolbar"] { display: none !important; }
            .block-container {
                padding-top: 3rem !important;
                max-width: 600px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _mostrar_navegacao_fixa():
    """
    Após login: sidebar SEMPRE aberta e fixa.
    Sem botão de toggle (que tinha bug com Material Icons).
    Trava de vez pra usuário NÃO conseguir fechar.
    """
    st.markdown(
        """
        <style>
            /* === SIDEBAR FIXA — bloqueia qualquer tentativa de fechar === */
            section[data-testid="stSidebar"] {
                display: block !important;
                min-width: 260px !important;
                max-width: 260px !important;
                width: 260px !important;
                transform: translateX(0px) !important;
                visibility: visible !important;
                margin-left: 0 !important;
            }

            /* Esconde TODOS os botões que poderiam fechar/abrir */
            section[data-testid="stSidebar"] button[kind="header"],
            section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"],
            section[data-testid="stSidebar"] [data-testid="stSidebarCollapseControl"],
            button[data-testid="collapsedControl"],
            button[data-testid="stSidebarCollapseButton"],
            [data-testid="stSidebarUserContent"] button[kind="header"] {
                display: none !important;
                visibility: hidden !important;
                pointer-events: none !important;
                width: 0 !important;
                height: 0 !important;
                opacity: 0 !important;
            }

            /* Esconde a lista de pages automática do Streamlit */
            [data-testid="stSidebarNav"] {
                display: none !important;
            }

            /* Header limpo */
            header[data-testid="stHeader"] {
                background: transparent;
                display: none !important;
            }

            /* Ajusta padding do conteúdo principal */
            .main .block-container {
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION STATE - helpers
# ============================================================

def usuario_logado():
    return st.session_state.get("usuario_atual")


def logar(usuario):
    st.session_state["usuario_atual"] = usuario


def deslogar():
    for k in list(st.session_state.keys()):
        if k not in ("banco_inicializado",):
            del st.session_state[k]


# ============================================================
# TELA: LOGIN
# ============================================================

def tela_login():
    """Tela inicial quando não há usuário logado."""
    LOGO = Path(__file__).parent / "assets" / "logo_lle.png"

    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.write("")
        if LOGO.exists():
            st.image(str(LOGO), use_container_width=True)

        st.markdown(
            f"""
            <div style="text-align:center; margin-top: -20px; margin-bottom: 24px;">
                <h2 style="color:{AZUL_ESCURO}; margin-bottom: 4px;">Sistema de Acordos de Cobrança</h2>
                <p style="color: #666;">LLE Ferragens — acesso restrito à equipe</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Se está em meio de uma troca de senha forçada, mostra essa tela
        if st.session_state.get("usuario_trocando_senha"):
            _tela_troca_senha_forcada()
            return

        # Se acabou de se cadastrar, mostra a chave
        if st.session_state.get("chave_recem_gerada"):
            _mostrar_chave_gerada()
            return

        tab_login, tab_cadastro = st.tabs(["🔑 Entrar", "📝 Cadastrar"])

        with tab_login:
            _form_login()

        with tab_cadastro:
            _form_cadastro()


def _form_login():
    """Formulário de login (e-mail + senha)."""
    with st.form("login", clear_on_submit=False):
        email = st.text_input(
            "E-mail",
            placeholder="seu.email@lle.com.br",
            autocomplete="username",
        )
        senha = st.text_input(
            "Senha",
            type="password",
            autocomplete="current-password",
        )
        entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if entrar:
            usuario = repo_usuario.autenticar(email.strip(), senha)
            if usuario is None:
                st.error("❌ E-mail ou senha inválidos.")
                return
            if not usuario.ativo:
                st.error("❌ Usuário inativado. Procure o administrador.")
                return
            if not usuario.aprovado:
                _mostrar_acesso_pendente(usuario)
                return

            # Se admin definiu uma senha temporária, força troca
            if usuario.deve_trocar_senha:
                st.session_state["usuario_trocando_senha"] = usuario
                st.rerun()
                return

            logar(usuario)
            st.success(f"Olá, {usuario.nome}!")
            st.rerun()


def _tela_troca_senha_forcada():
    """
    Mostrada quando o admin redefiniu a senha do usuário.
    O usuário entrou com a senha temporária mas precisa definir a real
    antes de seguir.
    """
    usuario = st.session_state.get("usuario_trocando_senha")
    if not usuario:
        return

    st.markdown(
        f"""
        <div style="background:#FFF3CD; border-left:4px solid {AMARELO};
                    padding:16px; margin:16px 0; border-radius:6px;">
            <div style="font-weight:700; color:{AZUL_ESCURO}; margin-bottom:8px;">
                🔐 Você precisa definir uma nova senha
            </div>
            <div style="color:#444; font-size:14px;">
                O administrador redefiniu seu acesso com uma senha temporária.
                Por segurança, crie agora a sua senha pessoal.
                Ninguém mais saberá ela.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("trocar_senha_forcada"):
        nova = st.text_input(
            "Nova senha (mín. 8 caracteres)",
            type="password",
            help="Use uma senha que só você conheça",
        )
        confirma = st.text_input("Confirme a nova senha", type="password")
        salvar = st.form_submit_button(
            "✓ Salvar e entrar",
            type="primary", use_container_width=True,
        )

        if salvar:
            if nova != confirma:
                st.error("❌ As senhas não conferem.")
                return
            try:
                repo_usuario.alterar_senha(
                    usuario.id, nova,
                    deve_trocar_no_proximo_login=False,
                )
                # Recarrega usuário atualizado
                usuario_atualizado = repo_usuario.buscar_por_id(usuario.id)
                del st.session_state["usuario_trocando_senha"]
                logar(usuario_atualizado)
                st.success("✓ Senha alterada com sucesso!")
                st.rerun()
            except ValueError as e:
                st.error(f"❌ {e}")


def _form_cadastro():
    """Cadastro: cria usuário em estado PENDENTE e mostra a chave."""
    st.caption(
        "📝 Preencha seus dados pra criar uma conta. "
        "Após o cadastro você receberá uma **chave de liberação** que deve ser "
        "enviada ao administrador. Ele libera seu acesso e você pode entrar."
    )

    with st.form("cadastro", clear_on_submit=False):
        nome = st.text_input(
            "Nome completo *",
            placeholder="Ex: João Silva Santos",
            help="Seu nome completo. NÃO use e-mail aqui.",
        )
        email = st.text_input(
            "E-mail *",
            placeholder="seu.email@empresa.com",
        )
        senha = st.text_input(
            "Senha (mín. 8 caracteres) *",
            type="password",
            help="A senha NÃO é compartilhada com ninguém. Só você precisa lembrar dela.",
        )
        senha_conf = st.text_input("Confirme a senha *", type="password")

        submitted = st.form_submit_button(
            "Criar conta", use_container_width=True, type="primary",
        )

        if submitted:
            if not nome or not email or not senha:
                st.error("❌ Preencha todos os campos obrigatórios.")
                return
            # Validação: nome não pode ser e-mail (engano comum)
            if "@" in nome:
                st.error(
                    "❌ O campo 'Nome completo' deve ter seu nome, não e-mail. "
                    "Coloque o e-mail no campo de baixo."
                )
                return
            if senha != senha_conf:
                st.error("❌ As senhas não conferem.")
                return
            try:
                # Define perfil: 1º vira ADMIN automaticamente (auto-bootstrap)
                perfil_pedido = (
                    PerfilUsuario.ADMIN
                    if not repo_usuario.existe_algum_usuario()
                    else PerfilUsuario.COBRANCA
                )
                novo = repo_usuario.criar_usuario(
                    nome=nome.strip(),
                    email=email.strip(),
                    senha=senha,
                    perfil=perfil_pedido,
                )
                # Guarda a chave pra mostrar
                st.session_state["chave_recem_gerada"] = novo.chave_aprovacao
                st.session_state["nome_recem_cadastrado"] = novo.nome
                st.session_state["email_recem_cadastrado"] = novo.email
                st.session_state["aprovado_auto"] = novo.aprovado
                st.rerun()
            except ValueError as e:
                st.error(f"❌ {e}")


def _mostrar_chave_gerada():
    """Tela mostrada logo após o cadastro — exibe a chave única."""
    chave = st.session_state.get("chave_recem_gerada")
    nome = st.session_state.get("nome_recem_cadastrado", "")
    email = st.session_state.get("email_recem_cadastrado", "")
    aprovado_auto = st.session_state.get("aprovado_auto", False)

    st.success(f"✅ Cadastro realizado, {nome.split()[0] if nome else ''}!")

    if aprovado_auto:
        st.info(
            "🎉 **Você é o primeiro usuário do sistema** — virou Administrador "
            "automaticamente e já tem acesso liberado.\n\n"
            "Faça login abaixo para entrar."
        )
    else:
        st.markdown(
            f"""
            <div style="background: #FFF3CD; border-left: 4px solid {AMARELO};
                        padding: 16px; margin: 16px 0; border-radius: 6px;">
                <div style="font-weight: 700; color: {AZUL_ESCURO}; margin-bottom: 8px;">
                    ⏳ Seu acesso está PENDENTE de aprovação.
                </div>
                <div style="color: #444; font-size: 14px;">
                    Avise o administrador do sistema que se cadastrou. Ele
                    pode te aprovar diretamente pela tela "Negociadores" e seu
                    acesso será liberado imediatamente.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Caixa destacada com a chave (só pra referência - já que admin aprova pela tela)
    if not aprovado_auto:
        st.markdown(
            f"""
            <div style="background: {AZUL_ESCURO}; color: white; padding: 18px;
                        border-radius: 8px; text-align: center; margin: 16px 0;">
                <div style="font-size: 11px; letter-spacing: 1px;
                            text-transform: uppercase; opacity: 0.7; margin-bottom: 6px;">
                    Chave de identificação (opcional)
                </div>
                <div style="font-family: 'Courier New', monospace; font-size: 22px;
                            font-weight: 700; color: {AMARELO}; letter-spacing: 3px;">
                    {chave}
                </div>
                <div style="font-size: 11px; opacity: 0.7; margin-top: 8px;">
                    Caso o administrador precise confirmar quem você é
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    if st.button("← Voltar para a tela de login", use_container_width=True, type="primary"):
        # Limpa o estado da chave e volta pra tela inicial
        for k in ["chave_recem_gerada", "nome_recem_cadastrado",
                  "email_recem_cadastrado", "aprovado_auto"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()


def _mostrar_acesso_pendente(usuario):
    """Se o usuário tenta entrar mas ainda não foi aprovado."""
    st.markdown(
        f"""
        <div style="background: #FFF3CD; border-left: 4px solid {AMARELO};
                    padding: 16px; margin: 16px 0; border-radius: 6px;">
            <div style="font-weight: 700; color: {AZUL_ESCURO}; margin-bottom: 8px;">
                ⏳ Seu acesso ainda está pendente de aprovação.
            </div>
            <div style="color: #444; font-size: 14px;">
                Avise o administrador do sistema que se cadastrou.
                Ele pode te aprovar diretamente pela tela "Negociadores".
                Após aprovado, é só recarregar a página e fazer login normalmente.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SIDEBAR LOGADO
# ============================================================

def sidebar_logado(usuario):
    """Sidebar com menu principal. Sempre fixa e aberta."""
    LOGO_BRANCO = Path(__file__).parent / "assets" / "logo_lle_branco.png"
    LOGO_COR = Path(__file__).parent / "assets" / "logo_lle.png"
    logo_a_usar = LOGO_BRANCO if LOGO_BRANCO.exists() else LOGO_COR

    with st.sidebar:
        if logo_a_usar.exists():
            st.image(str(logo_a_usar), use_container_width=True)
        st.markdown("---")
        st.markdown(f"👤 **{usuario.nome}**")
        from src.utils.traducoes import traduzir_perfil
        st.caption(f"Perfil: {traduzir_perfil(usuario.perfil.value)}")
        # Atalho destacado pra Meu Perfil (logo abaixo do nome)
        st.page_link("pages/0_👤_Meu_Perfil.py", label="👤 Meu Perfil")
        st.markdown("---")

        # Menu de navegação manual (substitui o stSidebarNav que escondemos)
        st.markdown("**Menu**")
        st.page_link("pages/1_🏠_Início.py", label="🏠 Início")
        # "Novo Acordo" foi removido do menu (decisão Erick 13/05/2026)
        # Agora se cria acordo pela tela do cliente: Clientes → Cliente → Novo Acordo
        st.page_link("pages/3_🧮_Calculadora.py", label="🧮 Calculadora")
        st.page_link("pages/2b_📥_Importar_Acordo.py", label="📥 Importar Acordo")
        st.page_link("pages/4_📊_Acordos.py", label="📊 Acordos")
        st.page_link("pages/5_🏢_Clientes.py", label="🏢 Clientes")

        # Parcelas Confirmadas: Admin e Cobrança (Diretoria não vê)
        if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA):
            st.page_link(
                "pages/6_✅_Parcelas_Confirmadas.py",
                label="✅ Parcelas Confirmadas",
            )

        # Admin e Diretoria têm acesso à administração
        if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.DIRETORIA):
            st.markdown("---")
            st.markdown("**Administração**")
            st.page_link("pages/7_👥_Usuários.py", label="👥 Usuários")
            st.page_link("pages/8_⚙_Admin.py", label="⚙ Configurações")

        st.markdown("---")
        if st.button("🚪 Sair", use_container_width=True):
            deslogar()
            st.rerun()


# ============================================================
# ROTEAMENTO
# ============================================================

def main():
    usuario = usuario_logado()
    if usuario is None:
        _esconder_navegacao()
        tela_login()
    else:
        _mostrar_navegacao_fixa()
        sidebar_logado(usuario)
        from src.telas.inicio import renderizar_inicio
        renderizar_inicio(usuario)


main()
