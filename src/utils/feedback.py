"""
Sistema unificado de feedback para o LLE Acordos.

Resolve o problema crônico de "tela travada após clicar em botão":
- Toda ação destrutiva ou demorada DEVE usar `executar_acao()` que mostra
  spinner durante a execução.
- Mensagens de sucesso/erro são enfileiradas e drenadas no topo da tela
  pra sobreviverem ao rerun (sem duplicar).
- Botões de confirmação têm cleanup automático.

Padrão de uso:

    from src.utils.feedback import executar_acao, drenar_mensagens

    def renderizar_tela(usuario):
        drenar_mensagens()  # SEMPRE como primeira linha visual

        if st.button("Excluir"):
            executar_acao(
                rotulo="Excluindo...",
                funcao=lambda: repo.deletar(id),
                sucesso="Item excluído com sucesso!",
            )
"""
from __future__ import annotations

from typing import Callable, Any
import streamlit as st


FILA_KEY = "_fila_mensagens"


def enfileirar(tipo: str, texto: str) -> None:
    """Adiciona uma mensagem à fila pra ser drenada após o próximo rerun."""
    if FILA_KEY not in st.session_state:
        st.session_state[FILA_KEY] = []
    st.session_state[FILA_KEY].append((tipo, texto))


def drenar_mensagens() -> None:
    """
    Exibe e remove TODAS as mensagens enfileiradas.

    Chame como PRIMEIRA linha de cada renderizar_*(). Suporta:
      - sucesso → st.success
      - erro → st.error
      - aviso → st.warning
      - info → st.info
      - toast → st.toast (banner pequeno do canto)
    """
    fila = st.session_state.pop(FILA_KEY, [])
    for tipo, texto in fila:
        if tipo == "sucesso":
            st.success(texto)
        elif tipo == "erro":
            st.error(texto)
        elif tipo == "aviso":
            st.warning(texto)
        elif tipo == "info":
            st.info(texto)
        elif tipo == "toast":
            st.toast(texto, icon="✅")
        else:
            st.write(texto)


def executar_acao(
    rotulo: str,
    funcao: Callable[[], Any],
    sucesso: str | None = None,
    erro_prefixo: str = "Erro",
    fazer_rerun: bool = True,
    callback_sucesso: Callable[[Any], None] | None = None,
) -> tuple[bool, Any]:
    """
    Executa uma função com:
      - st.spinner com o rótulo (feedback visual durante a operação)
      - try/except automático (mostra erro detalhado se falhar)
      - mensagem de sucesso enfileirada (sobrevive ao rerun)
      - rerun automático após sucesso (a menos que fazer_rerun=False)

    Retorna (sucesso: bool, resultado: Any).

    Use sempre que o clique disparar:
      - INSERT/UPDATE/DELETE no banco
      - Upload de arquivo
      - Cálculo demorado
      - Qualquer operação que possa demorar > 0.5s
    """
    try:
        with st.spinner(rotulo):
            resultado = funcao()
        if sucesso:
            enfileirar("sucesso", sucesso)
        if callback_sucesso:
            callback_sucesso(resultado)
        if fazer_rerun:
            st.rerun()
        return True, resultado
    except Exception as e:
        st.error(f"❌ {erro_prefixo}: {type(e).__name__}: {e}")
        with st.expander("🔍 Detalhes técnicos", expanded=False):
            st.exception(e)
        return False, None


def confirmar_e_executar(
    chave_estado: str,
    rotulo_botao: str,
    pergunta_confirmacao: str,
    funcao: Callable[[], Any],
    sucesso: str | None = None,
    erro_prefixo: str = "Erro",
    tipo_botao_inicial: str = "secondary",
    icone: str = "⚠️",
) -> None:
    """
    Padrão de 2 etapas: 1º clique abre confirmação, 2º clique executa.

    chave_estado: chave única no session_state pra controlar o estado de confirmação.
    """
    confirmando = st.session_state.get(chave_estado, False)

    if not confirmando:
        if st.button(rotulo_botao, type=tipo_botao_inicial, use_container_width=True, key=f"btn_{chave_estado}"):
            st.session_state[chave_estado] = True
            st.rerun()
    else:
        st.warning(f"{icone} {pergunta_confirmacao}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✓ Confirmar", type="primary", use_container_width=True, key=f"sim_{chave_estado}"):
                st.session_state.pop(chave_estado, None)
                executar_acao(rotulo=f"Processando...", funcao=funcao, sucesso=sucesso, erro_prefixo=erro_prefixo)
        with c2:
            if st.button("Cancelar", use_container_width=True, key=f"nao_{chave_estado}"):
                st.session_state.pop(chave_estado, None)
                st.rerun()
