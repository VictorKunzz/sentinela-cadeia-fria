# VENT-01: placa perfurada soldada (22/11)

Placa YS-5CM*7CM (anéis de cobre isolados por furo; não é como protoboard). Só há 5 V na placa: os 12 V da ventoinha não passam por ela.

## O que há na placa

- **Soquete do ESP32:** duas barras fêmea de 15 pinos soldadas; o ESP32 encaixa por cima (USB para a esquerda, `VIN` na ponta do USB da fileira de cima, `D23` na ponta oposta da fileira de baixo).
- **Borne KF301** (borda esquerda, linhas C e E da coluna da borda, entradas de fio voltadas para fora): polo de baixo = **+5 V**, polo de cima = **GND**, vindos do LM2596 (`OUT+` e `OUT−`).
- **3 pinos macho** (5V, GND, IN) para os jumpers fêmea-fêmea do módulo do relé, que fica fora da placa.

## Fios por baixo (lado do cobre), 5 no total

| # | Cor | De | Para |
|---|---|---|---|
| 1 | verde | `VIN` do soquete | pino 5V do relé |
| 2 | verde | pino 5V do relé | polo +5 V do borne |
| 3 | laranja (ou marrom) | `GND` do soquete (ao lado do `VIN`) | pino GND do relé |
| 4 | laranja (ou marrom) | pino GND do relé | polo GND do borne |
| 5 | azul | `D23` do soquete | pino IN do relé |

O ESP32 tem dois `GND` ligados entre si; só o da fileira de cima (ao lado do `VIN`) é usado. O `GND` de baixo (ao lado do `3V3`) teve o anel levantado na solda e fica sem uso.

## Jumpers do relé

| Módulo do relé | Pino da placa |
|---|---|
| `VCC` | 5V |
| `GND` | GND |
| `IN` | IN |

## Lado de 12 V (fora da placa)

- `+` do P4 → `IN+` do LM2596 e `COM` do relé.
- `−` do P4 → `IN−` do LM2596 e fio preto da ventoinha (os 12 V da ventoinha voltam direto à fonte).
- `NO` do relé → fio vermelho da ventoinha. `NC` sem uso.
- LM2596 ajustado a 5,03 V (não mexer no trimpot): `OUT+` e `OUT−` vão ao borne da placa.

## Verificação (22/11)

- 5,04–5,05 V no `OUT+`/`OUT−` do LM2596, no `VIN`/`GND` do soquete e nos pinos 5V/GND do relé.
- Continuidade de cada fio nos dois sentidos e sem curto entre os nós (+5 V, GND, IN).
- ESP32 encaixado: VENT-01 online no painel.
- Relé e ventoinha: ligar e desligar o exaustor pelo painel funcionam e ficam confirmados.

Limitações declaradas: sem diodo 1N4007 na ventoinha (não comprado); placa feita à mão, com excesso de estanho em alguns pinos do soquete (sem pontes, conferido com continuidade).
