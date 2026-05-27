"""
Tela Inicial — Dashboard executivo.

Layout enxuto estilo plataforma de referência:
  1. KPIs grandes coloridos no topo
  2. Gráfico de recebimentos dos últimos 30 dias
  3. Blocos compactos: vencimentos hoje, aguardando, confirmadas hoje, promessas, rascunhos
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import streamlit as st

from src.banco import repo_acordo, repo_extras, repos_auxiliares
from src.modelos.tipos import PerfilUsuario, StatusAcordo
from src.utils.formatadores import formatar_brl, formatar_data
from src.utils.marca import AZUL_ESCURO, AMARELO, VERDE, AZUL_VIVO


COR_KPI_AZUL = "#0071FE"
COR_KPI_VERDE = "#0F8C3B"
COR_KPI_LARANJA = "#FF8C00"
COR_KPI_VERMELHO = "#DC3545"
COR_KPI_CINZA = "#6C757D"
COR_KPI_AMARELO = "#FAC318"


def renderizar_inicio(usuario):
    """Tela inicial pós-login - Dashboard executivo."""
    primeiro_nome = usuario.nome.split()[0] if usuario.nome else "usuário"
    st.markdown(
        f"<h1 style='color:{AZUL_ESCURO};margin-bottom:4px;'>Olá, {primeiro_nome}!</h1>",
        unsafe_allow_html=True,
    )
    st.caption("Resumo executivo da carteira de acordos")

    # ─── FILTRO DE CARTEIRA (por negociador) ─────────────────────────
    negociador_filtro_id = _seletor_carteira()

    _kpis_grandes(usuario, negociador_filtro_id)

    st.markdown("<br>", unsafe_allow_html=True)

    col_graf, col_venc = st.columns([3, 2])
    with col_graf:
        _grafico_recebimentos_30_dias(usuario, negociador_filtro_id)
    with col_venc:
        _bloco_compacto_vencimentos_hoje(usuario, negociador_filtro_id)

    st.markdown("<br>", unsafe_allow_html=True)

    if usuario.perfil == PerfilUsuario.ADMIN:
        _bloco_pagamentos_aguardando(usuario, negociador_filtro_id)
        st.markdown("<br>", unsafe_allow_html=True)

    # Bloco novo: propostas do cliente (admin/diretoria/cobranca veem)
    _bloco_propostas_cliente(usuario)

    if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA):
        _bloco_confirmadas_hoje(usuario, negociador_filtro_id)
        st.markdown("<br>", unsafe_allow_html=True)

    _bloco_promessas_hoje(usuario, negociador_filtro_id)

    st.markdown("<br>", unsafe_allow_html=True)

    _bloco_rascunhos(usuario)


def _seletor_carteira() -> Optional[int]:
    """
    Selectbox no topo do Dashboard pra filtrar tudo por negociador.
    Retorna o ID do negociador selecionado, ou None se "Todos".
    """
    negociadores = repo_acordo.listar_negociadores_com_acordos()

    if not negociadores:
        return None  # Ninguém tem acordo ainda, sem filtro

    # Monta opções: "Todos (X)" + cada negociador com sua qtd
    total_acordos = sum(n["qtd_acordos"] for n in negociadores)
    opcoes = {f"📊 Todos ({total_acordos} acordo(s))": None}
    for n in negociadores:
        opcoes[f"👤 {n['nome']} ({n['qtd_acordos']} acordo(s))"] = n["id"]

    escolha = st.selectbox(
        "🗂️ Carteira:",
        list(opcoes.keys()),
        index=0,
        key="dashboard_filtro_carteira",
        help="Filtra todo o dashboard pelos acordos de um negociador específico.",
    )
    return opcoes[escolha]


def _bloco_propostas_cliente(usuario):
    """Lista propostas de acordo enviadas pelos clientes pelo portal."""
    from src.banco import repo_portal
    propostas = repo_portal.listar_propostas_pendentes()
    if not propostas:
        return

    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
        f"📨 Propostas de cliente · {len(propostas)} aguardando análise</h3>",
        unsafe_allow_html=True,
    )
    st.caption("Propostas enviadas pelos clientes via Portal de Acordos.")

    for p in propostas[:10]:
        _render_proposta_item(p, usuario, key_prefix="inicio", mostrar_btn_cliente=True)
        st.markdown("<hr style='margin:4px 0; border-color:#EEE;'>", unsafe_allow_html=True)


def _render_proposta_item(p, usuario, key_prefix="prop", mostrar_btn_cliente=True):
    """Renderiza 1 proposta de cliente com botões de ação.
    
    Args:
        p: dict da proposta (com nome_principal, cnpj, etc)
        usuario: usuário logado (pra registrar quem analisou)
        key_prefix: prefixo único pras keys dos botões (evita conflito)
        mostrar_btn_cliente: se mostra o botão de abrir cliente (coluna extra)
    """
    from src.banco import repo_portal

    col_info, col_val, col_btns = st.columns([3, 1.5, 2.5])

    with col_info:
        obs_str = ""
        if p.get("observacao_cliente"):
            obs_str = (
                f"<br><span style='font-size:11px; color:#666; font-style:italic;'>"
                f"💬 \"{p['observacao_cliente'][:80]}\"</span>"
            )
        # Nome do cliente sempre clicável via botão inline
        st.markdown(
            f"<span style='font-size:13px; color:#555;'>"
            f"{p.get('cnpj') or 'sem CNPJ'}</span><br>"
            f"<span style='font-size:12px; color:#555;'>"
            f"{p['qtd_parcelas']}x {p['periodicidade'].lower()} · "
            f"1ª em {formatar_data(p['data_primeira_parcela'])}"
            f"</span>{obs_str}",
            unsafe_allow_html=True,
        )
        # Nome como botão clicável (vai pro perfil do cliente)
        if st.button(
            f"🏢 {p.get('nome_principal', '?')}",
            key=f"{key_prefix}_nome_cli_{p['id']}",
            help="Abrir perfil do cliente",
        ):
            st.session_state["cliente_aberto_id"] = p["cliente_id"]
            st.switch_page("pages/5_🏢_Clientes.py")

    with col_val:
        st.markdown(
            f"<div style='text-align:right; font-weight:700; "
            f"color:#0F8C3B; font-size:16px;'>"
            f"{formatar_brl(p['valor_parcela'])}<br>"
            f"<span style='font-size:10px; color:#666;'>por parcela</span></div>",
            unsafe_allow_html=True,
        )

    with col_btns:
        ba, br = st.columns(2)
        with ba:
            if st.button(
                "✅ Aceitar", key=f"{key_prefix}_aceitar_{p['id']}",
                type="primary", use_container_width=True,
            ):
                repo_portal.marcar_proposta_analisada(
                    p["id"], "ACEITA", usuario.id,
                    observacao=f"Aceita via {key_prefix}",
                )
                # Cria acordo automaticamente a partir da proposta
                _criar_acordo_da_proposta(p, usuario)
                st.rerun()
        with br:
            if st.button(
                "❌ Recusar", key=f"{key_prefix}_recusar_{p['id']}",
                use_container_width=True,
            ):
                repo_portal.marcar_proposta_analisada(
                    p["id"], "RECUSADA", usuario.id,
                )
                repo_portal.restaurar_titulos_em_aberto(p["titulos_ids"])
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)


def _criar_acordo_da_proposta(p: dict, usuario) -> None:
    """
    Cria um acordo automaticamente a partir de uma proposta aceita do portal.
    Busca os títulos avulsos da proposta, monta boletos e parcelas via FIFO
    e salva o acordo com status ATIVO.
    """
    from src.banco import repo_portal, repo_cliente
    from src.banco.repo_acordo import salvar_acordo_completo
    from src.modelos.tipos import (
        Boleto, Empresa, OrigemDado, Parcela, StatusParcela,
        TipoCobranca, Periodicidade, StatusAcordo,
    )
    from src.servicos.fifo import montar_acordo_qtd_fixa, montar_acordo_valor_fixo
    from datetime import datetime

    try:
        # Busca os títulos avulsos da proposta
        conn = __import__("src.banco.conexao", fromlist=["obter_conexao"]).obter_conexao()
        titulos_ids = p["titulos_ids"]
        if not titulos_ids:
            st.error("❌ Proposta sem títulos vinculados.")
            return

        placeholders = ",".join("?" * len(titulos_ids))
        cur = conn.execute(
            f"SELECT * FROM titulo_avulso WHERE id IN ({placeholders});",
            tuple(titulos_ids),
        )
        titulos = [dict(r) for r in cur.fetchall()]

        if not titulos:
            st.error("❌ Títulos da proposta não encontrados.")
            return

        # Monta boletos a partir dos títulos avulsos
        boletos = []
        for t in titulos:
            b = Boleto(
                codigo_parceiro=t["codigo_parceiro"],
                razao_social_parceiro=t["razao_social_parceiro"],
                empresa=Empresa(int(t["empresa"])),
                codigo_vendedor=t.get("codigo_vendedor", 0),
                nome_vendedor=t.get("nome_vendedor", ""),
                vencimento=datetime.fromisoformat(t["vencimento"]).date()
                    if isinstance(t["vencimento"], str) else t["vencimento"],
                numero_nota=t.get("numero_nota", ""),
                numero_unico=t.get("numero_unico", 0),
                principal=float(t["principal"]),
                dias_atraso=0,
                fim_juros=date.today(),
                juros=0.0, multa=0.0, total=float(t["principal"]),
                parcelas_alocadas=[], distribuicao=[],
                origem=OrigemDado.MANUAL,
            )
            boletos.append(b)

        data_acordo = date.today()
        data_primeira = datetime.fromisoformat(p["data_primeira_parcela"]).date() \
            if isinstance(p["data_primeira_parcela"], str) else p["data_primeira_parcela"]

        # Calcula parcelas via FIFO (sem juros — proposta já veio com valor do cliente)
        # Usa qtd_parcelas e valor_parcela da proposta
        qtd = int(p["qtd_parcelas"])
        periodicidade = p["periodicidade"].upper()

        parcelas = montar_acordo_qtd_fixa(
            boletos=boletos,
            data_acordo=data_acordo,
            pct_juros_mes=0.0,
            pct_multa=0.0,
            qtd_parcelas=qtd,
            data_primeira_parcela=data_primeira,
            periodicidade=Periodicidade(periodicidade),
            intervalo_personalizado_dias=1,
        )

        # Busca ou cria cliente
        cliente = repo_cliente.buscar_por_id(p["cliente_id"])
        if not cliente:
            st.error("❌ Cliente não encontrado.")
            return

        # Salva o acordo
        acordo_id = salvar_acordo_completo(
            cliente_id=cliente.id,
            negociador_id=usuario.id,
            criado_por_id=usuario.id,
            data_acordo=data_acordo,
            pct_juros_mes_titulos=0.0,
            pct_multa_titulos=0.0,
            pct_juros_mora_mes=5.0,
            pct_multa_mora=2.0,
            pct_desconto=0.0,
            tipo_cobranca=TipoCobranca.PIX,
            periodicidade=Periodicidade(periodicidade),
            intervalo_personalizado_dias=1,
            boletos=boletos,
            parcelas=parcelas,
            status_inicial=StatusAcordo.ATIVO,
            observacoes=f"Acordo gerado via Portal de Renegociação. "
                        f"Proposta do cliente: {p.get('observacao_cliente', '')}",
        )

        repos_auxiliares.registrar_log(
            usuario_id=usuario.id, usuario_nome=usuario.nome,
            acao="ACEITAR_PROPOSTA_PORTAL", entidade="acordo", entidade_id=acordo_id,
            contexto=p.get("nome_principal", ""),
            depois={"proposta_id": p["id"], "qtd_parcelas": qtd},
        )

        st.success(
            f"✅ Acordo criado automaticamente para **{p.get('nome_principal', 'cliente')}** · "
            f"{qtd}x · 1ª parcela em {formatar_data(data_primeira)}"
        )

    except Exception as e:
        st.error(f"❌ Erro ao criar acordo: {str(e)[:300]}")


def _kpis_grandes(usuario, negociador_id: Optional[int] = None):
    """6 cards de KPI no topo."""
    todos = repo_acordo.listar_resumos(
        status_em=[
            StatusAcordo.ATIVO, StatusAcordo.QUITADO,
            StatusAcordo.QUEBRADO, StatusAcordo.PENDENTE_APROVACAO,
        ],
        negociador_id=negociador_id,
    )
    ativos = [a for a in todos if a.status == StatusAcordo.ATIVO]
    quitados = [a for a in todos if a.status == StatusAcordo.QUITADO]
    atrasados = [a for a in ativos if a.parcelas_em_atraso > 0]
    em_andamento = [a for a in ativos if a.parcelas_em_atraso == 0]

    total_carteira = sum(a.valor_total for a in todos)
    total_recebido = sum(a.valor_total - a.saldo_devedor for a in todos)
    saldo_devedor_total = sum(a.saldo_devedor for a in todos if a.status != StatusAcordo.QUEBRADO)

    confirmadas_hoje = repo_acordo.listar_parcelas_confirmadas(
        apenas_hoje=True, negociador_id=negociador_id,
    )
    valor_recebido_hoje = sum(c["valor_pago"] for c in confirmadas_hoje)

    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)

    with c1:
        _card_kpi("💼 Total da Carteira", formatar_brl(total_carteira),
                  f"{len(todos)} acordo(s)", COR_KPI_AZUL)
    with c2:
        _card_kpi("💰 Total Recebido", formatar_brl(total_recebido),
                  f"de {formatar_brl(total_carteira)}", COR_KPI_VERDE)
    with c3:
        _card_kpi("📉 Saldo Devedor", formatar_brl(saldo_devedor_total),
                  f"{len(ativos)} acordo(s) ativo(s)", COR_KPI_AZUL)
    with c4:
        _card_kpi("⚪ Em Andamento", str(len(em_andamento)),
                  "sem atraso", COR_KPI_CINZA)
    with c5:
        _card_kpi("🟠 Atrasados", str(len(atrasados)),
                  "com parcela vencida", COR_KPI_LARANJA)
    with c6:
        _card_kpi("✅ Recebido hoje", formatar_brl(valor_recebido_hoje),
                  f"{len(confirmadas_hoje)} parcela(s)", COR_KPI_VERDE)


def _card_kpi(titulo: str, valor: str, sublabel: str, cor: str):
    st.markdown(
        f"""
