"""
Tela: Importar Acordo Pronto.

Aceita 2 tipos de entrada:
1. Um ou mais PDFs de Termo de Acordo do LLE (formato preferido)
   — se vários, junta como grupo econômico, somando principal e parcelas
2. Um XLSX (formato antigo, com 2 abas ou 1 aba lado-a-lado)

Mostra ANTES de salvar: total do principal, total do acordo, juros embutidos
e quanto de juros está em cada parcela (média).
"""
from __future__ import annotations
import hashlib
from datetime import date, datetime
from time import time

import pandas as pd
import streamlit as st

from src.utils.feedback import drenar_mensagens

from src.banco import repo_cliente, repo_usuario
from src.banco.repo_acordo import salvar_acordo_completo
from src.modelos.tipos import (
    Boleto, Empresa, OrigemDado, Parcela, PerfilUsuario, Periodicidade,
    StatusAcordo, StatusParcela, TipoCobranca,
)
from src.servicos.importador_acordo import ler_acordo_xlsx
from src.servicos.parser_termo_pdf import (
    GrupoAcordo, TermoAcordoPDF, juntar_termos, ler_termo_acordo_pdf,
)


# Helper de formatação BR
def _fmt_real(v: float | int | None) -> str:
    if v is None:
        v = 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        f = 0.0
    return f"R$ {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def renderizar(usuario):
    drenar_mensagens()
    st.markdown("## 📥 Importar Acordo Pronto")
    st.caption(
        "Importa acordos já montados (PDF do sistema LLE ou XLSX) "
        "diretamente no banco, sem passar pelo wizard."
    )

    st.info(
        "**📄 PDFs (recomendado):** sobe um ou mais Termos de Acordo do Grupo LLE. "
        "Se subir vários, o sistema entende como **grupo econômico** e junta tudo "
        "num único acordo (soma o principal e o cronograma de parcelas).\n\n"
        "**📊 XLSX (alternativa):** sobe um arquivo Excel com boletos + cronograma. "
        "Suporta os formatos do MALUZIN (1 aba) e do export do próprio sistema (2 abas)."
    )

    # Mensagem persistente do último envio
    msg = st.session_state.pop("import_msg", None)
    if msg:
        tipo, texto, acordo_id = msg.get("tipo"), msg.get("texto"), msg.get("acordo_id")
        if tipo == "sucesso":
            st.success(texto)
            if acordo_id:
                if st.button("👉 Ver acordo criado", type="primary"):
                    st.session_state["detalhe_acordo_id"] = acordo_id
                    st.switch_page("pages/4_📊_Acordos.py")
        elif tipo == "aviso":
            st.warning(texto)
        else:
            st.error(texto)

    arquivos = st.file_uploader(
        "Arquivo(s) do acordo (PDF ou XLSX)",
        type=["pdf", "xlsx"],
        accept_multiple_files=True,
        key=st.session_state.get("imp_uploader_key", "imp_uploader_v1"),
    )

    if not arquivos:
        return

    # Hash combinado (anti-reprocesso)
    h = hashlib.md5()
    for a in arquivos:
        h.update(a.getvalue())
    hash_combinado = h.hexdigest()

    if st.session_state.get("imp_hash_processado") == hash_combinado:
        st.info(
            "ℹ️ **Esse conjunto de arquivos já foi processado nessa sessão.** "
            "Selecione outros ou recarregue a página pra começar de novo."
        )
        return

    # Detecta tipo
    pdfs = [a for a in arquivos if a.name.lower().endswith(".pdf")]
    xlsxs = [a for a in arquivos if a.name.lower().endswith(".xlsx")]

    if pdfs and xlsxs:
        st.error(
            "❌ Misture só de um tipo: PDFs OU XLSX, não os dois ao mesmo tempo."
        )
        return

    if xlsxs:
        if len(xlsxs) > 1:
            st.error(
                "❌ XLSX só aceita 1 arquivo por vez. "
                "Pra múltiplos clientes use PDFs do termo de acordo."
            )
            return
        _fluxo_xlsx(xlsxs[0], usuario, hash_combinado)
    else:
        _fluxo_pdfs(pdfs, usuario, hash_combinado)


