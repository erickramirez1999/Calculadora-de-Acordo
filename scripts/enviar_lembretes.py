"""
Script de envio diário de lembretes (briefing Seção 10).

Roda via GitHub Actions cron. Verifica todas as parcelas em ABERTO/PARCIAL
e dispara e-mail para os gatilhos configurados (D-5, D-2, D0, D+1).

CONFIGURAÇÃO NECESSÁRIA (no GitHub Secrets do repositório):
    SMTP_HOST     ex: smtp.gmail.com
    SMTP_PORT     ex: 587
    SMTP_USER     ex: cobranca@grupolle.com.br
    SMTP_PASSWORD senha de app (não a senha normal do e-mail)
    SMTP_FROM     ex: cobranca@grupolle.com.br

Para Gmail: precisa criar "senha de app" em myaccount.google.com/apppasswords
(com autenticação de 2 fatores ativada).

# DECIDIDO POR CLAUDE — REVISAR COM ERICK:
# - Usando Gmail SMTP como default. Se preferir Resend ou outro serviço,
#   ajustar a função enviar_email().
# - Templates carregam dos parâmetros do banco; se não houver, usa fallback.
"""
from __future__ import annotations

import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

# Adiciona src/ ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.banco.conexao import obter_conexao
from src.banco.schema import inicializar_banco
from src.banco import repos_auxiliares
from src.utils.formatadores import formatar_brl, formatar_data


def carregar_smtp_config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from": os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")),
    }


def enviar_email(para: str, assunto: str, corpo: str, smtp: dict) -> bool:
    if not smtp["host"] or not smtp["user"]:
        print(f"[SKIP] SMTP não configurado. Não enviando para {para}.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp["from"]
        msg["To"] = para
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "plain", "utf-8"))
        with smtplib.SMTP(smtp["host"], smtp["port"]) as server:
            server.starttls()
            server.login(smtp["user"], smtp["password"])
            server.sendmail(smtp["from"], [para], msg.as_string())
        print(f"[OK] Enviado para {para}: {assunto}")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao enviar para {para}: {e}")
        return False


def aplicar_template(template: str, contexto: dict) -> str:
    saida = template
    for k, v in contexto.items():
        saida = saida.replace("{{" + k + "}}", str(v))
    return saida


def listar_parcelas_para_gatilho(gatilho: str) -> list:
    """Retorna parcelas elegíveis pra cada gatilho."""
    hoje = date.today()
    offset_dias = {"D-5": -5, "D-2": -2, "D0": 0, "D+1": 1}
    if gatilho not in offset_dias:
        return []
    alvo = hoje + timedelta(days=-offset_dias[gatilho])

    cur = obter_conexao().execute(
        """
        SELECT p.id, p.numero, p.vencimento_atual, p.valor_original, p.status,
               a.numero_interno, a.tipo_cobranca,
               a.pct_juros_mora_mes, a.pct_multa_mora,
               c.nome_principal AS cliente_nome, c.email_cobranca,
               u.nome AS negociador_nome
        FROM parcela p
        JOIN acordo a ON a.id = p.acordo_id
        JOIN cliente c ON c.id = a.cliente_id
        JOIN usuario u ON u.id = a.negociador_id
        WHERE p.status != 'QUITADA'
          AND DATE(p.vencimento_atual) = DATE(?)
          AND a.status = 'ATIVO';
        """,
        (alvo.isoformat(),),
    )
    return [dict(r) for r in cur.fetchall()]


def disparar_lembretes():
    inicializar_banco()
    smtp = carregar_smtp_config()

    import json
    gatilhos_raw = repos_auxiliares.get_parametro("lembrete.gatilhos") or '["D-5","D-2","D0","D+1"]'
    gatilhos = json.loads(gatilhos_raw)
    template_assunto = repos_auxiliares.get_parametro("lembrete.template_assunto") or ""
    template_corpo = repos_auxiliares.get_parametro("lembrete.template_corpo") or ""
    instrucoes = repos_auxiliares.get_parametro("lembrete.instrucoes_pagamento") or ""

    total_enviados = 0
    hoje = date.today()

    for g in gatilhos:
        parcelas = listar_parcelas_para_gatilho(g)
        print(f"\n=== Gatilho {g}: {len(parcelas)} parcela(s) elegíveis ===")
        for p in parcelas:
            if not p["email_cobranca"]:
                print(f"[PULA] {p['numero_interno']} parcela {p['numero']} sem e-mail de cobrança")
                continue

            venc = datetime.fromisoformat(p["vencimento_atual"]).date()
            dias_para_venc = (venc - hoje).days
            dias_atraso = max(0, (hoje - venc).days)

            # Calcula valor atualizado se atrasado
            if dias_atraso > 0:
                mora_j = p["valor_original"] * (p["pct_juros_mora_mes"] / 100) / 30 * dias_atraso
                mora_m = p["valor_original"] * (p["pct_multa_mora"] / 100)
                val_atu = p["valor_original"] + mora_j + mora_m
            else:
                val_atu = p["valor_original"]

            ctx = {
                "cliente": p["cliente_nome"],
                "negociador": p["negociador_nome"],
                "numero_parcela": str(p["numero"]),
                "valor": formatar_brl(p["valor_original"]),
                "valor_atualizado": formatar_brl(val_atu),
                "data_vencimento": formatar_data(venc),
                "dias_para_vencimento": str(dias_para_venc),
                "tipo_cobranca": p["tipo_cobranca"],
                "instrucoes_pagamento": instrucoes,
                "dias_atraso": str(dias_atraso),
                "numero_acordo": p["numero_interno"],
            }

            assunto = aplicar_template(template_assunto, ctx)
            corpo = aplicar_template(template_corpo, ctx)

            if enviar_email(p["email_cobranca"], assunto, corpo, smtp):
                total_enviados += 1
                repos_auxiliares.registrar_log(
                    usuario_id=None, usuario_nome="sistema (cron)",
                    acao=f"LEMBRETE_{g}",
                    entidade="parcela", entidade_id=p["id"],
                    contexto=f"{p['numero_interno']} · Parcela {p['numero']}",
                    depois={"para": p["email_cobranca"]},
                )

    print(f"\n✅ Total enviados: {total_enviados}")


if __name__ == "__main__":
    disparar_lembretes()
