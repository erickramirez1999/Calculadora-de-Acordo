# Regras de Cálculo — Sistema LLE Acordos

Este documento explica as regras matemáticas implementadas no sistema, com
exemplos numéricos para que qualquer pessoa do time consiga validar o resultado.

---

## 1. Algoritmo FIFO de rateio (Seção 3 do briefing)

O sistema distribui os boletos nas parcelas seguindo a ordem cronológica
(mais antigo primeiro). Cada parcela "consome" seu valor em boletos.
Quando um boleto não cabe inteiro numa parcela, o resto vai pra próxima.

### Exemplo simples
```
Boletos:
  B1 — venc 01/01 — total R$ 1.500
  B2 — venc 05/01 — total R$ 800

Parcelas de R$ 1.000 cada:
  P1 → consome 1000 do B1
  P2 → consome 500 do B1 + 500 do B2
  P3 → consome 300 do B2
```

---

## 2. CASO 1 — Juros e multa dos títulos

Esses cálculos são feitos **uma vez** na criação do acordo e ficam embutidos
no valor de cada parcela.

### Juros pro-rata diário
```
juros = principal × (%juros_mes / 30) × dias_corridos
```

- **Título vencido** (vencimento < data do acordo): dias contados do
  vencimento original até a data da parcela que quita o título.
- **Título a vencer** (vencimento >= data do acordo): dias contados da
  data do acordo até a data da parcela.

### Multa
- **Vencido**: aplica %multa direto sobre o principal.
- **A vencer**: só aplica se a parcela que quita o título for posterior
  ao vencimento original.

### Exemplo numérico
Título com:
- Principal R$ 971,93
- Vencimento 19/02/2026
- Data do acordo 08/04/2026
- Data da parcela que quita 08/04/2026 (mesma data, 48 dias após o vencimento)
- 8% juros a.m., 2% multa

Cálculo:
```
juros = 971,93 × (8 / 30 / 100) × 48 = 124,41
multa = 971,93 × 2% = 19,44
total = 971,93 + 124,41 + 19,44 = 1.115,77
```

---

## 3. Refinamento iterativo (decisão P2)

Aqui está a parte mais complexa do sistema. Há uma **dependência circular**:

> O juros de cada título depende da data da parcela que o quita.
> A parcela que o quita depende do total do título via FIFO.
> O total do título depende do juros.

A solução é iterar:

1. **Iteração 0**: calcula juros usando uma data aproximada (a data do acordo).
2. Roda FIFO → descobre quais parcelas quitam cada título.
3. **Iteração 1**: pra cada título, recalcula juros usando a data da última
   parcela que o quita (a data REAL).
4. Roda FIFO de novo.
5. Repete até que nenhum total mude (convergência).

Normalmente converge em 2-4 iterações.

O resultado final é equivalente a "juros calculado até a data exata da parcela
que quita cada título" — exatamente o que o briefing pediu.

---

## 4. CASO 2 — Mora de parcela atrasada

Quando uma parcela atrasa (passa do vencimento sem pagamento), o sistema
calcula um acréscimo:

```
juros_mora = valor_devido × (%juros_mora_mes / 30) × dias_atraso
multa_mora = valor_devido × %multa_mora
total_atualizado = valor_devido + juros_mora + multa_mora
```

### Importantes
- **`valor_devido` é o saldo restante da parcela** (decisão P3 + P4.1).
  - Se a parcela não foi paga: saldo = valor original (P3 — mora sobre TOTAL).
  - Se houve pagamento parcial: saldo = valor original - valor pago (P4.1).
- Os **percentuais são independentes** dos do CASO 1.

### Exemplo numérico
Parcela de R$ 2.400 venceu há 3 dias. Mora 5% a.m. + 2% multa:
```
juros_mora = 2.400 × (5 / 30 / 100) × 3 = 12,00
multa_mora = 2.400 × 2% = 48,00
total = 2.400 + 12 + 48 = 2.460,00
```