# ============================================================
# FLUXO PDF (1 ou múltiplos)
# ============================================================

def _fluxo_pdfs(arquivos_pdf, usuario, hash_combinado):
    st.markdown("---")
    st.markdown(f"### 📄 {len(arquivos_pdf)} PDF(s) carregado(s)")

    # Lê todos
    termos = []
    erros = []
    for arq in arquivos_pdf:
        try:
            t = ler_termo_acordo_pdf(arq.getvalue())
            termos.append(t)
        except Exception as e:
            erros.append(f"{arq.name}: {e}")

    if erros:
        for e in erros:
            st.error(f"❌ Erro lendo arquivo — {e}")
        return

    if not termos:
        st.error("❌ Nenhum termo válido nos PDFs.")
        return

    # Mostra cada termo
    for i, (arq, t) in enumerate(zip(arquivos_pdf, termos), 1):
        with st.expander(f"📄 {arq.name} — {t.cnpj_devedor or '(CNPJ não identificado)'}", expanded=False):
            cc1, cc2 = st.columns(2)
            with cc1:
                st.write(f"**Devedor:** {t.nome_devedor or '—'}")
                st.write(f"**CNPJ:** {t.cnpj_devedor or '—'}")
                st.write(f"**Endereço:** {t.endereco or '—'}")
                st.write(f"**Cidade:** {t.cidade or '—'}")
            with cc2:
                st.metric("Títulos negociados", len(t.titulos))
                st.metric("Principal (soma)", _fmt_real(t.total_principal))
                st.metric("Acordo (parcelas)", _fmt_real(t.total_parcelas))
                if t.juros_embutidos > 0:
                    st.metric("Juros embutidos", _fmt_real(t.juros_embutidos), delta=None)

    # Junção (grupo econômico)
    grupo = juntar_termos(termos)
    is_grupo = len(termos) > 1

    st.markdown("---")
    if is_grupo:
        st.markdown("### 🏢 Grupo econômico — totais")
    else:
        st.markdown("### 💰 Totais do acordo")

    col1, col2, col3 = st.columns(3)
    col1.metric("Clientes no acordo", len(termos))
    col2.metric(
        "Total de títulos",
        sum(len(t.titulos) for t in termos),
    )
    col3.metric("Qtd parcelas", grupo.qtd_parcelas)

    col4, col5, col6 = st.columns(3)
    col4.metric("Total PRINCIPAL", _fmt_real(grupo.total_principal))
    col5.metric("Total do ACORDO", _fmt_real(grupo.total_parcelas_acordo))
    col6.metric(
        "Juros embutidos",
        _fmt_real(grupo.juros_total_embutido),
        delta=None,
        help="Diferença entre o total do acordo e o principal."
    )

    # Quanto de juros em cada parcela
    if grupo.juros_total_embutido > 0.01:
        st.warning(
            f"💡 **Juros embutidos:** {_fmt_real(grupo.juros_total_embutido)} no total.\n\n"
            f"Isso dá em média **{_fmt_real(grupo.juros_por_parcela)} de juros em cada parcela** "
            f"(de {grupo.qtd_parcelas} parcelas)."
        )
    elif abs(grupo.juros_total_embutido) <= 0.50:
        st.success(
            "✅ Acordo SEM JUROS — total das parcelas é igual ao principal."
        )
    else:
        st.error(
            f"⚠️ O acordo está MENOR que o principal "
            f"em {_fmt_real(abs(grupo.juros_total_embutido))}. Verifique."
        )

    # Cronograma somado (preview)
    cronograma = grupo.cronograma_somado
    with st.expander(f"🗓️ Cronograma somado ({len(cronograma)} parcelas)"):
        df_cron = pd.DataFrame([
            {"Parcela": p.numero, "Vencimento": p.vencimento.isoformat(), "Valor": p.valor}
            for p in cronograma
        ])
        st.dataframe(df_cron, use_container_width=True, height=280)

    # Títulos (preview)
    with st.expander(f"📋 Todos os títulos ({sum(len(t.titulos) for t in termos)})"):
        linhas = []
        for t in termos:
            for tit in t.titulos:
                linhas.append({
                    "CNPJ devedor": t.cnpj_devedor,
                    "Título": tit.numero_titulo,
                    "Parcela": tit.parcela,
                    "Vencimento": tit.vencimento.isoformat(),
                    "Atraso (dias)": tit.atraso,
                    "Valor": tit.valor_original,
                })
        st.dataframe(pd.DataFrame(linhas), use_container_width=True, height=280)

    st.markdown("---")
    st.markdown("### ⚙️ Parâmetros do acordo")

    cc1, cc2 = st.columns(2)
    with cc1:
        data_acordo_input = st.date_input(
            "Data do acordo",
            value=date.today(),
            format="DD/MM/YYYY",
            key="imp_pdf_data",
        )
        tipo_cobranca = st.selectbox(
            "Tipo de cobrança",
            ["BOLETO", "PIX"],
            key="imp_pdf_tipo",
        )
    with cc2:
        # Detecta periodicidade
        peri_default = "MENSAL"
        intervalo_def = 30
        if len(cronograma) >= 2:
            dias = (cronograma[1].vencimento - cronograma[0].vencimento).days
            if dias <= 8:
                peri_default = "SEMANAL"
            elif dias <= 16:
                peri_default = "QUINZENAL"
            elif 28 <= dias <= 32:
                peri_default = "MENSAL"
            else:
                peri_default = "PERSONALIZADA"
            intervalo_def = max(1, dias)

        peri_opcoes = ["MENSAL", "QUINZENAL", "SEMANAL", "PERSONALIZADA"]
        periodicidade = st.selectbox(
            f"Periodicidade (detectada: {peri_default})",
            peri_opcoes,
            index=peri_opcoes.index(peri_default),
            key="imp_pdf_peri",
        )
        intervalo_pers = st.number_input(
            "Intervalo personalizado (dias)",
            min_value=1, value=intervalo_def,
            key="imp_pdf_intervalo",
            disabled=(periodicidade != "PERSONALIZADA"),
        )

    # Negociador
    negociadores = repo_usuario.listar_negociadores_ativos()
    if not negociadores:
        st.error("❌ Não há usuários ativos pra ser negociador. Cadastre antes.")
        return
    neg_opcoes = {f"{u.nome} ({u.perfil.value})": u.id for u in negociadores}
    if usuario.perfil in (PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA):
        default_key = f"{usuario.nome} ({usuario.perfil.value})"
    else:
        default_key = list(neg_opcoes.keys())[0]
    if default_key not in neg_opcoes:
        default_key = list(neg_opcoes.keys())[0]

    neg_label = st.selectbox(
        "Negociador responsável",
        list(neg_opcoes.keys()),
        index=list(neg_opcoes.keys()).index(default_key),
        key="imp_pdf_neg",
    )
    negociador_id = neg_opcoes[neg_label]

    observacoes = st.text_area(
        "Observações (opcional)",
        placeholder="Ex: importado do termo de acordo PDF em XX/XX/XXXX",
        key="imp_pdf_obs",
        value=(
            f"Importado de PDF(s) do Termo de Acordo LLE.\n"
            f"Total principal: {_fmt_real(grupo.total_principal)}\n"
            f"Total acordo: {_fmt_real(grupo.total_parcelas_acordo)}\n"
            f"Juros embutidos: {_fmt_real(grupo.juros_total_embutido)} "
            f"(≈ {_fmt_real(grupo.juros_por_parcela)} por parcela)"
        ),
    )

    st.markdown("---")
    # Lock anti-duplo-clique: se já está processando, mostra mensagem
    processando = st.session_state.get(f"imp_processando_pdf_{hash_combinado}", False)
    if processando:
        st.info("⏳ Importando... aguarde, não clique novamente.")
        return

    if st.button(
        "🚀 Importar como novo acordo",
        type="primary",
        use_container_width=True,
        disabled=processando,
        key=f"btn_imp_pdf_{hash_combinado[:8]}",
    ):
        # Marca como processando ANTES de qualquer coisa
        st.session_state[f"imp_processando_pdf_{hash_combinado}"] = True
        with st.spinner("⏳ Importando acordo... não recarregue a página."):
            try:
                _executar_importacao_pdf(
                    grupo=grupo,
                    usuario=usuario,
                    negociador_id=negociador_id,
                    data_acordo=data_acordo_input,
                    tipo_cobranca=tipo_cobranca,
                    periodicidade=periodicidade,
                    intervalo_dias=int(intervalo_pers),
                    observacoes=observacoes,
                    hash_combinado=hash_combinado,
                )
            except Exception as _e_acao:
                st.error(f"❌ Erro: {type(_e_acao).__name__}: {_e_acao}")
                with st.expander("🔍 Detalhes técnicos", expanded=False):
                    st.exception(_e_acao)


