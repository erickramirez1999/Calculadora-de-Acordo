# LLE Acordos — Sistema de Gestão de Acordos de Cobrança

Sistema web para gestão de acordos de cobrança da **LLE Ferragens (Grupo LLE)**.
Permite o cadastro, acompanhamento e exportação de acordos de parcelamento de
dívidas vencidas, com algoritmo FIFO de rateio idêntico ao da planilha-modelo.

![Identidade Grupo LLE](assets/logo_lle.png)

---

## ✨ O que o sistema faz

- **Cadastro de acordos** via wizard de 7 passos com upload de planilha .xlsx
- **Algoritmo FIFO** de rateio de boletos em parcelas (39 testes unitários cobrindo a lógica)
- **Cálculo de juros e multa** em 2 casos: CASO 1 (títulos) e CASO 2 (mora de parcela atrasada)
- **Pagamento parcial** de parcelas (status `EM_ABERTO`, `PARCIAL`, `QUITADA`)
- **Identidade visual oficial** do Grupo LLE (Manual da Marca fev/2026)
- **3 perfis de acesso**: ADMIN, COBRANÇA e DIRETORIA
- **Auto-bootstrap**: primeiro usuário cadastrado vira ADMIN automaticamente
- **Fluxo de aprovação** para parcelamentos fora do limite (mensal sempre, quinzenal >20, semanal >40)
- **Exportação** em PDF (formal, pro cliente) e XLSX (mesmo padrão da planilha-modelo)
- **Dashboard** com performance por negociador e parcelas em atraso
- **Auditoria** completa de todas as alterações
- **Lembretes automáticos** via GitHub Actions (D-5, D-2, D0, D+1)
- **Múltiplos parceiros, empresas e vendedores** num mesmo acordo (grupo econômico)

---

## 📦 Estrutura do projeto

```
lle_acordos/
├── app.py                          # Página principal (login)
├── requirements.txt
├── README.md
├── pages/                          # Multi-page nativo do Streamlit
│   ├── 1_🏠_Início.py
│   ├── 2_➕_Novo_Acordo.py
│   ├── 3_🧮_Calculadora.py
│   ├── 4_📁_Finalizados.py
│   ├── 5_👥_Negociadores.py
│   ├── 6_📊_Dashboard.py
│   ├── 7_✅_Aprovações.py
│   ├── 8_⚙_Parâmetros.py
│   └── 9_📜_Auditoria.py
├── src/
│   ├── modelos/tipos.py            # Enums e dataclasses
│   ├── utils/                      # Formatadores, identidade visual, CSS
│   ├── servicos/                   # FIFO, juros, cronograma, exportadores
│   ├── banco/                      # SQLite + repositórios (gancho Supabase)
│   └── telas/                      # Lógica de cada tela
├── tests/
│   └── test_fifo.py                # 39 testes unitários (coração do sistema)
├── assets/                         # Logos LLE
├── scripts/
│   └── enviar_lembretes.py         # Cron diário via GitHub Actions
├── .github/workflows/
│   ├── tests.yml                   # Roda testes a cada push
│   └── lembretes.yml               # Cron diário de e-mails
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

---

## 🚀 Como subir no GitHub e fazer o deploy no Streamlit Cloud

### Passo 1 — Substituir o conteúdo do GitHub

Você tem o repositório em https://github.com/erickramirez1999/Calculadora-de-Acordo

1. Faça **backup** do conteúdo atual (download como zip pelo botão "Code → Download ZIP")
2. **Apague** todos os arquivos do repositório (pelo navegador mesmo, ou pelo terminal)
3. **Descompacte** o `lle_acordos.zip` que vou te entregar
4. **Arraste** todo o conteúdo (arquivos e pastas) para o repositório

Pronto. O Streamlit Cloud vai detectar a mudança e fazer o deploy automaticamente.

### Passo 2 — Aguardar deploy (~3 minutos)

O Streamlit Cloud vai:
1. Detectar o novo `requirements.txt`
2. Instalar as dependências (streamlit, pandas, openpyxl, xlrd, reportlab, bcrypt, plotly)
3. Reiniciar o app

Você acompanha em https://share.streamlit.io/ no seu painel.

### Passo 3 — Primeiro acesso (cadastro do ADMIN)

1. Acesse a URL do seu app (https://calculadoradeacordo.streamlit.app)
2. Vá na aba **"📝 Cadastrar"** e preencha nome, e-mail e senha
3. Após criar a conta, o sistema vai mostrar uma **chave de liberação** (ex: `K7P4-N2X9-B5M1`)
4. Como ainda **não tem ninguém pra te liberar** (você é o primeiro), vá no Streamlit Cloud em **Manage app → Settings → Secrets** e cole:

```toml
[usuarios_aprovados]
chaves = ["K7P4-N2X9-B5M1"]
```

5. Salve. Aguarde uns 10 segundos pro app reiniciar.
6. Volte na tela de login do app, vai na aba **"🔑 Entrar"**, faça login com o e-mail e senha que você cadastrou.
7. Pronto. Como você foi o primeiro a se cadastrar, virou **ADMIN** automaticamente.

### Passo 4 — Liberar acesso de outros usuários

Quando alguém da equipe quiser usar o sistema:

1. **Eles** acessam a URL, vão na aba "📝 Cadastrar" e criam a conta
2. **Eles** copiam a chave de liberação que aparece após o cadastro
3. **Eles** te mandam essa chave (WhatsApp, e-mail, etc.) — **a senha fica só com eles**
4. **Você** vai em **Manage app → Settings → Secrets** e adiciona a chave à lista:

```toml
[usuarios_aprovados]
chaves = [
    "K7P4-N2X9-B5M1",   # você (admin)
    "ABCD-EFGH-IJKL",   # novo usuário liberado
]
```

5. Salva. Em ~10 segundos o usuário já consegue entrar.

> **Dica**: você também vê todas as chaves de usuários pendentes na tela **👥 Negociadores** (acessível só por ADMIN), bastando clicar no ícone de chave 🔑 ao lado do nome de cada um.

### Passo 5 — Criar primeiro acordo

1. Vá em **➕ Novo Acordo** no menu lateral
2. Siga os 7 passos do wizard
3. No passo 2, faça upload do .xlsx dos títulos (formato do briefing)
4. No passo 7, clique em "✅ Salvar Acordo"

---

## ⚠ Aviso importante sobre dados — Supabase

O sistema usa **SQLite local** por padrão. O arquivo do banco fica em `.streamlit/data/lle.db`.

**O Streamlit Cloud pode reiniciar o container** ocasionalmente (por exemplo, quando você atualiza o código). Quando isso acontece, o arquivo de banco pode ser **perdido**.

**Solução**: Quando o sistema estiver em produção de verdade, ative o **Supabase**:

1. Crie uma conta gratuita em https://supabase.com (use sua conta Google ou GitHub)
2. Crie um projeto (escolha um nome, ex: "lle-acordos")
3. Aguarde ~2 minutos pro projeto ser provisionado
4. Vá em **Settings → API** e copie:
   - **URL do projeto** (ex: `https://xxxxx.supabase.co`)
   - **anon key** (uma string longa começando com `eyJ...`)
