"""
Tipos centrais do sistema LLE Acordos.
Define enums para status, perfis, tipos de cobrança, etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional


# ============================================================
# ENUMS
# ============================================================

class StatusAcordo(str, Enum):
    """Estados possíveis de um acordo."""
    RASCUNHO = "RASCUNHO"
    PENDENTE_APROVACAO = "PENDENTE_APROVACAO"
    ATIVO = "ATIVO"
    QUITADO = "QUITADO"
    QUEBRADO = "QUEBRADO"
    CANCELADO = "CANCELADO"


class StatusParcela(str, Enum):
    """
    Estados possíveis de uma parcela.

    Fluxo de pagamento com dupla confirmação:
      EM_ABERTO → AGUARDANDO_CONFIRMACAO → QUITADA
                    (cobrança confirma)     (admin confirma)

      PARCIAL: quando a soma de pagamentos confirmados é menor que o valor total
    """
    EM_ABERTO = "EM_ABERTO"
    AGUARDANDO_CONFIRMACAO = "AGUARDANDO_CONFIRMACAO"
    PARCIAL = "PARCIAL"
    QUITADA = "QUITADA"


class PerfilUsuario(str, Enum):
    """Perfis de acesso. Define o que cada usuário pode fazer."""
    ADMIN = "ADMIN"
    COBRANCA = "COBRANCA"
    DIRETORIA = "DIRETORIA"


class TipoCobranca(str, Enum):
    """Forma de pagamento das parcelas."""
    BOLETO = "BOLETO"
    PIX = "PIX"


class Periodicidade(str, Enum):
    """Espaçamento das parcelas no cronograma."""
    MENSAL = "MENSAL"
    QUINZENAL = "QUINZENAL"
    SEMANAL = "SEMANAL"
    PERSONALIZADA = "PERSONALIZADA"


class Empresa(int, Enum):
    """Empresas emissoras de títulos no Grupo LLE."""
    UM = 1
    DOIS = 2


class OrigemDado(str, Enum):
    """Origem do dado (importado manual ou via integração futura)."""
    MANUAL = "MANUAL"
    SANKHYA = "SANKHYA"


# ============================================================
# DATACLASSES (modelos em memória — refletem o BD)
# ============================================================

@dataclass
class Boleto:
    """
    Representa um título original (boleto) que entrou no acordo.
    Um acordo pode ter títulos de vários parceiros e empresas (grupo econômico).
    """
    # Identificação do título no Sankhya
    codigo_parceiro: str
    razao_social_parceiro: str
    empresa: Empresa
    codigo_vendedor: str
    nome_vendedor: str
    # Dados do título
    vencimento: date
    numero_nota: str
    numero_unico: str
    principal: float
    # Campos calculados pelo motor de juros (CASO 1)
    dias_atraso: int = 0
    fim_juros: date = field(default_factory=date.today)
    juros: float = 0.0
    multa: float = 0.0
    total: float = 0.0
    # Vínculo com parcelas (preenchido pelo FIFO)
    parcelas_alocadas: list[int] = field(default_factory=list)
    distribuicao: list[dict] = field(default_factory=list)
    # Gancho pra integração futura
    titulo_sankhya_id: Optional[str] = None
    origem: OrigemDado = OrigemDado.MANUAL


@dataclass
class PagamentoParcela:
    """Um lançamento de pagamento numa parcela. Permite pagamento parcial."""
    data_pagamento: date
    valor: float
    observacao: str = ""


@dataclass
class Parcela:
    """
    Uma parcela do cronograma do acordo.
    Aceita pagamento parcial: status pode ser EM_ABERTO, PARCIAL ou QUITADA.
    """
    numero: int
    vencimento_original: date
    vencimento_atual: date  # pode ser remarcada sem afetar as outras
    valor_original: float
    # Decomposição P/J/M rateada via FIFO
    principal: float = 0.0
    juros: float = 0.0
    multa: float = 0.0
    # Saldo da parcela após pagamentos
    saldo_apos: float = 0.0
    # Pagamentos (pode haver vários se for parcial)
    pagamentos: list[PagamentoParcela] = field(default_factory=list)
    status: StatusParcela = StatusParcela.EM_ABERTO

    @property
    def valor_pago(self) -> float:
        """Total já pago nesta parcela."""
        return sum(p.valor for p in self.pagamentos)

    @property
    def valor_restante(self) -> float:
        """Quanto ainda falta pagar (sem mora). Pode ser 0 se já quitada."""
        return max(0.0, round(self.valor_original - self.valor_pago, 2))


@dataclass
class ConfiguracaoAcordo:
    """
    Conjunto de parâmetros financeiros de um acordo.
    Os 4 percentuais são INDEPENDENTES (briefing Seção 13 e 18a).
    """
    pct_juros_mes_titulos: float       # CASO 1 - juros mensal sobre títulos
    pct_multa_titulos: float           # CASO 1 - multa fixa sobre títulos
    pct_juros_mora_mes: float          # CASO 2 - mora mensal de parcela atrasada
    pct_multa_mora: float              # CASO 2 - multa fixa de parcela atrasada
    tipo_cobranca: TipoCobranca
    data_acordo: date
    periodicidade: Periodicidade
    intervalo_personalizado_dias: int = 1   # só usado se periodicidade = PERSONALIZADA


# Aliases pra retornos de funções de validação
ResultadoValidacao = Literal["OK", "PRECISA_APROVACAO_ADMIN", "INVALIDO"]