def _executar_importacao_pdf(
    grupo: GrupoAcordo, usuario, negociador_id: int,
    data_acordo: date, tipo_cobranca: str, periodicidade: str,
    intervalo_dias: int, observacoes: str, hash_combinado: str,
):
    """Cria o acordo no banco a partir do grupo de termos PDF."""
    try:
        # Nome do cliente principal
        nome_base = grupo.nome_devedor_principal or "Cliente importado"
        if len(grupo.termos) > 1:
            nome_principal = f"{nome_base} ({len(grupo.termos)} CNPJs)"
        else:
            nome_principal = nome_base

        # CNPJ: se for 1 só, usa direto. Se múltiplos, deixa em branco (vai pra obs)
        cnpj_principal = (
            grupo.termos[0].cnpj_devedor
            if len(grupo.termos) == 1 else None
        )

        cliente = repo_cliente.buscar_ou_criar(
            nome_principal=nome_principal,
            cnpj=cnpj_principal,
        )

        # Boletos: 1 por título, do PDF
        boletos = []
        for idx, (cnpj_devedor, titulo) in enumerate(grupo.todos_titulos, 1):
            # Razão social do parceiro = nome completo do termo respectivo
            nome_parceiro = next(
                (t.nome_devedor for t in grupo.termos
                 if t.cnpj_devedor == cnpj_devedor),
                nome_base
            )
            boletos.append(Boleto(
                codigo_parceiro="",
                razao_social_parceiro=nome_parceiro,
                empresa=Empresa.UM,
                codigo_vendedor="",
                nome_vendedor="",
                vencimento=titulo.vencimento,
                numero_nota=titulo.numero_titulo,
                # Sequencial garante unicidade mesmo com títulos duplicados no documento
                numero_unico=f"PDF{idx:03d}-{titulo.numero_titulo}-{titulo.parcela}",
                principal=titulo.valor_original,
                dias_atraso=titulo.atraso,
                juros=0.0,
                multa=0.0,
                total=titulo.valor_original,
                origem=OrigemDado.MANUAL,
            ))

        # Parcelas: cronograma somado
        parcelas = [
            Parcela(
                numero=p.numero,
                vencimento_original=p.vencimento,
                vencimento_atual=p.vencimento,
                valor_original=p.valor,
                principal=p.valor,
                juros=0.0,
                multa=0.0,
                saldo_apos=0.0,
                status=StatusParcela.EM_ABERTO,
            )
            for p in grupo.cronograma_somado
        ]

        # Observação detalhada com CNPJs
        cnpjs_str = "\n".join(f"  - CNPJ {c}" for c in grupo.cnpjs if c)
        obs_completa = (
            (observacoes + "\n\n" if observacoes else "")
            + f"⚠️ ACORDO IMPORTADO de PDF(s)\n"
            + (f"Grupo econômico ({len(grupo.termos)} CNPJs):\n{cnpjs_str}\n\n"
               if len(grupo.termos) > 1
               else f"CNPJ: {grupo.termos[0].cnpj_devedor}\n\n")
            + "Verifique CNPJ, contato e telefone em '🏢 Clientes'."
        )

        acordo_id = salvar_acordo_completo(
            cliente_id=cliente.id,
            negociador_id=negociador_id,
            criado_por_id=usuario.id,
            data_acordo=data_acordo,
            pct_juros_mes_titulos=0.0,
            pct_multa_titulos=0.0,
            pct_juros_mora_mes=0.01,
            pct_multa_mora=0.02,
            tipo_cobranca=TipoCobranca(tipo_cobranca),
            periodicidade=Periodicidade(periodicidade),
            intervalo_personalizado_dias=intervalo_dias,
            boletos=boletos,
            parcelas=parcelas,
            status_inicial=StatusAcordo.ATIVO,
            observacoes=obs_completa,
        )

        n_titulos = sum(len(t.titulos) for t in grupo.termos)
        n_parc = len(parcelas)
        st.session_state["import_msg"] = {
            "tipo": "sucesso",
            "texto": (
                f"✅ **Acordo importado com sucesso!**\n\n"
                f"- Cliente: {nome_principal}\n"
                f"- Títulos: {n_titulos} (R$ {grupo.total_principal:,.2f} de principal)\n"
                f"- Parcelas: {n_parc} (R$ {grupo.total_parcelas_acordo:,.2f} de acordo)\n"
                f"- Juros embutidos: R$ {grupo.juros_total_embutido:,.2f}"
            ),
            "acordo_id": acordo_id,
        }
        st.session_state["imp_hash_processado"] = hash_combinado
        st.session_state["imp_uploader_key"] = f"imp_uploader_{int(time())}"
        # Libera o lock
        st.session_state.pop(f"imp_processando_pdf_{hash_combinado}", None)
        st.toast("✅ Acordo importado!", icon="✅")
        st.rerun()
    except Exception as e:
        st.session_state["import_msg"] = {
            "tipo": "erro",
            "texto": f"❌ Erro ao importar: {e}",
            "acordo_id": None,
        }
        # Libera o lock no erro também
        st.session_state.pop(f"imp_processando_pdf_{hash_combinado}", None)
        st.exception(e)
        st.rerun()


