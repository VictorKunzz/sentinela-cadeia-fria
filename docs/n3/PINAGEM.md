# Pinagem e ligações — N3

Este arquivo é o **contrato entre o firmware e o hardware**. O código usa estes pinos e a montagem segue estas ligações. Se um pino mudar, mude aqui **e** no firmware no mesmo commit.

Placa dos dois dispositivos: ESP32 DevKit V1 de 30 pinos (`board = esp32dev`). Baseado no esquema elétrico da seção 5.1 do [CP12 v1.0](CP12_EQUIPE-6_PROJETO_v1.0.pdf), adaptado às peças compradas (onde diferem, vale a peça comprada).

## CF-01 — caixa (mede)

Pinos já usados em `firmware/src/main.cpp`:

| Função | GPIO | Ligação |
|---|---|---|
| DHT11 (dados) | 4 | `VCC` → 3V3, `DATA` → GPIO 4, `GND` → GND; pull-up de 10 kΩ entre `DATA` e 3V3 (se for o módulo de 3 pinos, o resistor já vem na plaquinha) |
| Tampa (microchave KW12) | 18 | `COM` → GND, `NA` → GPIO 18. `INPUT_PULLUP`: tampa fechada aperta a haste → LOW = fechada; solta → HIGH = aberta |
| Reset (botão PBS-11B) | 19 | um terminal → GPIO 19, outro → GND (`INPUT_PULLUP`, apertado = LOW) |
| Buzzer (ativo) via transistor BC337 | 27 | GPIO 27 → resistor 1 kΩ → base do BC337; emissor → GND; coletor → `−` do buzzer; `+` do buzzer → VIN (5 V). Nada muda no firmware: HIGH = toca. **BC337 não foi comprado** (ver BOM). **Montagem final (sem BC337):** buzzer ativo ligado direto, `+` → GPIO 27, `−` → GND; funciona, mas puxa corrente do pino. Divergência do esquema do CP12, limitação declarada |
| LED RGB — vermelho | 25 | via resistor de 220 Ω |
| LED RGB — verde | 26 | via resistor de 220 Ω |
| LED RGB — azul | 33 | via resistor de 220 Ω; terminal comum (o mais longo, cátodo) → GND |
| Relé do sinalizador (canal 1 do módulo de 2 canais) | 23 | módulo: `VCC` → **VIN** (5 V, nunca 3V3: causa brownout), `GND` → GND, `IN1` → GPIO 23. Active-low (`RELE_ATIVO_ALTO = false`). **Medido na bancada (20/11) com `VCC` em `VIN`:** `IN1` solto = solto; `IN1`→GND = aciona; `IN1`→3V3 = **solta**. Diferente do módulo de 1 canal da VENT-01, este módulo solta com `HIGH` de 3,3 V, então o `digitalWrite` normal do firmware da CF-01 serve (não precisa de open-drain) |
| Sinalizador de retenção | — | no borne do relé: `COM` → VIN (5 V); `NA` → resistor 150 Ω → ânodo do LED vermelho; cátodo → GND (o CP12 cita LED de 10 mm; usamos o vermelho de 5 mm do kit) |

Alimentação: power bank pelo micro-USB.

## VENT-01 — estação de ventilação (só atua)

Segue o esquema elétrico do CP12 v1.0 (seção 5.1). O firmware da VENT-01 está em `firmware/src/vent01/main.cpp` e segue esta tabela:

| Função | GPIO | Ligação |
|---|---|---|
| Relé da ventoinha (módulo 1 canal SRD-05VDC) | 23 | `VCC` → VIN (5 V), `GND` → GND, `IN` → GPIO 23. **Medido na bancada (20/11): módulo active-low** (aciona com `IN` em GND). **Não solta com `HIGH` de 3,3 V** do ESP32 (VCC do módulo em 5 V): o relé fica acionado. Por isso a saída deve ser **open-drain simulada**: *ligar* = `pinMode(23, OUTPUT)` + `digitalWrite(23, LOW)`; *desligar* = `pinMode(23, INPUT)` (pino flutuando; o módulo puxa a entrada para 5 V e o relé solta). Nunca escrever `HIGH` nesse pino. **Validado com `vent01_teste` (46 ciclos, LED e clique acompanham o Serial).** O módulo não teve o opto-isolamento verificado (o CP12 diz que sim): limitação declarada |
| LED RGB de estado — vermelho | 25 | via resistor de 220 Ω · **opcional**, não está no esquema do CP12 |
| LED RGB de estado — verde | 26 | via resistor de 220 Ω · opcional |
| LED RGB de estado — azul | 33 | via resistor de 220 Ω; comum → GND · opcional |

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

Diodo 1N4007 em antiparalelo nos terminais da ventoinha: faixa (cátodo) no +,
outra ponta no GND. **1N4007 não foi comprado** (ver BOM): a ventoinha roda **sem o diodo** (divergência do CP12, limitação declarada).
```

- **Antes de ligar o ESP32:** com o LM2596 sozinho na fonte, girar o trimpot até o multímetro marcar **5,0 V** na saída.
- Conferir no multímetro qual pino do P4 é o `+` antes de ligar qualquer coisa.
- Para gravar pelo USB, desligar a fonte de 12 V (evita duas alimentações ao mesmo tempo no `VIN`).
- O ESP32 nunca alimenta a ventoinha: ela só recebe 12 V pelo contato do relé.
