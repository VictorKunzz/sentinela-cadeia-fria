# CF-01: placa perfurada soldada (22 a 23/11)

Placa YS-5CM*7CM (anéis de cobre isolados por furo; não é como protoboard). Toda a eletrônica da CF-01 fica numa placa adaptadora: o ESP32 encaixa num soquete e cada periférico sai por um cabo com a ponta livre, soldada na peça. Alimentação por USB / power bank (`VIN` ≈ 4,7 V). Pinos conforme `PINAGEM.md`.

Convenção de coordenadas: lado dos componentes para cima, USB do ESP32 à esquerda, linhas A (topo) a X, colunas 17 (pino 1, ponta do USB) a 3 (pino 15). Coluna = 18 menos o número do pino.

## O que há na placa

- **Soquete do ESP32:** duas barras fêmea de 15 pinos, nas linhas **H** (fileira de cima: `VIN`, `GND`, D13…) e **R** (fileira de baixo: `3V3`, `GND`, D15…, `D23`). Sobram 7 a 8 linhas livres acima e abaixo.
- **3 pinos macho do relé** na linha C: **C-6 = 5V**, **C-5 = GND**, **C-4 = IN** (jumpers fêmea-fêmea até `VCC`, `GND` e `IN1` do módulo de 2 canais, que fica fora da placa).
- **2 trilhos de GND** (fio nu deitado no cobre): linha **E**, colunas 16 a 12 (ligado ao `GND` de cima por uma ponte laranja H-16 a E-16), e linha **U**, colunas 16 a 12 (ligado ao `GND` de baixo, R-16 a U-16). Os dois GND só se encontram dentro do ESP32.
- **Fios internos:** `VIN` (H-17) a C-6; trilho de cima (E-12) a C-5; `D23` (R-3) a C-4.

## Cabos com ponta livre (15)

Cada cabo desce por um furo da linha vizinha (apoio mecânico) e a ponta é soldada no anel do pino ou no trilho. Os fios de cada periférico são torcidos num cabo só.

| Cabo | Pino do ESP32 / nó | Peça |
|---|---|---|
| `BUZ+` / `BUZ-` | `D27` (GPIO 27) / GND | buzzer ativo (direto no GPIO, sem transistor) |
| `RGB-R` / `RGB-G` / `RGB-B` | `D25` / `D26` / `D33` | LED RGB cátodo comum, com 1 resistor de 220 Ω por cor **na perna do LED** |
| `RGB-K` | GND | cátodo do LED RGB |
| `5V-COM` | `VIN` (entra por I-17, sob o ESP32) | `COM` do canal usado do relé (5 V do sinalizador) |
| `LEDV-` | GND | cátodo do LED vermelho do sinalizador |
| `DHT-3V3` / `DHT-D` / `DHT-GND` | `3V3` / `D4` / GND | DHT11 (cabos de ~50 cm, vai para dentro da caixa) |
| `TAMPA-D` / `TAMPA-GND` | `D18` / GND | chave de tampa KW12 (terminais C e NO; fechada = alavanca apertada = LOW) |
| `RST-D` / `RST-GND` | `D19` / GND | botão de reset PBS-11B |

## Sinalizador

`COM` (5 V) → contato do relé → `NO` → fio → resistor 150/220 Ω → LED vermelho 5 mm (ânodo) → cátodo → `LEDV-` (GND). O relé é active-low: o módulo solta com HIGH em `D23`.

## Verificação

- Continuidade de cada ligação e silêncio entre todos os nós, com a caneta (sem ESP32).
- ESP32 encaixado, só USB: `VIN` 4,75 V, `3V3` 3,29 V, sem reinício; `cf01_teste` sobe.
- No `cf01_teste`: LED RGB (vermelho, verde, azul, apagado), buzzer (tecla `b` sempre normal), reset (APERTADO/solto), tampa (ABERTA/FECHADA), relé e LED vermelho do sinalizador.

## Pendências e limitações declaradas

- **DHT11 e botão de reset tinham falha intermitente** (23/11 à noite): a causa eram soldas soltas nas duas peças; refeitas em 24/11 e ambos passaram a funcionar. Com o firmware definitivo (`esp32dev`), a CF-01 ficou online no painel, alimentada por power bank, junto com a VENT-01 em 12 V.
- Sem BC337 no buzzer (direto no GPIO 27) e placa feita à mão, com excesso de estanho em alguns pontos (sem pontes, conferido com continuidade).
- O bip automático de 5 s do `cf01_teste` pode sair curto quando coincide com a leitura do DHT11 (só no programa de teste; o firmware definitivo liga o buzzer por nível).
