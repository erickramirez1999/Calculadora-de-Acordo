"""
Aplicação do CSS LLE no Streamlit.
Carrega Montserrat do Google Fonts + variáveis de cor + overrides nos componentes.
"""
from __future__ import annotations

import streamlit as st

from src.utils.marca import (
    AZUL_ESCURO, AMARELO, VERDE, AZUL_VIVO, BRANCO,
    FUNDO_ATRASO, TEXTO_ATRASO, FUNDO_PAGO, TEXTO_PAGO,
    FUNDO_PARCIAL, TEXTO_PARCIAL, LINHA_ALTERNADA, BORDA_FINA,
    CINZA_CLARO, CINZA_MEDIO,
)


def aplicar_css_lle():
    """Injeta CSS global. Chamar uma vez por página."""
    st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
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
    }}

    /* Fonte global */
    html, body, [class*="css"], [class*="st-"], button, input, select, textarea {{
        font-family: 'Montserrat', Calibri, Arial, sans-serif !important;
    }}

    /* Títulos */
    h1, h2, h3, h4, h5 {{
        color: var(--lle-azul-escuro) !important;
        font-weight: 700 !important;
    }}

    /* Botões primários */
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    button[data-testid="baseButton-primary"] {{
        background-color: var(--lle-azul-escuro) !important;
        color: var(--lle-branco) !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: var(--lle-azul-vivo) !important;
    }}

    /* Botões secundários */
    .stButton > button[kind="secondary"] {{
        border: 1.5px solid var(--lle-azul-escuro) !important;
        color: var(--lle-azul-escuro) !important;
        font-weight: 600 !important;
        background-color: var(--lle-branco) !important;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: var(--lle-azul-escuro) !important;
    }}
    section[data-testid="stSidebar"] * {{
        color: var(--lle-branco) !important;
    }}
    section[data-testid="stSidebar"] .stButton > button {{
        background-color: rgba(255,255,255,0.08) !important;
        color: var(--lle-branco) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        background-color: var(--lle-amarelo) !important;
        color: var(--lle-azul-escuro) !important;
        border-color: var(--lle-amarelo) !important;
    }}

    /* === FIX GLOBAL: ÍCONES MATERIAL QUEBRADOS NOS BOTÕES NATIVOS ===
       Streamlit usa Material Symbols que às vezes não carregam, mostrando
       o nome do ícone como texto cru (ex: "upload", "download",
       "keyboard_double_arrow_right"). Esse texto fica sobrepondo o
       label real do botão.
       
       A regra abaixo identifica esses ícones (que têm classes específicas)
       e força que o nome do ícone NUNCA apareça como texto - quando a
       fonte Material não carrega, fica simplesmente invisível.
    */
    span[data-testid="stIconMaterial"],
    span.material-icons,
    span.material-symbols-outlined,
    span.material-symbols-rounded,
    span[class*="stIconMaterial"] {{
        font-family: 'Material Symbols Outlined', 'Material Symbols Rounded',
                     'Material Icons' !important;
        font-weight: normal !important;
        font-style: normal !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        display: inline-block !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        -webkit-font-feature-settings: 'liga' !important;
        -webkit-font-smoothing: antialiased !important;
    }}
    /* Se o Material Icon não conseguir renderizar (e mostrar o nome cru
       do ícone), torna o texto invisível em vez de sobrepor. */
    @supports not (font-variation-settings: normal) {{
        span[data-testid="stIconMaterial"],
        span.material-icons,
        span.material-symbols-outlined,
        span.material-symbols-rounded {{
            color: transparent !important;
            font-size: 0 !important;
        }}
    }}
    /* Garante carregamento das Material Symbols (caso a CDN do Streamlit falhe) */
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=block');

    /* === BOTÃO DE TOGGLE DA SIDEBAR ===
       Streamlit usa Material Icons que às vezes não carregam, mostrando
       o nome do ícone como texto ("keyboard_double_arrow_right"). 
       Aqui escondemos esse texto e colocamos uma seta unicode no lugar. */
    button[data-testid="collapsedControl"] {{
        background: var(--lle-azul-escuro) !important;
        border: 1px solid var(--lle-amarelo) !important;
        border-radius: 6px !important;
        color: var(--lle-amarelo) !important;
        padding: 6px 10px !important;
        font-size: 0 !important;
        min-width: 36px !important;
        min-height: 36px !important;
    }}
    button[data-testid="collapsedControl"] * {{
        font-size: 0 !important;
        color: transparent !important;
    }}
    button[data-testid="collapsedControl"]::before {{
        content: "☰" !important;
        font-size: 20px !important;
        color: var(--lle-amarelo) !important;
        display: inline-block !important;
        line-height: 1 !important;
    }}
    button[data-testid="collapsedControl"]:hover {{
        background: var(--lle-amarelo) !important;
    }}
    button[data-testid="collapsedControl"]:hover::before {{
        color: var(--lle-azul-escuro) !important;
    }}
    /* Botão de fechar sidebar (dentro dela) */
    section[data-testid="stSidebar"] button[kind="header"] {{
        font-size: 0 !important;
    }}
    section[data-testid="stSidebar"] button[kind="header"] * {{
        font-size: 0 !important;
        color: transparent !important;
    }}
    section[data-testid="stSidebar"] button[kind="header"]::before {{
        content: "✕" !important;
        font-size: 18px !important;
        color: var(--lle-branco) !important;
    }}

    /* === FILE UPLOADER ===
       O botão "Browse files" do uploader é nativo do Streamlit. Vou
       estilizá-lo pra ficar com cara LLE e sem sobreposições.
    */
    section[data-testid="stFileUploaderDropzone"] {{
        border: 2px dashed var(--lle-azul-escuro) !important;
        border-radius: 8px !important;
        background-color: #F8F9FA !important;
        padding: 16px !important;
    }}
    section[data-testid="stFileUploaderDropzone"]:hover {{
        border-color: var(--lle-azul-vivo) !important;
        background-color: #EFF6FF !important;
    }}
    section[data-testid="stFileUploaderDropzone"] button {{
        background-color: var(--lle-azul-escuro) !important;
        color: var(--lle-branco) !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
    }}
    /* Esconde o ícone Material quebrado dentro do file uploader */
    section[data-testid="stFileUploaderDropzone"] svg + small,
    section[data-testid="stFileUploaderDropzone"] span[data-testid*="Icon"] {{
        display: inline-block !important;
    }}

    /* === BOTÕES DE DOWNLOAD E POPOVER ===
       Esconde texto Material em botões customizados quando o ícone
       falha em carregar.
    */
    .stDownloadButton button [data-testid="stIconMaterial"],
    button[data-testid="baseButton-primary"] [data-testid="stIconMaterial"],
    .stPopover button [data-testid="stIconMaterial"] {{
        min-width: 16px;
        min-height: 16px;
    }}

    /* Cards de métrica */
    div[data-testid="stMetricValue"] {{
        color: var(--lle-azul-escuro) !important;
        font-weight: 700 !important;
    }}
    div[data-testid="stMetricLabel"] {{
        color: var(--lle-cinza-medio) !important;
        font-weight: 500 !important;
    }}

    /* Tabelas */
    .stDataFrame thead th {{
        background-color: var(--lle-azul-escuro) !important;
        color: var(--lle-branco) !important;
        font-weight: 600 !important;
    }}

    /* Inputs */
    .stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox select {{
        border-radius: 6px !important;
        border: 1.5px solid var(--lle-borda) !important;
    }}

    /* Badge customizado */
    .lle-badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
    }}
    .lle-badge-ativo {{ background: {VERDE}33; color: {VERDE}; }}
    .lle-badge-pendente {{ background: {AMARELO}55; color: #856404; }}
    .lle-badge-quitado {{ background: {VERDE}; color: white; }}
    .lle-badge-quebrado {{ background: #DC3545; color: white; }}
    .lle-badge-cancelado {{ background: {CINZA_MEDIO}; color: white; }}
    .lle-badge-rascunho {{ background: {CINZA_CLARO}; color: {CINZA_MEDIO}; border: 1px solid {BORDA_FINA}; }}

    /* Card de acordo */
    .lle-card {{
        background: white;
        border: 1px solid var(--lle-borda);
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
        transition: box-shadow 0.2s;
    }}
    .lle-card:hover {{
        box-shadow: 0 2px 8px rgba(4,23,71,0.1);
        border-color: var(--lle-azul-vivo);
    }}

    /* Barra de progresso */
    .lle-progress-wrapper {{
        background: var(--lle-cinza-claro);
        height: 8px;
        border-radius: 4px;
        overflow: hidden;
        margin-top: 8px;
    }}
    .lle-progress-bar {{
        background: linear-gradient(90deg, {VERDE}, {AZUL_VIVO});
        height: 100%;
        border-radius: 4px;
        transition: width 0.3s;
    }}

    /* Diminui padding superior do app */
    .block-container {{
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px;
    }}

    /* Remove menu hamburger e "Made with Streamlit" */
    header[data-testid="stHeader"] {{
        background: transparent;
    }}
    footer {{ visibility: hidden; }}
</style>
    """, unsafe_allow_html=True)


def badge_status_acordo(status: str) -> str:
    """Retorna HTML de badge colorido para status de acordo."""
    classes = {
        "ATIVO": "lle-badge-ativo",
        "PENDENTE_APROVACAO": "lle-badge-pendente",
        "QUITADO": "lle-badge-quitado",
        "QUEBRADO": "lle-badge-quebrado",
        "CANCELADO": "lle-badge-cancelado",
        "RASCUNHO": "lle-badge-rascunho",
    }
    labels = {
        "ATIVO": "● Ativo",
        "PENDENTE_APROVACAO": "⏳ Pendente Aprovação",
        "QUITADO": "✓ Quitado",
        "QUEBRADO": "✕ Quebrado",
        "CANCELADO": "⊘ Cancelado",
        "RASCUNHO": "📝 Rascunho",
    }
    classe = classes.get(status, "lle-badge-rascunho")
    label = labels.get(status, status)
    return f'<span class="lle-badge {classe}">{label}</span>'


def barra_progresso(pagas: int, total: int) -> str:
    """HTML de barra de progresso visual."""
    pct = (pagas / total * 100) if total > 0 else 0
    return f"""
<div class="lle-progress-wrapper">
    <div class="lle-progress-bar" style="width:{pct}%"></div>
</div>
<div style="font-size: 11px; color: #666; margin-top: 4px;">
    {pagas} de {total} parcelas pagas ({pct:.0f}%)
</div>
    """
