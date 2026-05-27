"""
Formatadores pt-BR para exibição.
Moeda: R$ 1.234,56  |  Data: dd/mm/aaaa  |  Percentual: 8,00%
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Union


def formatar_brl(valor: float, prefixo: str = "R$ ") -> str:
    """
    Formata número como moeda brasileira: R$ 1.234,56
    Valor 0 vira "R$ 0,00" (não vira traço, pois precisamos do alinhamento na tabela).
    """
    if valor is None:
        return f"{prefixo}0,00"
    s = f"{abs(valor):,.2f}"
    # Troca separadores (US -> BR): 1,234.56 -> 1.234,56
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}{prefixo}{s}"


def formatar_data(d: Union[date, datetime, str, None]) -> str:
    """
    Formata data como dd/mm/aaaa.
    Aceita date, datetime, string ISO, ou None.
    Tolera input com prefixo de 10 caracteres ISO (YYYY-MM-DD).
    """
    if d is None:
        return ""
    if isinstance(d, str):
        # Se vier 'YYYY-MM-DD...' (ISO), pega só os 10 primeiros
        try:
            d = datetime.fromisoformat(d[:19]).date()
        except ValueError:
            try:
                d = datetime.fromisoformat(d[:10]).date()
            except ValueError:
                return d
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y")


def formatar_hora(d) -> str:
    """
    Extrai HH:MM de uma data/datetime/string ISO.
    Aceita ambos formatos do SQLite (string) e Postgres (datetime).
    """
    if d is None:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d[:19])
        except ValueError:
            try:
                return d[11:16]
            except Exception:
                return ""
    if isinstance(d, date) and not isinstance(d, datetime):
        return ""
    if isinstance(d, datetime):
        return d.strftime("%H:%M")
    return ""


def formatar_pct(valor: float, casas: int = 2) -> str:
    """Formata percentual: 8,00%"""
    s = f"{valor:.{casas}f}".replace(".", ",")
    return f"{s}%"


def parse_brl(texto: str) -> float:
    """
    Converte string em formato BR para float.
    Aceita: "1.234,56", "R$ 1.234,56", "1234,56", "1234.56"
    """
    if not texto:
        return 0.0
    s = str(texto).strip()
    s = s.replace("R$", "").replace(" ", "")
    # Se tem vírgula, é o separador decimal BR
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def parse_data_br(texto: str) -> date:
    """Converte 'dd/mm/aaaa' para date."""
    if not texto:
        raise ValueError("Data vazia")
    s = str(texto).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {texto!r} (esperado dd/mm/aaaa)")


def remover_acentos(texto: str) -> str:
    """
    Remove acentuação para uso em buscas case-insensitive ignorando acentos.
    'Ferragens' -> 'Ferragens', 'maçã' -> 'maca', 'João' -> 'Joao'
    """
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_busca(texto: str) -> str:
    """Normaliza texto para comparação em busca: lowercase + sem acentos + trim."""
    return remover_acentos(str(texto)).lower().strip()


def slugificar(texto: str) -> str:
    """Slug para nomes de arquivo: 'Empresa Exemplo LTDA' -> 'empresa-exemplo-ltda'."""
    s = remover_acentos(texto).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "acordo"
