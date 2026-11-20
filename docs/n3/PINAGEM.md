# Pinagem e ligações — N3

Este arquivo é o **contrato entre o firmware e o hardware**. O código usa estes pinos e a montagem segue estas ligações. Se um pino mudar, mude aqui **e** no firmware no mesmo commit, e registre no [ESTADO.md](ESTADO.md).

Placa dos dois dispositivos: ESP32 DevKit V1 de 30 pinos (`board = esp32dev`).

## CF-01 — caixa (mede)

Pinos já usados em `firmware/src/main.cpp`:

| Função | GPIO | Ligação |
|---|---|---|
| DHT11 (dados) | 4 | módulo DHT11: `VCC` → 3V3, `DATA` → GPIO 4, `GND` → GND |
| Tampa (microchave KW12) | 18 | `COM` → GND, `NA` → GPIO 18. `INPUT_PULLUP`: tampa fechada aperta a haste → LOW = fechada; solta → HIGH = aberta |
| Reset (botão PBS-11B) | 19 | um terminal → GPIO 19, outro → GND (`INPUT_PULLUP`, apertado = LOW) |
| Buzzer (ativo) | 27 | `+` → GPIO 27, `−` → GND |
| LED RGB — vermelho | 25 | via resistor de 220 Ω |
| LED RGB — verde | 26 | via resistor de 220 Ω |
| LED RGB — azul | 33 | via resistor de 220 Ω; terminal comum (o mais longo, cátodo) → GND |
| Relé do sinalizador (canal 1 do módulo de 2 canais) | 23 | módulo: `VCC` → **VIN** (5 V, nunca 3V3: causa brownout), `GND` → GND, `IN1` → GPIO 23. Active-low (`RELE_ATIVO_ALTO = false`) |
| Sinalizador de retenção | — | no borne do relé: `COM` → VIN (5 V); `NA` → resistor 330 Ω → ânodo do LED vermelho de 5 mm; cátodo → GND |

Alimentação: power bank pelo micro-USB.

## VENT-01 — estação de ventilação (só atua)

**Proposta v1** (o firmware da VENT-01 ainda não existe; quem escrever o firmware usa esta tabela):

| Função | GPIO | Ligação |
|---|---|---|
| Relé da ventoinha (módulo 1 canal SRD-05VDC) | 23 | `VCC` → VIN (5 V), `GND` → GND, `IN` → GPIO 23. **Nível de acionamento a confirmar na bancada** (alto ou baixo) e registrar aqui |
| LED RGB de estado — vermelho | 25 | via resistor de 220 Ω |
| LED RGB de estado — verde | 26 | via resistor de 220 Ω |
| LED RGB de estado — azul | 33 | via resistor de 220 Ω; comum → GND |

Os mesmos números de pino da CF-01, de propósito: menos chance de erro na solda e no código.

### Energia da VENT-01 (uma tomada só)

```
Fonte 12 V ──P4── conector P4 fêmea (borne: + e −)
                    │+12 V                          │GND
                    ├──► LM2596 IN+                 ├──► LM2596 IN−
                    │       LM2596 OUT+ (5,0 V) ──► VIN do ESP32
                    │       LM2596 OUT− ─────────► GND do ESP32
                    └──► COM do relé
                           NA do relé ──► fio vermelho (+) da ventoinha
                                          fio preto (−) da ventoinha ──► GND da fonte
```

- **Antes de ligar o ESP32:** com o LM2596 sozinho na fonte, girar o trimpot até o multímetro marcar **5,0 V** na saída.
- Conferir no multímetro qual pino do P4 é o `+` antes de ligar qualquer coisa.
- Para gravar pelo USB, desligar a fonte de 12 V (evita duas alimentações ao mesmo tempo no `VIN`).
- O ESP32 nunca alimenta a ventoinha: ela só recebe 12 V pelo contato do relé.
