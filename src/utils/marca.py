"""
Identidade visual do Grupo LLE.
Cores e fonte oficiais conforme Manual da Marca (fev/2026).
NUNCA use cores que não estejam aqui.
"""
from __future__ import annotations

# ============================================================
# CORES OFICIAIS GRUPO LLE (Manual da Marca, página 6)
# ============================================================

# Cor primária - azul-marinho institucional
AZUL_ESCURO = "#041747"

# Cor de destaque - amarelo/dourado
AMARELO = "#FAC318"

# Cor de sucesso / valores positivos
VERDE = "#0F8C3B"

# Cor de links / botões secundários
AZUL_VIVO = "#0071FE"

# Neutros
BRANCO = "#FFFFFF"
PRETO = "#000000"

# ============================================================
# CORES DERIVADAS (para estados específicos descritos no briefing)
# ============================================================

# Atraso de parcela (Seção 4 do briefing)
FUNDO_ATRASO = "#F8D7DA"
TEXTO_ATRASO = "#721C24"

# Parcela paga (Seção 4 do briefing)
FUNDO_PAGO = "#D4EDDA"
TEXTO_PAGO = "#155724"

# Pagamento parcial (P4 - definimos amarelo claro)
FUNDO_PARCIAL = "#FFF3CD"
TEXTO_PARCIAL = "#856404"

# Linhas alternadas em tabelas
LINHA_ALTERNADA = "#F2F2F2"

# Bordas finas
BORDA_FINA = "#D9D9D9"

# Cinza claro (cards, fundos suaves)
CINZA_CLARO = "#F8F9FA"
CINZA_MEDIO = "#6C757D"

# ============================================================
# TIPOGRAFIA
# ============================================================

FONTE_PRINCIPAL = "Montserrat"
FONTE_FALLBACK = "Calibri, Arial, sans-serif"

# Pesos disponíveis (Manual da Marca, página 7)
PESOS_MONTSERRAT = {
    "thin": 100,
    "light": 300,
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
    "extrabold": 800,
    "black": 900,
}

# ============================================================
# OUTROS PADRÕES
# ============================================================

# Tamanho mínimo do logo em mídia digital (Manual da Marca, página 9)
LOGO_MIN_PX = 132

# Nome da empresa
NOME_EMPRESA = "Grupo LLE"
NOME_OPERACAO = "LLE Ferragens"
CONTATO_MARKETING = "marketing@grupolle.com.br"


def css_variaveis() -> str:
    """Gera bloco CSS com as variáveis da marca pra injetar no Streamlit."""
    return f"""
    :root {{
        --lle-azul-escuro: {AZUL_ESCURO};
        --lle-amarelo: {AMARELO};
        --lle-verde: {VERDE};
        --lle-azul-vivo: {AZUL_VIVO};
        --lle-branco: {BRANCO};
        --lle-fundo-atraso: {FUNDO_ATRASO};
        --lle-texto-atraso: {TEXTO_ATRASO};
        --lle-fundo-pago: {FUNDO_PAGO};
        --lle-texto-pago: {TEXTO_PAGO};
        --lle-fundo-parcial: {FUNDO_PARCIAL};
        --lle-texto-parcial: {TEXTO_PARCIAL};
        --lle-linha-alt: {LINHA_ALTERNADA};
        --lle-borda: {BORDA_FINA};
        --lle-cinza-claro: {CINZA_CLARO};
        --lle-cinza-medio: {CINZA_MEDIO};
        --lle-fonte: '{FONTE_PRINCIPAL}', {FONTE_FALLBACK};
    }}
    """
