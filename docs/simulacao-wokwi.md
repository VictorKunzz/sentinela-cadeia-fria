# Simulação do protótipo — Wokwi

Antes de furar caixa térmica e soldar fio, o circuito é montado e validado em simulador. Este documento registra **por que Wokwi**, **como rodar**, **o que a simulação prova e o que não prova**, e o **roteiro de validação** que precisa passar antes da montagem física.

Arquivos da simulação (dentro de `firmware/`, versionados junto com o código):

| Arquivo | O quê |
|---|---|
| `firmware/diagram.json` | o circuito — peças, posições e ligações |
| `firmware/wokwi.toml` | aponta o simulador para o binário gerado pelo PlatformIO |
| `firmware/platformio.ini` | dois alvos: `esp32dev` (bancada) e `wokwi` (simulação) |

## 1. Por que Wokwi e não Tinkercad

A decisão não é de preferência, é de capacidade.

| Requisito da N1 | Tinkercad | Wokwi |
|---|---|---|
| ESP32 | ❌ só Arduino UNO / micro:bit / ATtiny | ✅ `board-esp32-devkit-v1` |
| Wi-Fi | ❌ não existe | ✅ AP virtual `Wokwi-GUEST`, canal 6, sem senha |
| MQTT com broker real | ❌ | ✅ saída TCP/UDP pela internet (ex.: `test.mosquitto.org`) |
| Relé com contatos COM/NO/NC | ❌ | ✅ `wokwi-relay-module` |
| Rodar o firmware do projeto | ❌ editor próprio | ✅ executa o `.bin` do PlatformIO |
| Circuito versionado em Git | ❌ arquivo na nuvem deles | ✅ `diagram.json`, texto, entra em PR |

O Tinkercad simularia, no máximo, a versão do projeto **anterior à Aula 04** — a BlackBoard UNO sem rádio, que foi abandonada justamente para atender o requisito de conectividade. Metade da N1 (Wi-Fi, MQTT, comando remoto, confirmação, reconexão, *Last Will*) ficaria de fora.

## 2. Como rodar

### Opção A — VS Code (recomendada, integra com o PlatformIO do repo)

1. Instalar as extensões **PlatformIO IDE** e **Wokwi for VS Code**.
2. Ativar a licença do Wokwi: `Ctrl+Shift+P` → `Wokwi: Request a License` (gratuita para uso pessoal/estudo).
3. Compilar o alvo de simulação:

```bash
pio run -e wokwi
```

4. `Ctrl+Shift+P` → `Wokwi: Start Simulator`.

O `wokwi.toml` já aponta para `.pio/build/wokwi/firmware.bin` e `.elf`.

### Opção B — navegador (sem instalar nada, bom para mostrar ao grupo)

1. Abrir <https://wokwi.com/projects/new/esp32>.
2. Colar `firmware/src/main.cpp` na aba de código.
3. Abrir a aba **diagram.json** e colar o conteúdo de `firmware/diagram.json`.
4. Nas **Library Manager**, adicionar `DHT sensor library` e `Adafruit Unified Sensor`.
5. ▶ Play.

> Na opção B o código é compilado pelo Wokwi, não pelo PlatformIO — a flag `SIM_WOKWI` não é definida. Trocar manualmente `TIPO_DHT` para `DHT22` e `BUZZER_PASSIVO` para `true`, ou compilar pela opção A.

## 3. O circuito montado

Mesma pinagem da seção 7 do README — a simulação **não** inventa pinos novos.

| GPIO | Peça no Wokwi | Ligação |
|---|---|---|
| GPIO4 | `wokwi-dht22` | SDA → D4; VCC → 3V3; GND → GND |
| GPIO18 | `wokwi-slide-switch` (tampa) | comum (pino 2) → D18; pino 1 → GND; pino 3 → 3V3 |
| GPIO19 | `wokwi-pushbutton` (reset) | 1.l → D19; 2.l → GND (usa `INPUT_PULLUP`) |
| GPIO25 / 26 / 33 | `wokwi-rgb-led` (semáforo) | R / G / B via resistor 220 Ω; COM → GND (cátodo comum) |
| GPIO27 | `wokwi-buzzer` | pino 2 (+) → D27; pino 1 (−) → GND |
| GPIO23 | `wokwi-relay-module` | IN → D23; VCC → VIN (5 V); GND → GND |
| — | `wokwi-led` vermelho (sinalizador de retenção) | VIN → COM do relé; NO → resistor 330 Ω → LED → GND |

**A chave de tampa é deslizante, não de pressão.** É a única mudança de topologia em relação ao arranjo físico, e é deliberada: a tampa de uma caixa térmica *fica* aberta, e um botão momentâneo obrigaria alguém a segurar o mouse durante os dois minutos de drenagem do orçamento. Na bancada, a peça continua sendo a chave momentânea usada como fim de curso. O firmware não muda — os dois casos são `INPUT_PULLUP` com nível estável.

## 4. Roteiro de validação

Rodar **na ordem**. Cada item é um "pronto quando" verificável; o conjunto valida a tarefa 11 do backlog.

