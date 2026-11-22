# Orçamento térmico: base técnica e opções de modelo

Estudo de 21/11/2026 sobre a fórmula que a CF-01 usa para decidir quando uma exposição vira QUEBRA. **Status: pesquisa e recomendação. A fórmula do firmware não foi alterada** (a implementação fica para depois de tudo pronto, se sobrar tempo; ver seção 6).

Convenção de verificação: **ABERTA** = a fonte foi lida; **INDIRETA** = só resumo de busca ou agregador; **NÃO CONFIRMADA** = não foi encontrada ou aberta. Números marcados INDIRETA devem ser conferidos na fonte antes de citar na defesa.

## 1. O que o firmware faz hoje

`consumo por segundo c(T) = max(0, 1 + (T − 20)/10)`, com T em °C, e orçamento inicial de **120 unidades** (≈ 2 min a 20 °C, valor de demonstração). O orçamento só é drenado com a tampa aberta; chegando a zero, a caixa entra em QUEBRA. A faixa do comando `config` é 30–600 u.

Essa fórmula **não vem de nenhuma norma**. Ela coincide com um modelo Q10 = 2 exatamente em 20 °C (c = 1) e 30 °C (c = 2); entre os dois pontos é a corda reta da exponencial. Fora dessa faixa diverge:

| T (°C) | Linear (atual) | Q10 = 2 | Q10 = 3 | Arrhenius 83,1 kJ/mol |
|---|---|---|---|---|
| 10 | 0 | 0,50 | 0,33 | 0,30 |
| 15 | 0,50 | 0,71 | 0,58 | 0,55 |
| 20 | 1,00 | 1,00 | 1,00 | 1,00 |
| 25 | 1,50 | 1,41 | 1,73 | 1,77 |
| 30 | 2,00 | 2,00 | 3,00 | 3,08 |
| 35 | 2,50 | 2,83 | 5,20 | 5,26 |
| 40 | 3,00 | 4,00 | 9,00 | 8,84 |

(taxas normalizadas a 20 °C; contas da pesquisa, a reproduzir em código antes de citar.) Duas consequências: abaixo de ~10 °C o linear dá consumo zero, o que é fisicamente falso (a deterioração nunca para); acima de 30 °C ele subestima o estresse e o erro cresce rápido.

**O que "120" significa:** tempo até zero = 120 / c(T): 120 s a 20 °C, 80 s a 25 °C, 60 s a 30 °C, 48 s a 35 °C. É uma escala de demonstração, não corresponde a nenhuma vida útil real.

## 2. Base normativa (o que tem respaldo)

| Fonte | Número | Verificação |
|---|---|---|
| FDA Food Code 2026, §3-501.19 (tempo como controle de saúde pública) | até 4 h fora da refrigeração (saindo a ≤ 5 °C); até 6 h se nunca passar de 21 °C | ABERTA |
| USDA FSIS, "Danger Zone" | até 2 h; **1 h acima de 32,2 °C (90 °F)**; zona de perigo 4,4–60 °C | INDIRETA (página bloqueou o acesso automático) |
| OMS Europa, 18/08/2023 | alimento cozido: máx. 2 h em temperatura ambiente; geladeira < 5 °C | ABERTA |
| São Paulo, Portaria CVS 5/2013, art. 47 (sucedida pela CVS 3/2026, vigência a conferir no DOE-SP) | frio ≤ 10 °C: 4 h; frio de 10 a 21 °C: 2 h (medido no centro do produto, alimento exposto para consumo) | INDIRETA (agregador) |
| ANVISA RDC 216/2004 | resfriar de 60 a 10 °C em até 2 h; refrigerado ≤ 4 °C dura 5 dias. **Não traz** limite de exposição de refrigerado | ABERTA (agregador) |
| Nota Técnica Conjunta 351/2025 (MS/PNI com INCQS-Fiocruz), vacinas | >8 a 25 °C por até 48 h (maioria); alguns produtos 10–24 h; acima de 25 °C descarte; **tempos cumulativos** entre excursões | ABERTA |

Observações honestas:
- A "regra de 2 h / 1 h acima de 32 °C" tem respaldo do FSIS (americano), mas não foi aberta; **não achamos regra regulatória brasileira equivalente**. A CVS é norma do estado de São Paulo; não pesquisamos Santa Catarina.
- Não confirmamos números do Codex, nem limite da OMS para excursão de vacinas, nem a USP <659> (fontes divergentes, texto pago).
- Ponto conceitual útil: a NT 351/2025 diz que excursões **se acumulam e não reiniciam**. É o melhor respaldo para "drenar um orçamento" que não zera ao fechar a caixa.
- As normas usam **faixas discretas**, não um gradiente contínuo. Qualquer fórmula contínua é modelo de engenharia calibrado nesses pontos.

## 3. Base de modelagem

