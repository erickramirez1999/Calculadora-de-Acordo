"""
Tela "📊 Acordos" — consulta completa de todos os acordos do sistema.

Substitui a antiga tela Finalizados. Funcionalidades:
  - Filtros: termo (CNPJ, nome, código parceiro), período
  - Abas por status:
      * Em Andamento (cinza): ATIVO sem nenhuma parcela vencida
      * Atrasado (laranja): ATIVO com pelo menos uma parcela vencida
      * Quebra de Acordo (vermelha): QUEBRADO
      * Quitado (verde): QUITADO
  - Lista cards com nome do cliente + códigos dos parceiros
  - Clique no card abre o detalhe do acordo

Permissões: todos os perfis podem ver (igual ao Início).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import streamlit as st

from src.banco import repo_acordo
from src.banco.repo_acordo import AcordoResumo
from src.modelos.tipos import PerfilUsuario, StatusAcordo
from src.utils.feedback import drenar_mensagens
from src.utils.estilo import (
    AZUL_ESCURO, AMARELO, VERDE, AZUL_VIVO,
    barra_progresso, badge_status_acordo,
)
from src.utils.formatadores import (
    formatar_brl, formatar_data, normalizar_busca,
)
from src.utils.marca import AZUL_ESCURO as MARCA_AZUL


# Cores das abas
COR_EM_ANDAMENTO = "#6C757D"      # cinza
COR_ATRASADO = "#FF8C00"          # laranja
COR_QUEBRA = "#DC3545"            # vermelho
COR_QUITADO = "#0F8C3B"           # verde


def renderizar_acordos(usuario):
    drenar_mensagens()
    st.markdown(f"<h1 style='color:{MARCA_AZUL}'>📊 Acordos</h1>", unsafe_allow_html=True)
    st.caption(
        "Consulta completa de acordos com filtros avançados. "
        "Use as abas pra filtrar por status."
    )

    # ============ FILTROS ============
    with st.container():
        col_t, col_dini, col_dfim = st.columns([3, 1.5, 1.5])
        with col_t:
            termo = st.text_input(
                "🔍 Pesquisar",
                placeholder="CNPJ, nome do cliente, código do parceiro, vendedor, nº nota...",
                label_visibility="collapsed",
                key="acordos_termo",
            )
        with col_dini:
            data_ini = st.date_input(
                "Data inicial",
                value=None,
                format="DD/MM/YYYY",
                key="acordos_data_ini",
            )
        with col_dfim:
            data_fim = st.date_input(
                "Data final",
                value=None,
                format="DD/MM/YYYY",
                key="acordos_data_fim",
            )

    # ============ BUSCAR DADOS ============
    # Pega TODOS os acordos (todos os status)
    resumos = repo_acordo.listar_resumos(
        status_em=[
            StatusAcordo.ATIVO, StatusAcordo.QUITADO,
            StatusAcordo.QUEBRADO, StatusAcordo.PENDENTE_APROVACAO,
            StatusAcordo.CANCELADO,
        ],
    )

    # Aplicar filtros
    resumos = _filtrar_por_termo(resumos, termo)
    resumos = _filtrar_por_periodo(resumos, data_ini, data_fim)

    # Classificar em buckets
    em_andamento, atrasados, quebrados, quitados = _classificar(resumos)

    # ============ ABAS POR STATUS ============
    st.markdown("<br>", unsafe_allow_html=True)
    aba_em_andamento, aba_atrasado, aba_quebra, aba_quitado = st.tabs([
        f"⚪ Em Andamento · {len(em_andamento)}",
        f"🟠 Atrasado · {len(atrasados)}",
        f"🔴 Quebra de Acordo · {len(quebrados)}",
        f"🟢 Quitado · {len(quitados)}",
    ])

    with aba_em_andamento:
        _renderizar_lista(em_andamento, COR_EM_ANDAMENTO, "Em Andamento")
    with aba_atrasado:
        _renderizar_lista(atrasados, COR_ATRASADO, "Atrasado")
    with aba_quebra:
        _renderizar_lista(quebrados, COR_QUEBRA, "Quebra de Acordo")
    with aba_quitado:
        _renderizar_lista(quitados, COR_QUITADO, "Quitado")


def _filtrar_por_termo(resumos: List[AcordoResumo], termo: str) -> List[AcordoResumo]:
    """Filtra por termo (cliente, CNPJ, código parceiro, vendedor, número nota)."""
    if not termo or not termo.strip():
        return resumos

    termo_norm = normalizar_busca(termo)

    def matcha(r: AcordoResumo) -> bool:
        # Campos diretos
        if termo_norm in normalizar_busca(r.cliente_nome):
            return True
        if termo_norm in normalizar_busca(r.numero_interno):
            return True
        if termo_norm in normalizar_busca(r.negociador_nome):
            return True

        # CNPJ e dados do cliente
        from src.banco.conexao import obter_conexao
        cur = obter_conexao().execute(
            "SELECT cnpj, contato FROM cliente WHERE id = ?;",
            (r.cliente_id,),
        )
        row = cur.fetchone()
        if row:
            for campo in row:
                if campo and termo_norm in normalizar_busca(str(campo)):
                    return True

        # Códigos de parceiro, razão social, vendedor, nº nota
        cur = obter_conexao().execute(
            """
            SELECT codigo_parceiro, razao_social_parceiro,
                   codigo_vendedor, nome_vendedor, numero_nota, numero_unico
            FROM boleto WHERE acordo_id = ?;
            """,
            (r.id,),
        )
        for row in cur.fetchall():
            for campo in row:
                if campo and termo_norm in normalizar_busca(str(campo)):
                    return True
        return False

    return [r for r in resumos if matcha(r)]


def _filtrar_por_periodo(
    resumos: List[AcordoResumo],
    data_ini,
    data_fim,
) -> List[AcordoResumo]:
    """Filtra acordos por data de criação."""
    if not data_ini and not data_fim:
        return resumos

    filtrados = []
    for r in resumos:
        # data_criacao pode vir como str ISO ou date
        dc = r.data_criacao
        if isinstance(dc, str):
            try:
                from datetime import datetime
                dc = datetime.fromisoformat(dc[:19]).date()
            except Exception:
                continue

        if data_ini and dc < data_ini:
            continue
        if data_fim and dc > data_fim:
            continue
        filtrados.append(r)

    return filtrados


def _classificar(resumos: List[AcordoResumo]):
    """
    Divide os acordos em 4 buckets:
      - Em Andamento: ATIVO sem atraso
      - Atrasado: ATIVO com pelo menos uma parcela vencida
      - Quebra: QUEBRADO
      - Quitado: QUITADO

    Regras (Erick):
      - Quebrado NUNCA aparece em Em Andamento ou Atrasado
      - Acordo atrasado SIM pode aparecer apenas em Atrasado (não duplica)
    """
    em_andamento = []
    atrasados = []
    quebrados = []
    quitados = []

    for r in resumos:
        if r.status == StatusAcordo.QUEBRADO:
            quebrados.append(r)
        elif r.status == StatusAcordo.QUITADO:
            quitados.append(r)
        elif r.status == StatusAcordo.ATIVO:
            if r.parcelas_em_atraso > 0:
                atrasados.append(r)
            else:
                em_andamento.append(r)
        # PENDENTE_APROVACAO e CANCELADO vão pra "Em Andamento" (não atrasado)
        elif r.status == StatusAcordo.PENDENTE_APROVACAO:
            em_andamento.append(r)
        # CANCELADO não aparece em nenhum bucket (decisão: só os 4 listados)

    return em_andamento, atrasados, quebrados, quitados


def _renderizar_lista(resumos: List[AcordoResumo], cor_borda: str, titulo: str):
    """Renderiza a lista de cards de uma aba."""
    if not resumos:
        st.info(f"Nenhum acordo no status '{titulo}'.")
        return

    # Total
    total_valor = sum(r.saldo_devedor for r in resumos)
    st.markdown(
        f"<div style='color:#666; font-size:14px; margin-bottom:12px;'>"
        f"<b>{len(resumos)}</b> acordo(s) · "
        f"Saldo total: <b style='color:{cor_borda};'>{formatar_brl(total_valor)}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for r in resumos:
        _render_card(r, cor_borda)


def _render_card(r: AcordoResumo, cor_borda: str):
    """Renderiza 1 card de acordo na lista."""
    # Pega códigos de parceiros do acordo
    parceiros = repo_acordo.listar_codigos_parceiro_do_acordo(r.id)

    # Detecta grupo econômico
    eh_grupo_economico = len(parceiros) >= 2

    parc_chips = " ".join(
        f"<span style='font-size:11px; background:#E9ECEF; border-radius:10px; "
        f"padding:2px 8px; margin-right:4px; color:#444;'>"
        f"{p['codigo_parceiro']}/E{p['empresa']}</span>"
        for p in parceiros[:5]
    )
    if len(parceiros) > 5:
        parc_chips += f"<span style='font-size:11px; color:#666;'>+{len(parceiros)-5}</span>"

    selo_grupo = ""
    if eh_grupo_economico:
        selo_grupo = (
            f"<span style='font-size:10px; background:{AMARELO}; color:{AZUL_ESCURO}; "
            f"border-radius:4px; padding:2px 8px; margin-left:6px; font-weight:700;'>"
            f"🏢 GRUPO ECONÔMICO · {len(parceiros)} CNPJs</span>"
        )

    info_extra = ""
    if r.parcelas_em_atraso > 0:
        info_extra = (
            f" · <span style='color:{COR_ATRASADO}; font-weight:700;'>"
            f"⚠ {r.parcelas_em_atraso} parcela(s) atrasada(s)</span>"
        )

    st.markdown(
        f"""