| # | Ação no simulador | Esperado |
|---|---|---|
| 1 | ▶ Play | Serial imprime `=== Sentinela de Cadeia Fria ===` e `Estado inicial: FECHADO`. Semáforo **verde**. |
| 2 | Clicar no DHT e mover o slider de temperatura | Nenhum efeito visível ainda (só é consumido em EXPOSTO) — correto. |
| 3 | Deslizar a chave de tampa para **aberta** | Semáforo vai a **amarelo**; serial imprime `ABERTURA #1`; começa a sair `EXPOSTO T=... restante=...` a cada 1 s. |
| 4 | Deslizar de volta para **fechada** | Semáforo volta a **verde**; serial imprime `FECHAMENTO #1 dur=Xs Tmed=... restante=...`. |
| 5 | Abrir a tampa com o DHT em **20 °C** e cronometrar | O `restante` cai ≈ 1,0 por segundo. |
| 6 | Repetir com o DHT em **40 °C** | O `restante` cai ≈ 3,0 por segundo — **o orçamento ponderado pelo calor é a tese do projeto; se este item falhar, nada mais importa.** |
| 7 | Manter aberta até `restante` ≤ 0 | Serial imprime `QUEBRA aberturas=N Tmed=...`; semáforo **pisca vermelho**; buzzer apita junto, a cada 300 ms. |
| 8 | Fechar e abrir a tampa em QUEBRA | **Nada acontece** — o estado está travado. |
| 9 | Pressionar o botão RESET | Serial imprime `RESET`; volta a **verde**; orçamento volta a 120. |
| 10 | Abrir/fechar a tampa 20 vezes seguidas | Exatamente 20 `ABERTURA` e 20 `FECHAMENTO` — valida o debounce (tarefa 6). |
| 11 | Observar o log logo após o ▶ Play | `=== CONECTADO ===` e `IP (DHCP): 10.10.0.x` do gateway virtual do Wokwi (tarefa 7). |
| 12 | Abrir a tampa e, com o orçamento drenando, digitar `d` no serial | `!!! QUEDA DETECTADA !!!`, tentativas com backoff e `=== RECONECTADO ===` — **e as linhas `EXPOSTO T=... restante=...` não param durante a queda**, provando que a rede não bloqueia a lógica local. |

O relé/sinalizador **ainda não tem como ser acionado** neste roteiro: por decisão de projeto ele é ortogonal à máquina de estados e só responde a comando MQTT (tarefas 9 e 12). Ele já está montado e ligado no `diagram.json`, esperando a camada de rede.

> **Se o farol acender invertido** (aceso em repouso, apagado ao comandar), trocar `"transistor": "pnp"` por `"npn"` no `diagram.json`. O Wokwi inverte a lógica do módulo entre os dois modos, e essa é exatamente a mesma dúvida registrada no README — se o relé do kit é acionado em nível alto ou baixo. O simulador não resolve a dúvida do hardware real; só permite testar as duas hipóteses de graça.

## 5. O que a simulação NÃO prova

Registrado aqui para não virar falsa confiança na hora da montagem.

- **Não valida o RISCO-01.** O DHT do Wokwi responde instantaneamente ao slider. A inércia térmica do encapsulamento — o risco principal do projeto — é justamente o que o simulador não modela. A tarefa 13 continua sendo obrigatoriamente de bancada.
- **Não é DHT11.** O Wokwi não tem essa peça; a simulação usa DHT22, que tem resolução de 0,1 °C e faixa mais larga. **A simulação é otimista** em relação ao sensor real (±2 °C, resolução 1 °C).
- **Não valida elétrica.** Corrente do LED RGB, queda de tensão, capacidade da porta USB, se o relé de 5 V funciona alimentado pelo VIN — nada disso aparece. O simulador não queima componente.
- **Não valida a mecânica.** Se a chave de fim de curso realmente aciona quando a tampa encosta é problema de montagem, não de circuito.
- **Não valida a rede real.** O `Wokwi-GUEST` nunca cai sozinho, e é um AP aberto sem disputa de canal. Testar reconexão (tarefas 7 e 10) exige derrubar o AP de verdade; no simulador a queda só é forçada por software — o comando `d` no monitor serial. O que o simulador não mostra é o tempo de volta do AP, a variação de RSSI e a reassociação de rádio. Ver [`evidencia-wifi.md`](evidencia-wifi.md).

## 6. Próximo passo — camada MQTT no simulador

A tarefa 7 (Wi-Fi + reconexão) **já está no firmware** e roda na simulação: o alvo `wokwi` define `SIM_WOKWI`, que seleciona o AP virtual aberto com canal 6 explícito (`WiFi.begin("Wokwi-GUEST", "", 6)` — o canal fixo dispensa a varredura e acelera muito a associação). No monitor serial da simulação, `d` derruba o Wi-Fi por software e `s` imprime o status.

Faltam as tarefas 8 a 10 (MQTT), com estes pontos de atenção:

- **Broker:** usar `test.mosquitto.org:1883` ou `broker.hivemq.com:1883`. O gateway público do Wokwi dá saída TCP para a internet.
- **Mosquitto local não é alcançável** pelo gateway público. Isso exige o *private gateway* do Wokwi (recurso pago), que expõe a máquina como `host.wokwi.internal`. **Para a N1 isso não é problema:** o plano já é desenvolver com broker público e demonstrar com Mosquitto local na bancada — exatamente o que está em [`arquitetura-mqtt.md`](arquitetura-mqtt.md) e é a dúvida 2 do README dirigida ao professor.
- **Ping não funciona** no Wokwi (sem ICMP). Diagnosticar conectividade por TCP, nunca por ping.
- Dá para inspecionar o tráfego MQTT em PCAP e abrir no Wireshark — material de sobra para a documentação da entrega.