- **Q10 e Arrhenius:** Q10(T) = exp[(Ea/R)(1/T − 1/(T+10))]. A Ea padrão do MKT, **83,144 kJ/mol, equivale a ΔH/R ≈ 10 000 K** e a um Q10 ≈ 3 (não 2). *(Correção: o briefing interno falava em "10 kJ/mol" e "83,14 K"; os valores corretos são 83 kJ/mol e 10 000 K.)* A origem do 83,144 kJ/mol (USP <1079>, protocolos OMS PQS) veio de resumos de busca (NÃO CONFIRMADA na fonte primária).
- **Valores medidos de Q10/Ea** (exemplos, não faixa geral): salada pronta pasteurizada, Q10 = 4,53 e Ea = 105,6 kJ/mol (Haouet et al., 2019, ABERTA); carne de caranguejo, Q10 ≈ 3,4–3,9 (conta nossa sobre a Tabela 6.1 da FAO, ABERTA); vacinas, o indicador VVM da OMS implica Ea ≈ 119 kJ/mol e Q10 ≈ 4,8 (conta nossa sobre a Tabela 1a do documento WHO PQS E006/IN05.3, ABERTA). **Não existe revisão por pares aberta que firme uma faixa "típica" para refrigerados**; Q10 = 2 não é um valor confirmado.
- **Orçamento = indicador tempo-temperatura:** acumular Σ c(T)·Δt até um limite é exatamente o princípio do VVM e dos TTI. A CF-01 é um TTI eletrônico; o VVM (OMS) é a referência regulatória mais próxima.
- **MKT** (Haynes, 1971; USP <1079>) é uma média: não detecta uma exposição curta e intensa, só vale se a degradação for Arrhenius, e a USP restringe seu uso. Serve como **indicador secundário** do período, não como regra de QUEBRA.

## 4. Limitações que devem ser declaradas

- O **DHT11 mede o ar**, não o produto; o produto segue o ar com atraso (inércia da caixa e da massa). Em exposição curta o produto aquece menos que o ar, então o modelo superestima o estresse. Ninguém quantificou isso nas fontes abertas.
- Exatidão ±2 °C, resolução 1 °C, faixa 0–50 °C (valores via páginas de terceiros; tempo de resposta NÃO CONFIRMADO, as cópias do datasheet divergem). Com Ea = 83 kJ/mol, ±2 °C muda c(T) em cerca de ±25% a 30–40 °C.
- **Texto sugerido:** "A temperatura usada é a do ar próximo ao produto, medida por sensor de ±2 °C e 1 °C de resolução. O orçamento é um indicador didático de exposição acumulada, não uma medida da temperatura do produto nem da sua vida útil real."

## 5. Opções de modelo

**A. Manter o linear, com a declaração honesta.** Simples, já testado. Contras: subestima acima de 30 °C, consumo zero abaixo de 10 °C, sem base além de ser corda de Q10 = 2. Texto: "aproximação linear de Q10 = 2 entre 20 e 30 °C, válida nesse intervalo".

**B. Q10 parametrizável, com tabela de 51 entradas (0–50 °C).** c(T) = Q10^((T − T_ref)/10), precomputada em `const float[51]` (o DHT11 tem resolução de 1 °C): sem `powf` em tempo de execução, determinístico e testável. Nunca zera. Parâmetro único e visível. Se Q10 = 3, justificar com a FAO/Haouet/VVM (medições entre 3,4 e 4,8). Gravar o saldo na NVS só a cada N s e em eventos (início, pausa, QUEBRA), não a cada leitura. **Recomendada como padrão.**

**C. Arrhenius com Ea = 83,144 kJ/mol.** Alinhada à USP/OMS e permite exibir MKT do período como indicador secundário. Contras: mais difícil de explicar, a Ea real do produto é desconhecida e a demo quebra em ~14 s se o ambiente passar de 40 °C. Pode citar-se como comparação.

**Calibração pela regra regulatória** (exemplo hipotético, "2 h a 32 °C"): normalizar o modelo em T_ref = 32 °C (c(32) = 1) e usar B = 7200 s evita a escala arbitrária. Tempo até esgotar B = 7200 (min):

| T (°C) | Linear | Q10 = 2 | Arrhenius 83,1 |
|---|---|---|---|
| 25 | 176 | 195 | 259 |
| 30 | 132 | 138 | 149 |
| 32 | 120 | 120 | 120 |
| 35 | 106 | 97 | 87 |
| 40 | 88 | 69 | 52 |
| 45 | 75 | 49 | 31 |

Os três modelos concordam perto da âncora (30–35 °C) e divergem por fator 2–3 longe dela: a escolha do modelo muda o tempo até a QUEBRA na demonstração (secador, mão), e por isso é uma **decisão da coordenação**.

**Possível modelo de regras por faixa (mais próximo das normas):** consumo por faixa em vez de fórmula contínua, por exemplo ≤ 10 °C: 4 h; 10–21 °C: 2 h; 21–32 °C: 2 h; > 32 °C: 1 h, combinando CVS e FSIS. É o que tem mais respaldo cruzado, mas depende de confirmar essas fontes. Um teto absoluto (QUEBRA imediata acima de um limite) só tem respaldo para vacinas (NT 351).

## 6. Decisão registrada

O Victor decidiu (21/11) que isso vai para o **backlog**: a pesquisa e a justificativa estão feitas; **implementar** (mais de uma regra, visíveis nos painéis, editáveis pela coordenação com recomendação e justificativa) fica para **depois de tudo soldado e pronto**, se sobrar tempo, com os testes refeitos. Mudar a fórmula invalida a conferência de `docs/testes.md` e os testes do firmware (`firmware/test/test_logica`). Se não der tempo, fica documentado como **trabalho futuro**, com o texto de limitação da seção 4.

Pendências de verificação antes de citar na defesa: abrir as páginas do USDA FSIS e o texto da CVS 5/2013 / CVS 3/2026, confirmar a vigência no DOE-SP, e conferir a Ea padrão nos protocolos OMS PQS.