<div style="border-left:5px solid {cor_borda}; background:#FFFFFF;
            border-radius:6px; padding:14px 18px; margin-bottom:12px;
            box-shadow:0 1px 3px rgba(0,0,0,0.06);">
    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div style="flex: 1;">
            <div style="font-size:13px; color:#666; margin-bottom: 2px;">
                {r.numero_interno}{selo_grupo}
            </div>
            <div style="font-size:17px; font-weight:700; color:{AZUL_ESCURO}; margin-bottom: 6px;">
                {r.cliente_nome}
            </div>
            <div style="margin-bottom: 6px;">{parc_chips}</div>
            <div style="font-size:12px; color:#444;">
                Negociador: <b>{r.negociador_nome}</b> ·
                {r.parcelas_pagas}/{r.quantidade_parcelas} parcelas pagas{info_extra}
            </div>
        </div>
        <div style="text-align:right; min-width: 200px;">
            <div style="font-size:12px; color:#666;">Saldo devedor</div>
            <div style="font-size:19px; font-weight:700; color:{AZUL_ESCURO};">
                {formatar_brl(r.saldo_devedor)}
            </div>
            <div style="margin-top: 4px;">{badge_status_acordo(r.status.value)}</div>
        </div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "👁 Ver detalhes",
        key=f"acordo_det_{r.id}_{cor_borda}",
        use_container_width=False,
    ):
        st.session_state["acordo_id_aberto"] = r.id
        st.rerun()
