# Protótipo do produto — Sentinela de Cadeia Fria

Rascunho visual do que está sendo construído. Duas faces: o **arranjo físico** na caixa térmica (o que o técnico manuseia) e o **painel da coordenação** (a interface que consome a telemetria MQTT). Nada foi montado ainda — é um esboço para guiar a construção.

## 1. Arranjo físico (bancada de campo)

```
                    ┌────────────────────────────────────────┐
                    │            CAIXA TÉRMICA                │
                    │                                         │
   tampa ═══════════╪══╗                                      │
                    │  ║ chave de tampa (fim de curso)        │
                    │  ▼                                       │
                    │ ┌─────────────────────────────────────┐ │
                    │ │  ESP32 DevKit + protoboard          │ │
                    │ │                                     │ │
                    │ │  [DHT11]  ← temperatura/umidade     │ │
                    │ │  🟢🟡🔴  ← LED RGB (semáforo)        │ │
                    │ │  ((•))   ← buzzer                    │ │
                    │ │  [botão reset local]                │ │
                    │ │  [relé] ──────► 🚨 sinalizador       │ │
                    │ └─────────────────────────────────────┘ │
                    │                                         │
                    │  alimentação: USB 5 V (bancada) /       │
                    │               powerbank (campo)         │
                    └────────────────────────────────────────┘
                                    │
                                    │ Wi-Fi (hotspot / AP local)
                                    ▼
                              ((  broker MQTT  ))
```

**Semáforo — leitura imediata pelo técnico:**

| Cor | Significado |
|---|---|
| 🟢 verde | tampa fechada, tudo certo |
| 🟡 amarelo | tampa aberta, orçamento sendo consumido |
| 🔴 vermelho (piscando) + buzzer | QUEBRA — travado até reset |

O **sinalizador de retenção** (acionado pelo relé) é uma luz/torre separada, visível de longe, ligada **remotamente pela coordenação** para dizer "esta caixa fica retida, não use".

## 2. Painel da coordenação (interface MQTT)

Wireframe do painel que assina os tópicos de telemetria e publica comandos. Pode ser um dashboard simples (Node-RED, um app web, ou até MQTT Explorer na N1).

```
┌──────────────────────────────────────────────────────────┐
│  SENTINELA DE CADEIA FRIA · Coordenação            ● online │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  Caixa CF-01                          Última leitura: 2 s  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Estado:   🟡  EXPOSTO                              │   │
│  │  Temperatura:  31.2 °C        Umidade:  58 %        │   │
│  │  Orçamento:  ▓▓▓▓▓▓▓▓░░░░░░░░░░  44.8 / 120         │   │
│  │  Aberturas hoje:  2           Sinal Wi-Fi: -67 dBm  │   │
│  └────────────────────────────────────────────────────┘   │
│                                                            │
│  Ações remotas:                                            │
│   [ 🔔 Disparar alarme ]   [ 🔇 Silenciar ]                │
│   [ ♻ Reset remoto ]                                       │
│   [ 🚨 Ligar sinalizador de retenção ]  [ Desligar ]       │
│                                                            │
│  Últimos eventos:                                          │
│   03:50  QUEBRA        aberturas=2  Tmed=29.3 °C           │
│   03:50  FECHAMENTO#2  dur=48s  restante=0.0              │
│   03:02  ABERTURA #2                                       │
│   ─ comando enviado: rele=ligar  ✔ confirmado 04:10       │
└──────────────────────────────────────────────────────────┘
```

**Estados visuais do cabeçalho de presença** (vêm do tópico `status`, retained):

| Indicador | Origem | Significado |
|---|---|---|
| ● online (verde) | `status = online` | dispositivo conectado e reportando |
| ● offline (cinza) | *Last Will* `status = offline` | dispositivo sumiu da rede |

## 3. Correspondência com os tópicos MQTT

O painel é só uma casca visual sobre a [arquitetura MQTT](arquitetura-mqtt.md):

| Elemento do painel | Tópico |
|---|---|
| Estado / Temp / Umidade / Orçamento / Aberturas / RSSI | `sentinela/cadeia-fria/telemetria` |
| Lista "Últimos eventos" | `sentinela/cadeia-fria/evento` |
| Indicador online/offline | `sentinela/cadeia-fria/status` |
| Botões 🔔 / 🔇 | `sentinela/cadeia-fria/comando/alarme` |
| Botão ♻ Reset | `sentinela/cadeia-fria/comando/reset` |
| Botões 🚨 Ligar/Desligar sinalizador | `sentinela/cadeia-fria/comando/rele` |
| Marcação "✔ confirmado" | `sentinela/cadeia-fria/confirmacao` |

## 4. O que ainda é rascunho

- A tecnologia do painel na N1 (Node-RED × app web × ferramenta genérica de MQTT) ainda será decidida — a tarefa 8 do backlog entrega telemetria; a escolha da casca visual pode ser simples.
- O formato físico do sinalizador de retenção (LED de potência, lâmpada, torre de sinalização) depende do que for adquirido — tarefa 3.
- Cores, ícones e disposição do painel são ilustrativos.