# ============================================================
# FLUXO XLSX (compatibilidade com formato antigo)
# ============================================================

def _fluxo_xlsx(arquivo, usuario, hash_combinado):
    arq_bytes = arquivo.getvalue()

    try:
        acordo_imp = ler_acordo_xlsx(arq_bytes)
    except Exception as e:
        st.error(f"❌ Erro ao ler arquivo: {e}")
        st.exception(e)
        return

    if not acordo_imp.boletos:
        st.error("❌ Nenhum boleto encontrado no arquivo.")
        return
    if not acordo_imp.parcelas:
        st.error("❌ Nenhuma parcela (cronograma) encontrada no arquivo.")
        return

    st.markdown("### 📊 Resumo do que será importado")
    col1, col2, col3 = st.columns(3)
    col1.metric("Clientes do grupo", len(acordo_imp.nomes_clientes))
    col2.metric("Boletos (títulos)", len(acordo_imp.boletos))
    col3.metric("Parcelas", len(acordo_imp.parcelas))

    col4, col5 = st.columns(2)
    col4.metric("Valor dos boletos", _fmt_real(acordo_imp.valor_total_boletos))
    col5.metric("Valor das parcelas", _fmt_real(acordo_imp.valor_total_parcelas))

    # Calcular juros igual ao PDF
    diff = round(acordo_imp.valor_total_parcelas - acordo_imp.valor_total_boletos, 2)
    if diff > 0.01:
        juros_por_parc = round(diff / len(acordo_imp.parcelas), 2)
        st.warning(
            f"💡 **Juros embutidos:** {_fmt_real(diff)} no total — "
            f"em média **{_fmt_real(juros_por_parc)} por parcela** "
            f"(de {len(acordo_imp.parcelas)} parcelas)."
        )

    if acordo_imp.aviso_diferenca:
        st.info(acordo_imp.aviso_diferenca)

    with st.expander(f"👥 Clientes ({len(acordo_imp.nomes_clientes)})", expanded=True):
        for n in acordo_imp.nomes_clientes:
            st.write(f"- {n}")
        st.caption("⚠️ Após importar, complete CNPJ/contato em '🏢 Clientes'.")

    with st.expander(f"📋 Boletos ({len(acordo_imp.boletos)})"):
        df = pd.DataFrame([
            {
                "Cliente": b.nome_parceiro[:30],
                "Nro Único": b.nro_unico,
                "Nro Nota": b.nro_nota or "",
                "Vencimento": b.vencimento.isoformat(),
                "Valor": b.valor_principal,
            }
            for b in acordo_imp.boletos
        ])
        st.dataframe(df, use_container_width=True, height=280)

    with st.expander(f"🗓️ Cronograma ({len(acordo_imp.parcelas)})"):
        df = pd.DataFrame([
            {"Parcela": p.numero, "Data": p.data.isoformat(),
             "Valor": p.valor, "Status": p.status}
            for p in acordo_imp.parcelas
        ])
        st.dataframe(df, use_container_width=True, height=280)

    st.markdown("---")
    st.markdown("### ⚙️ Parâmetros")

    col_a, col_b = st.columns(2)
    with col_a:
        data_acordo_input = st.date_input(
            "Data do acordo", value=date.today(), key="imp_xlsx_data",
        )
        tipo_cobranca = st.selectbox("Tipo cobrança", ["BOLETO", "PIX"], key="imp_xlsx_tipo")
    with col_b:
        peri_default = "MENSAL"
        intervalo_def = 30
        if len(acordo_imp.parcelas) >= 2:
            dias = (acordo_imp.parcelas[1].data - acordo_imp.parcelas[0].data).days
            if dias <= 8: peri_default = "SEMANAL"
            elif dias <= 16: peri_default = "QUINZENAL"
            elif 28 <= dias <= 32: peri_default = "MENSAL"
            else: peri_default = "PERSONALIZADA"
            intervalo_def = max(1, dias)
        peri_opcoes = ["MENSAL", "QUINZENAL", "SEMANAL", "PERSONALIZADA"]
        periodicidade = st.selectbox(
            f"Periodicidade (detectada: {peri_default})",
            peri_opcoes,
            index=peri_opcoes.index(peri_default),
            key="imp_xlsx_peri",
        )
        intervalo_pers = st.number_input(
            "Intervalo (dias)",
            min_value=1, value=intervalo_def,
            disabled=(periodicidade != "PERSONALIZADA"),
            key="imp_xlsx_intervalo",
        )

    negociadores = repo_usuario.listar_negociadores_ativos()
    if not negociadores:
        st.error("❌ Não há usuários ativos pra negociador.")
        return
    neg_opcoes = {f"{u.nome} ({u.perfil.value})": u.id for u in negociadores}
    default_key = f"{usuario.nome} ({usuario.perfil.value})" if usuario.perfil in (
        PerfilUsuario.ADMIN, PerfilUsuario.COBRANCA
    ) else list(neg_opcoes.keys())[0]
    if default_key not in neg_opcoes:
        default_key = list(neg_opcoes.keys())[0]
    neg_label = st.selectbox(
        "Negociador",
        list(neg_opcoes.keys()),
        index=list(neg_opcoes.keys()).index(default_key),
        key="imp_xlsx_neg",
    )
    negociador_id = neg_opcoes[neg_label]

    observacoes = st.text_area(
        "Observações", key="imp_xlsx_obs",
        placeholder="Ex: importado de XLSX em DD/MM/AAAA"
    )

    st.markdown("---")
    # Lock anti-duplo-clique
    processando = st.session_state.get(f"imp_processando_xlsx_{hash_combinado}", False)
    if processando:
        st.info("⏳ Importando... aguarde, não clique novamente.")
        return

    if st.button(
        "🚀 Importar como novo acordo",
        type="primary",
        use_container_width=True,
        disabled=processando,
        key=f"btn_imp_xlsx_{hash_combinado[:8]}",
    ):
        st.session_state[f"imp_processando_xlsx_{hash_combinado}"] = True
        with st.spinner("⏳ Importando acordo... não recarregue a página."):
            try:
                _executar_importacao_xlsx(
                    acordo_imp, usuario, negociador_id, data_acordo_input,
                    tipo_cobranca, periodicidade, int(intervalo_pers),
                    observacoes, hash_combinado,
                )
            except Exception as _e_acao:
                st.error(f"❌ Erro: {type(_e_acao).__name__}: {_e_acao}")
                with st.expander("🔍 Detalhes técnicos", expanded=False):
                    st.exception(_e_acao)