<div style="background:#FFFFFF; border-left:5px solid {cor};
            padding:14px 18px; border-radius:8px;
            box-shadow:0 1px 4px rgba(0,0,0,0.08); height:100px;">
    <div style="font-size:13px; color:#666; font-weight:600; margin-bottom:6px;">
        {titulo}
    </div>
    <div style="font-size:22px; font-weight:800; color:{cor}; line-height:1.1;">
        {valor}
    </div>
    <div style="font-size:11px; color:#999; margin-top:4px;">
        {sublabel}
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _grafico_recebimentos_30_dias(usuario, negociador_id: Optional[int] = None):
    """Gráfico de linha com recebimentos dos últimos 30 dias."""
    st.markdown(
        f"<h4 style='color:{AZUL_ESCURO}; margin-bottom:6px;'>"
        f"📈 Recebimentos · Últimos 30 dias</h4>",
        unsafe_allow_html=True,
    )

    data_inicio = date.today() - timedelta(days=29)
    confirmadas = repo_acordo.listar_parcelas_confirmadas(
        data_inicio=data_inicio, data_fim=date.today(),
        negociador_id=negociador_id,
    )

    if not confirmadas:
        st.info("Nenhum pagamento confirmado nos últimos 30 dias.")
        return

    from collections import defaultdict
    por_dia = defaultdict(float)
    for c in confirmadas:
        dt = c.get("confirmado_em")
        if not dt:
            continue
        if isinstance(dt, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(dt[:19]).date()
            except Exception:
                continue
        else:
            dt = dt.date() if hasattr(dt, "date") else dt
        por_dia[dt] += c["valor_pago"]

    dias = []
    valores = []
    for i in range(30):
        d = data_inicio + timedelta(days=i)
        dias.append(d)
        valores.append(por_dia.get(d, 0.0))

    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dias, y=valores,
        mode='lines+markers',
        line=dict(color=AZUL_VIVO, width=2.5),
        marker=dict(size=6, color=AZUL_VIVO),
        fill='tozeroy',
        fillcolor='rgba(0, 113, 254, 0.1)',
        hovertemplate='%{x|%d/%m}<br>R$ %{y:,.2f}<extra></extra>',
    ))
    fig.update_layout(
        height=240,
        margin=dict(l=0, r=0, t=10, b=10),
        showlegend=False,
        xaxis=dict(tickformat="%d/%m", showgrid=False, tickfont=dict(size=10)),
        yaxis=dict(tickprefix="R$ ", tickformat=",.0f",
                   showgrid=True, gridcolor="#EEE", tickfont=dict(size=10)),
        plot_bgcolor='white',
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    total = sum(valores)
    st.caption(f"Total no período: **{formatar_brl(total)}** · {len(confirmadas)} pagamento(s)")


def _bloco_compacto_vencimentos_hoje(usuario, negociador_id: Optional[int] = None):
    """Lista compacta de parcelas vencendo HOJE."""
    st.markdown(
        f"<h4 style='color:{AZUL_ESCURO}; margin-bottom:6px;'>"
        f"📅 Vencimentos de Hoje</h4>",
        unsafe_allow_html=True,
    )

    from src.banco.conexao import obter_conexao
    sql = """
        SELECT
            p.id AS pid,
            p.numero AS pnumero,
            p.valor_original AS pvalor,
            a.numero_interno,
            c.nome_principal AS cliente_nome,
            a.id AS acordo_id
        FROM parcela p
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        WHERE DATE(p.vencimento_atual) = DATE('now')
          AND p.status NOT IN ('QUITADA')
          AND a.status = 'ATIVO'
    """
    params: list = []
    if negociador_id:
        sql += " AND a.negociador_id = ?"
        params.append(negociador_id)
    sql += " ORDER BY c.nome_principal LIMIT 10;"
    cur = obter_conexao().execute(sql, params)
    vencimentos = [dict(r) for r in cur.fetchall()]

    if not vencimentos:
        st.markdown(
            f"<div style='background:#F8F9FA; border-radius:6px; padding:16px; "
            f"text-align:center; color:#666; font-size:14px;'>"
            f"🎉 Sem parcelas vencendo hoje</div>",
            unsafe_allow_html=True,
        )
        return

    for v in vencimentos[:5]:
        st.markdown(
            f"""
<div style="background:#FFF3CD; border-left:3px solid {COR_KPI_AMARELO};
            padding:8px 12px; border-radius:4px; margin-bottom:6px;">
    <div style="font-size:13px; font-weight:600; color:{AZUL_ESCURO};">
        {v['cliente_nome']}
    </div>
    <div style="font-size:11px; color:#666;">
        {v['numero_interno']} · Parc. {v['pnumero']} ·
        <b>{formatar_brl(v['pvalor'])}</b>
    </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    if len(vencimentos) > 5:
        st.caption(f"+ {len(vencimentos) - 5} outros vencimentos hoje")


def _bloco_pagamentos_aguardando(usuario, negociador_id: Optional[int] = None):
    """Pagamentos que cobrança registrou e admin precisa confirmar."""
    pendentes = repo_acordo.listar_pagamentos_aguardando_confirmacao(
        negociador_id=negociador_id,
    )
    if not pendentes:
        return

    total = sum(p["valor"] for p in pendentes)

    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
        f"💰 Aguardando sua confirmação · {len(pendentes)} · "
        f"<span style='color:{COR_KPI_VERDE};'>{formatar_brl(total)}</span></h3>",
        unsafe_allow_html=True,
    )

    for p in pendentes[:5]:
        col_info, col_v, col_btns = st.columns([3, 1.5, 2.5])
        with col_info:
            st.markdown(
                f"**{p['cliente_nome']}** · {p['numero_interno']}<br>"
                f"<span style='font-size:12px; color:#555;'>"
                f"Parc. {p['parcela_numero']} · "
                f"Registrado por {p['registrado_por_nome']}</span>",
                unsafe_allow_html=True,
            )
        with col_v:
            st.markdown(
                f"<div style='text-align:right; font-weight:700; "
                f"color:{COR_KPI_VERDE}; font-size:16px;'>"
                f"{formatar_brl(p['valor'])}</div>",
                unsafe_allow_html=True,
            )
        with col_btns:
            bc, be = st.columns(2)
            with bc:
                if st.button(
                    "✅ Confirmar",
                    key=f"pag_conf_inicio_{p['pagamento_id']}",
                    type="primary", use_container_width=True,
                ):
                    repo_acordo.confirmar_pagamento_admin(
                        p["pagamento_id"], usuario.id,
                    )
                    repos_auxiliares.registrar_log(
                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                        acao="CONFIRMAR_PAGAMENTO_ADMIN",
                        entidade="parcela", entidade_id=p["parcela_id"],
                        contexto=f"{p['numero_interno']} · Parc. {p['parcela_numero']}",
                        depois={"valor": p["valor"]},
                    )
                    st.rerun()
            with be:
                if st.button(
                    "❌ Estornar",
                    key=f"pag_est_inicio_{p['pagamento_id']}",
                    use_container_width=True,
                ):
                    repo_acordo.estornar_pagamento(p["pagamento_id"])
                    repos_auxiliares.registrar_log(
                        usuario_id=usuario.id, usuario_nome=usuario.nome,
                        acao="ESTORNAR_PAGAMENTO",
                        entidade="parcela", entidade_id=p["parcela_id"],
                        contexto=f"{p['numero_interno']} · Parc. {p['parcela_numero']}",
                        antes={"valor": p["valor"]},
                    )
                    st.rerun()
        st.markdown("<hr style='margin:4px 0; border-color:#EEE;'>", unsafe_allow_html=True)

    if len(pendentes) > 5:
        st.caption(f"+ {len(pendentes) - 5} pagamento(s) — ver em cada acordo.")


def _bloco_confirmadas_hoje(usuario, negociador_id: Optional[int] = None):
    """Lembrete diário das parcelas confirmadas pelo admin hoje."""
    confirmadas = repo_acordo.listar_parcelas_confirmadas(
        apenas_hoje=True, negociador_id=negociador_id,
    )
    if not confirmadas:
        return

    total = sum(c["valor_pago"] for c in confirmadas)

    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
        f"✅ Parcelas confirmadas hoje · {len(confirmadas)} · "
        f"<span style='color:{COR_KPI_VERDE};'>{formatar_brl(total)}</span></h3>",
        unsafe_allow_html=True,
    )

    for c in confirmadas[:5]:
        st.markdown(
            f"""
<div style="background:#D4EDDA; color:#155724;
            padding:8px 12px; border-radius:4px; margin-bottom:6px;
            display:flex; justify-content:space-between;">
    <div>
        <b>✓ {c['cliente_nome']}</b> · {c['numero_interno']} ·
        Parc. {c['parcela_numero']}
    </div>
    <div style="font-weight:700;">
        {formatar_brl(c['valor_pago'])}
    </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    if len(confirmadas) > 5:
        st.caption(f"+ {len(confirmadas) - 5} — ver tudo em 'Parcelas Confirmadas'.")


def _bloco_promessas_hoje(usuario, negociador_id: Optional[int] = None):
    """Promessas de pagamento prometidas para HOJE."""
    try:
        promessas = repo_extras.listar_promessas_para_data(date.today())
    except Exception:
        promessas = []

    if usuario.perfil == PerfilUsuario.COBRANCA:
        promessas = [p for p in promessas if p.get("negociador_id") == usuario.id]

    # Filtro do dashboard (todos os perfis)
    if negociador_id:
        promessas = [p for p in promessas if p.get("negociador_id") == negociador_id]

    if not promessas:
        return

    total = sum(p.get("valor_prometido", 0) for p in promessas)

    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
        f"🤝 Promessas para hoje · {len(promessas)} · "
        f"<span style='color:{COR_KPI_AMARELO};'>{formatar_brl(total)}</span></h3>",
        unsafe_allow_html=True,
    )

    for p in promessas[:5]:
        valor_str = formatar_brl(p.get("valor_prometido", 0)) if p.get("valor_prometido") else ""
        st.markdown(
            f"""
<div style="background:#FFF3CD; padding:8px 12px;
            border-radius:4px; margin-bottom:6px;
            border-left:3px solid {COR_KPI_AMARELO};">
    <b>{p.get('cliente_nome', '—')}</b> · {p.get('acordo_numero', '')}<br>
    <span style='font-size:12px; color:#555;'>
        Negociador: {p.get('negociador_nome', '—')} · {valor_str}
    </span>
</div>
            """,
            unsafe_allow_html=True,
        )


def _bloco_rascunhos(usuario):
    """Rascunhos de acordos em aberto (todos os perfis veem)."""
    rascunhos = repos_auxiliares.listar_rascunhos_todos()
    if not rascunhos:
        return

    st.markdown(
        f"<h3 style='color:{AZUL_ESCURO}; margin-bottom:8px;'>"
        f"📝 Rascunhos em aberto · {len(rascunhos)}</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Acordos sendo elaborados pela equipe. Só o criador (ou admin) "
        "pode retomar ou excluir."
    )

    eh_admin = usuario.perfil == PerfilUsuario.ADMIN

    for r in rascunhos[:10]:
        criador_id = r.get("criado_por_id")
        pode_mexer = eh_admin or criador_id == usuario.id

        col_info, col_btns = st.columns([4, 2])
        with col_info:
            criado_em_fmt = formatar_data(r.get("criado_em"))
            atualizado_fmt = formatar_data(r.get("atualizado_em"))
            st.markdown(
                f"<div style='background:#F8F9FA; padding:8px 12px; "
                f"border-radius:4px; border-left:3px solid #6C757D;'>"
                f"<b>{r.get('nome', 'Sem nome')}</b><br>"
                f"<span style='font-size:12px; color:#555;'>"
                f"Criado por {r.get('criador_nome', '—')} em {criado_em_fmt} · "
                f"Atualizado: {atualizado_fmt} · "
                f"Passo {r.get('passo_atual', 1)}"
                f"</span></div>",
                unsafe_allow_html=True,
            )
        with col_btns:
            if pode_mexer:
                bc, bd = st.columns(2)
                with bc:
                    if st.button(
                        "▶ Retomar", key=f"retomar_{r['id']}",
                        use_container_width=True, type="primary",
                    ):
                        st.session_state["rascunho_retomar_id"] = r["id"]
                        st.switch_page("pages/2_➕_Novo_Acordo.py")
                with bd:
                    if st.button(
                        "🗑 Excluir", key=f"excluir_rasc_{r['id']}",
                        use_container_width=True,
                    ):
                        repos_auxiliares.excluir_rascunho(
                            r["id"], usuario.id, eh_admin=eh_admin,
                        )
                        st.rerun()
