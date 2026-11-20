# BOM — N3

Lista de materiais dos dois dispositivos da N3: a caixa `CF-01` e a estação de ventilação `VENT-01`.

Critério: o kit da equipe (ESP32 Basic Starter Kit) cobre a base. A compra completa o que falta para a VENT-01, para a montagem de produto (sensor de tampa, botão e sinalizador de painel) e para a compactação em placa soldada da fase de compactação (opcional, só se sobrar tempo).

## O que já temos (kit + N1)

| Item | Onde é usado |
|---|---|
| ESP32 DevKit V1 30 pinos | CF-01 |
| Sensor DHT11 | CF-01 |
| LED RGB cátodo comum + resistores | CF-01 (semáforo) |
| LEDs 5 mm vermelho, amarelo e verde | CF-01: o vermelho é o sinalizador de retenção |
| Buzzer | CF-01 |
| Módulo relé 2 canais 5 V, active-low | CF-01 (sinalizador) |
| Chaves táteis, protoboard, jumpers (incompletos), cabo micro-USB | protótipo de bancada |

## O que foi comprado (Mercado Livre Full, 13 itens, R$ 307,93, frete grátis)

Funcionamento da VENT-01:

| Item | Para quê |
|---|---|
| ESP32 DevKit V1 30 pinos | cérebro da VENT-01, igual ao da CF-01 |
| Ventoinha 80 mm 12 V 0,15 A | o exaustor: atuador da regra do R8 |
| Fonte 12 V 1 A, plugue P4 | alimenta a VENT-01 inteira (ventoinha + ESP32 via LM2596) |
| Módulo relé 1 canal 5 V (SRD-05VDC) | a VENT-01 liga e desliga a ventoinha. O ESP32 nunca alimenta a carga direto |
| Kit 120 jumpers 20 cm (40 M-M, 40 M-F, 40 F-F) | ligar o ESP32 aos módulos com ou sem protoboard e repor os que faltam no kit |

Montagem de produto e compactação:

| Item | Para quê |
|---|---|
| Regulador step-down LM2596 3 A | baixa os 12 V da fonte para 5 V no `VIN` do ESP32 da VENT-01: uma tomada só. **Ajustar para 5,0 V no multímetro antes de ligar o ESP32** |
| 10 conectores P4 fêmea com borne | recebe o plugue da fonte sem cortar o cabo |
| 6 microchaves fim de curso KW12 | sensor de tampa da CF-01: a tampa aperta a haste ao fechar |
| 10 botões de painel PBS-11B (sem trava) | botão de reset da CF-01, preso no gabinete |
| 10 LEDs RGB difusos cátodo comum, 4 terminais (retangulares 2×5×5 mm) | semáforo de estado no gabinete da CF-01 e indicador de estado da VENT-01 (o LED RGB do kit fica na protoboard). O sinalizador de retenção usa os LEDs vermelhos de 5 mm do kit |
| 10 placas perfuradas 5×7 cm | eletrônica soldada da CF-01 e da VENT-01 (Fase 5) |
| 10 barras de pinos fêmea 1×40 | soquete para o ESP32 e os módulos: encaixam sem solda direta e podem ser trocados |
| 10 barras de pinos macho 1×40 | pontos de conexão na placa para jumpers F-F |
| 10 bornes KF301 2 vias | entrada de alimentação e saída da ventoinha na placa, com parafuso |

## O que a equipe fornece

- **CF-01:** caixa térmica pequena (isopor serve), ainda **não providenciada**.
- **CF-01:** power bank + cabo micro-USB. Testar se o power bank não desliga sozinho com o consumo baixo do ESP32 (~100 mA).
- **Ferramentas (emprestadas, em mãos):** ferro de solda com ponta fina e esponja, estanho, multímetro Minipa ET-2042C, alicates, desencapador, chave de fenda, cabinho AWG 22–24, sugador, terceira mão com lupa, isqueiro, fita isolante. Sem cola quente e sem furadeira.

## Ainda falta (prometido no esquema do CP12 v1.0, não comprado)

| Item | Para quê | Onde conseguir |
|---|---|---|
| Transistor BC337 (NPN) + resistor 1 kΩ | aciona o buzzer da CF-01, para ele não puxar corrente direto do GPIO 27 | tio / loja de eletrônica; qualquer NPN equivalente (BC547, 2N2222) serve |
| Diodo 1N4007 | roda livre nos terminais da ventoinha da VENT-01 | tio / loja de eletrônica; 1N4001–1N4007 servem |
| Resistor 150 Ω | limita a corrente do LED sinalizador | conferir no kit; 220 Ω serve se não houver (LED um pouco menos brilhante) |

São componentes de centavos, mas estão no esquema elétrico entregue. Sem eles a montagem diverge do CP12.

## Ficou de fora de propósito

| Item | Por quê |
|---|---|
| ESP32 reserva | custo; risco aceito. **O CP12 v1.0 listava** "2 ESP32 (VENT-01 + reserva)" e "DHT11 reserva": declarar como limitação no README da N3 |
| DHT11 reserva | custo; risco aceito (idem) |
| Parafusos M3 e termo-retrátil | só para a compactação (Fase 5); fita isolante cobre a bancada |

## Plano B

Se a ventoinha ou a fonte não chegarem, uma ventoinha de 5 V no mesmo relé mantém a arquitetura; só muda a carga.
