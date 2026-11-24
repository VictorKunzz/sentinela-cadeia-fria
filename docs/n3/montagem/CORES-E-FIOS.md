# Cores de fio e notas de montagem (bancada)

Registro da frente Hardware. Serve para o código de cores ser o mesmo em todo o projeto.

## Cabinho disponível (tirado de cabo de rede, fio rígido AWG 22–24)

Marrom, laranja, azul, verde, cada um com o seu par "branco com listras finas da mesma cor" (o branco/cor vale como "branco"), mais variações (azul claro, verde claro). **Preto: pouco.** Não há vermelho.

## Código de cores (a confirmar com o Victor antes de soldar)

| Função | Cor |
|---|---|
| +12 V (fonte) | vermelho-alaranjado |
| GND (qualquer ponto, entrada ou saída) | marrom; branco/marrom quando precisar distinguir entrada de saída |
| +5 V | verde |
| Sinal do ESP32 (ex.: GPIO 23 → IN do relé) | azul |

### CF-01 (remontagem de 21/11)

3V3 vermelho, `VIN` (5 V) verde, GND marrom. Sinais: GPIO 4 (DHT11) branco, 18 (tampa) cinza, 19 (reset) roxo, 27 (buzzer) preto, 25 (RGB vermelho) laranja, 26 (RGB verde) amarelo, 33 (RGB azul) azul, 23 (relé `IN1`) azul. Nesta placa o preto **não** é GND.

## Notas

- **Ventoinha:** o conector branco de 2 pinos aceita a ponta macho de um jumper (confirmado pelo Victor em 20/11). Dá para ligar sem cortar o conector.
- **LM2596 (ZX-001):** furos de solda nos 4 cantos (`IN+`, `IN−`, `OUT+`, `OUT−`), sem borne nem pino. Os furos grandes e redondos são de fixação, não se solda neles. `IN−` e `OUT−` são o mesmo GND: apitam entre si na continuidade, é normal.