def _executar_importacao_xlsx(
    acordo_imp, usuario, negociador_id: int, data_acordo: date,
    tipo_cobranca: str, periodicidade: str, intervalo_dias: int,
    observacoes: str, hash_combinado: str,
):
    """Importação a partir de XLSX (formato legado)."""
    try:
        nome = acordo_imp.nomes_clientes[0] if acordo_imp.nomes_clientes else "Cliente importado"
        if len(acordo_imp.nomes_clientes) > 1:
            nome = " + ".join(acordo_imp.nomes_clientes[:2])
            if len(acordo_imp.nomes_clientes) > 2:
                nome += f" + {len(acordo_imp.nomes_clientes) - 2} outro(s)"

        cliente = repo_cliente.buscar_ou_criar(nome_principal=nome, cnpj=None)

        boletos = [
            Boleto(
                codigo_parceiro="", razao_social_parceiro=b.nome_parceiro,
                empresa=Empresa.UM, codigo_vendedor="", nome_vendedor="",
                vencimento=b.vencimento, numero_nota=b.nro_nota or "",
                numero_unico=b.nro_unico, principal=b.valor_principal,
                dias_atraso=0, juros=0.0, multa=0.0, total=b.valor_principal,
                origem=OrigemDado.MANUAL,
            )
            for b in acordo_imp.boletos
        ]

        parcelas = [
            Parcela(
                numero=p.numero,
                vencimento_original=p.data, vencimento_atual=p.data,
                valor_original=p.valor, principal=p.valor,
                juros=0.0, multa=0.0, saldo_apos=0.0,
                status=StatusParcela.QUITADA if p.status == "PAGA" else StatusParcela.EM_ABERTO,
            )
            for p in acordo_imp.parcelas
        ]

        acordo_id = salvar_acordo_completo(
            cliente_id=cliente.id, negociador_id=negociador_id,
            criado_por_id=usuario.id, data_acordo=data_acordo,
            pct_juros_mes_titulos=0.0, pct_multa_titulos=0.0,
            pct_juros_mora_mes=0.01, pct_multa_mora=0.02,
            tipo_cobranca=TipoCobranca(tipo_cobranca),
            periodicidade=Periodicidade(periodicidade),
            intervalo_personalizado_dias=intervalo_dias,
            boletos=boletos, parcelas=parcelas,
            status_inicial=StatusAcordo.ATIVO,
            observacoes=(
                (observacoes + "\n\n" if observacoes else "")
                + f"Importado de XLSX. Clientes do grupo:\n"
                + "\n".join(f"  - {n}" for n in acordo_imp.nomes_clientes)
            ),
        )

        st.session_state["import_msg"] = {
            "tipo": "sucesso",
            "texto": (
                f"✅ **Acordo importado!**\n\n"
                f"- Cliente: {nome}\n"
                f"- Boletos: {len(boletos)}\n"
                f"- Parcelas: {len(parcelas)}"
            ),
            "acordo_id": acordo_id,
        }
        st.session_state["imp_hash_processado"] = hash_combinado
        st.session_state["imp_uploader_key"] = f"imp_uploader_{int(time())}"
        # Libera o lock
        st.session_state.pop(f"imp_processando_xlsx_{hash_combinado}", None)
        st.toast("✅ Acordo importado!", icon="✅")
        st.rerun()
    except Exception as e:
        st.session_state["import_msg"] = {
            "tipo": "erro",
            "texto": f"❌ Erro: {e}",
            "acordo_id": None,
        }
        # Libera o lock no erro
        st.session_state.pop(f"imp_processando_xlsx_{hash_combinado}", None)
        st.exception(e)
        st.rerun()