5. No Streamlit Cloud, vá em **Manage app → Settings → Secrets** e cole:

```toml
[supabase]
url = "https://xxxxx.supabase.co"
key = "eyJ..."
```

6. Salve. O sistema detecta automaticamente e passa a usar o Supabase.
7. **Pronto**, nunca mais perde dado.

> **Nota técnica**: o adapter Supabase está com gancho pronto em `src/banco/conexao.py`,
> mas a migração de SQL automática ainda é a próxima etapa de desenvolvimento.
> Por enquanto, com Supabase configurado o sistema vai continuar usando SQLite local até
> a próxima atualização.

---

## 📨 Lembretes automáticos por e-mail (opcional)

Se quiser ativar os lembretes D-5, D-2, D0, D+1:

### 1. Configurar SMTP do Gmail

1. Use uma conta Gmail (ex: `cobranca@grupolle.com.br`, mas pode ser qualquer)
2. Ative **autenticação de 2 fatores** na conta
3. Acesse https://myaccount.google.com/apppasswords
4. Crie uma **"Senha de aplicativo"** (qualquer nome, ex: "LLE Acordos")
5. Copie a senha gerada (16 caracteres)

### 2. Adicionar Secrets no GitHub

No seu repositório no GitHub, vá em **Settings → Secrets and variables → Actions** e adicione:

| Secret | Valor |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | seu e-mail Gmail |
| `SMTP_PASSWORD` | a senha de app (16 chars) |
| `SMTP_FROM` | mesmo e-mail Gmail |

### 3. Pronto

O workflow `lembretes.yml` vai rodar todo dia às 09:00 (Brasília) automaticamente, sem custo.

Você pode também rodar manualmente: vá em **Actions → Lembretes Diários → Run workflow**.

---

## 🧪 Rodar os testes

Os testes cobrem o algoritmo FIFO (coração do sistema):

```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

São **39 testes** que validam:

- Cálculo de juros do CASO 1 (vencido e a vencer)
- Aplicação da multa (vencido = aplica; a vencer = só se pagar depois)
- FIFO básico, transbordo, ordem por vencimento
- Rateio proporcional P/J/M nas parcelas
- Invariantes (P+J+M = Total em boletos e parcelas)
- Refinamento iterativo (resolução da dependência circular)
- Geração de cronograma (4 periodicidades + pula fim de semana)
- Cálculo de mora pós-pagamento parcial (decisão P4.1)
- **Reprodução completa da planilha-modelo MB Comércio** (39 boletos reais)

O GitHub Actions roda esses testes a cada push automaticamente.

---

## 🛠 Como rodar localmente (opcional)

```bash
git clone https://github.com/erickramirez1999/Calculadora-de-Acordo.git
cd Calculadora-de-Acordo
pip install -r requirements.txt
streamlit run app.py
```

---

## 📋 Decisões de regras de negócio

Todas as decisões importantes (P1 a P10) foram tomadas com você antes do desenvolvimento.
Documentadas em `docs/REGRAS_CALCULO.md`.

Principais:
- **P1**: Acordo finalizado reaberto volta exatamente como estava no encerramento
- **P2**: Juros do CASO 1 calculados até a data exata da parcela que quita cada título (refinamento iterativo)
- **P3**: Mora incide sobre o **valor total** da parcela
- **P4**: Pagamento parcial permitido
- **P4.1**: Após pagamento parcial, mora corre sobre o saldo restante
- **P5**: Quinzenal ≤20, semanal ≤40 sem aprovação; mensal e personalizada sempre aprovação
- **P6**: 11 placeholders disponíveis nos templates de e-mail
- **P7**: Número de acordo no formato `ACO-AAAAMMDD-###`
- **P8**: Primeiro usuário cadastrado vira ADMIN automaticamente
- **P9**: Auditoria visível para ADMIN + DIRETORIA
- **P10**: Sankhya com ganchos genéricos (sem doc concreta ainda)

---

## 📞 Suporte

- **Time de marketing** (uso da marca): marketing@grupolle.com.br
- **Streamlit Cloud** (problemas de deploy): https://discuss.streamlit.io
- **Bugs do sistema**: abrir issue no GitHub do projeto

---

**Desenvolvido para LLE Ferragens — Grupo LLE — 2026**