### Exemplo com pagamento parcial
Mesma parcela acima, mas o cliente pagou R$ 1.500 no dia 3 (vencimento + 3 = 18/05).
Hoje é 25/05 (7 dias depois do pagamento parcial). Saldo restante = R$ 960.
```
juros_mora = 960 × (5 / 30 / 100) × 7 = 11,20
multa_mora = 960 × 2% = 19,20
total a pagar agora = 960 + 11,20 + 19,20 = 990,40
```

---

## 5. Geração do cronograma (Seção 14)

A contagem do intervalo é em **dias corridos**. Se a data final cair em
sábado ou domingo, é **empurrada para a próxima segunda-feira** (nunca para sexta).

Feriados nacionais NÃO são considerados nesta versão.

### Importante: encadeamento
Para evitar empilhamento de várias parcelas na mesma segunda quando o intervalo
é pequeno (ex: personalizada=1 dia), o cálculo da próxima parcela parte
da data anterior **já ajustada**, não da data-base original.

### Exemplo: 41 parcelas diárias começando sexta 08/05/2026
```
P1  = 08/05 (sex)
P2  = 09/05 → sábado → empurra pra 11/05 (seg)
P3  = parte de 11/05 + 1 = 12/05 (ter)
P4  = 13/05 (qua)
...
```

Esse é exatamente o cronograma da planilha-modelo MB Comércio.

---

## 6. Modos de parcelamento

### Modo "Quantidade fixa de parcelas"
Usuário define N. Sistema divide:
```
valor_parcela_padrão = ARREDONDAR(total / N, 2)
```
A última parcela absorve a diferença para fechar exatamente o total.

### Modo "Valor fixo por parcela"
Usuário define o valor de cada parcela. Sistema calcula:
```
N = ceil(total / valor_parcela)
```
A última parcela pode ser menor (sobra).

**Exemplo da planilha-modelo**: total R$ 97.948 ÷ R$ 2.400 = 40 parcelas cheias + 1
parcela final de R$ 1.948.

---

## 7. Regras de aprovação (decisão P5)

| Periodicidade | Limite sem aprovação | Acima disso |
|---|---|---|
| **Quinzenal** | até 20 parcelas | aprovação ADMIN |
| **Semanal** | até 40 parcelas | aprovação ADMIN |
| **Mensal** | sempre exige aprovação | aprovação ADMIN |
| **Personalizada** | sem limite, mas total >= valor da Calculadora | — |

Acima do limite o acordo entra em status `PENDENTE_APROVACAO`. Um ADMIN
revisa na tela "Aprovações" e aprova/recusa com justificativa.

---

## 8. Status do acordo (decisão P1)

| Status | O que significa |
|---|---|
| `RASCUNHO` | Wizard salvo mas não confirmado |
| `PENDENTE_APROVACAO` | Aguardando ADMIN aprovar |
| `ATIVO` | Em andamento, com parcelas em aberto |
| `QUITADO` | Todas as parcelas quitadas |
| `QUEBRADO` | Encerrado por inadimplência |
| `CANCELADO` | Cancelado antes de qualquer pagamento |

**Reabertura** (decisão P1): COBRANÇA ou ADMIN pode reabrir um acordo
finalizado. Ele volta como estava no momento do encerramento (parcelas
pagas continuam pagas).

---

## 9. Pagamento parcial (decisão P4)

Uma parcela pode ter múltiplos pagamentos. Sistema guarda cada lançamento.

### Status da parcela
| Status | Quando |
|---|---|
| `EM_ABERTO` | Nada pago ainda |
| `PARCIAL` | Pago parte, mas não tudo |
| `QUITADA` | Pago integralmente (valor pago >= valor original) |

### Cálculo da mora pós-pagamento parcial (decisão P4.1)
A mora **continua correndo** sobre o saldo restante. O cliente é "premiado"
por ter pago alguma coisa.

---

## 10. Validações cruzadas (briefing Seção 3)

O sistema valida três invariantes:

1. **Em cada boleto**: `Principal + Juros + Multa = Total`
2. **Em cada parcela**: `Principal + Juros + Multa = Valor da parcela`
3. **Soma agregada**: `total dos boletos = total das parcelas`

Pequenas diferenças de centavos (até R$ 0,05) são aceitas por causa de arredondamento.
Diferenças maiores indicam bug e o sistema avisa.
