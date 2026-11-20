# Estado da N3 — quadro compartilhado

Este é o ponto de encontro entre as frentes (e entre os chats do Claude) que trabalham na N3 ao mesmo tempo.
O **[PLANO-N3.md](PLANO-N3.md)** diz *o que* fazer; este arquivo diz *onde cada frente está agora*.

**Regras de uso**
- Ler este arquivo **inteiro** antes de começar qualquer trabalho.
- Cada frente edita **só a própria seção** e acrescenta linhas no **Diário** (no fim, nunca apaga nem reescreve linhas antigas).
- Algo que a outra frente precisa saber ou fazer vai em **Recados entre frentes**. Quem resolver, marca `[x]` e anota no Diário.
- Atualizar logo depois de cada passo concluído, decisão tomada ou bloqueio encontrado, não só no fim.
- Contratos compartilhados: pinos e ligações em [PINAGEM.md](PINAGEM.md); MQTT em `CONTRATOS.md` (a criar, item 1.1 do plano). Mudou um contrato → avisar em Recados.

---

## Frente Software

*Itens 1.1 a 1.9 do plano: contrato, firmwares CF-01 v2 e VENT-01, infra, backend, banco, autenticação, interface, Telegram, testes/CI.*

- **Status:** não iniciada.
- **Agora:** —
- **Próximo passo:** 1.1 `CONTRATOS.md` v1, transcrevendo o contrato já congelado na seção 6 do CP12 v1.0 (PDF em `docs/n3/`). Firmwares seguem o fluxograma da seção 5.3 (MANUAL 10 min; SEGURO após 3 leituras inválidas; VENT-01 desliga após 15 min ligada sem MQTT).
- **Bloqueios:** —
- **Última atualização:** 20/11

## Frente Hardware

*Fase 2 do plano (e Fase 5, se sobrar tempo): montagem da CF-01 e da VENT-01, ligações, solda.*

- **Status:** peças e ferramentas em mãos; montagem não iniciada.
- **Ferramentas disponíveis:** ferro de solda com ponta fina e esponja, estanho, multímetro **Minipa ET-2042C** (o Victor ainda não sabe usar: explicar cada medição passo a passo, com a posição do seletor e das pontas), alicates, desencapador, chave de fenda, cabinho AWG 22–24 (tirado de cabo de rede), sugador de solda, terceira mão com lupa, isqueiro, fita isolante.
- **Não tem:** cola quente (fica para o acabamento) e furadeira. O botão de reset **não** vai montado em caixa.
- **Agora:** —
- **Próximo passo:** montar a VENT-01 na protoboard seguindo [PINAGEM.md](PINAGEM.md), ajustar o LM2596 para 5,0 V e confirmar o nível de acionamento do relé de 1 canal.
- **Bloqueios:** caixa térmica da CF-01 ainda não providenciada (não foi comprada); BC337 + 1 kΩ e 1N4007 do esquema do CP12 a conseguir com o tio.
- **Última atualização:** 20/11

---

## Recados entre frentes

- [ ] **Hardware → Software:** confirmar se o relé de 1 canal da VENT-01 é acionado em nível alto ou baixo e anotar em PINAGEM.md (o firmware da VENT-01 depende disso).
- [ ] **Software → Hardware:** um programa de teste simples para a VENT-01 (pisca o relé no GPIO 23 a cada 2 s e mostra no Serial) ajuda a validar a montagem antes do firmware definitivo.

---

## Diário

Formato: `DD/MM · frente · o que mudou` (uma linha por evento; só acrescentar).

- 17/11 · geral · merge pendente do CP12 resolvido; repositório alinhado ao PDF entregue (VENT-01); keep-alive MQTT em 60 s.
- 17/11 · geral · PLANO-N3.md criado com fases, decisões técnicas e calendário.
- 18/11 · hardware · compra feita no Mercado Livre (13 itens, R$ 307,93): lista em BOM.md. VENT-01 com fonte única de 12 V + LM2596; microchave KW12 como sensor de tampa; botão PBS-11B como reset.
- 20/11 · hardware · peças e ferramentas em mãos (empréstimo do tio). PINAGEM.md criada como contrato entre firmware e montagem.
- 20/11 · geral · documentação alinhada à compra: README seção 6 virou a lista definitiva de peças por dispositivo; prototipo.md atualizado; PLANO ganhou a tabela "Termos do CP12 × peça real". Hardware fechado: farol/torre 12 V, MOSFET, chave tátil como tampa e carregador USB na VENT-01 estão superados.
- 20/11 · geral · CP12 v1.0 (seções 1–9) conferido contra a compra. PINAGEM, BOM, PLANO e README alinhados ao esquema do PDF: buzzer via BC337 + 1 kΩ, 1N4007 na ventoinha, sinalizador com 150 Ω, LED RGB da VENT-01 marcado como opcional. Faltam BC337, 1N4007 e reservas (ESP32/DHT11) prometidas no BOM do CP12.
- 20/11 · geral · regra fixada: onde o CP12 v1.0 conflita com a compra ou o plano, valem compra e plano (diferença declarada); onde detalha o que faltava, o PDF completa o plano.
- 20/11 · geral · trabalho dividido em duas frentes (software e hardware), cada uma num chat próprio; este quadro criado para manter os dois em sincronia.
