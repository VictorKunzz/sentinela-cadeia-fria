# Wi-Fi e reconexão — comportamento e roteiro de evidência

Tarefa 7 do backlog. Documenta **como o firmware trata a rede**, **como provocar a queda** e **o que precisa aparecer no print** para valer como evidência do CP06.

## 1. O princípio: a rede é opcional para a lógica local

O projeto parte do RISCO-02 — em campanha extramuros a rede **vai** cair. Isso tem uma consequência de arquitetura: nenhuma linha do tratamento de Wi-Fi pode bloquear o laço principal.

Por isso o firmware **não** usa o padrão dos tutoriais:

```cpp
// NÃO fazemos isso:
WiFi.begin(ssid, senha);
while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
```

Esse `while` congela tudo. Enquanto ele gira, a chave de tampa não é lida, o orçamento de exposição não drena e o buzzer não toca — o aparelho fica cego exatamente durante uma falha de rede, que é quando ele mais precisa continuar medindo.

O que fazemos é uma **máquina de estados de rede** amostrada a cada volta do `loop()`:

```
OFFLINE ──(chegou a hora da próxima tentativa)──► ASSOCIANDO
ASSOCIANDO ──(WL_CONNECTED)──► ONLINE
ASSOCIANDO ──(timeout de 10 s)──► OFFLINE  (com backoff)
ONLINE ──(status != WL_CONNECTED)──► ASSOCIANDO  (queda detectada)
```

| Parâmetro | Valor | Por quê |
|---|---|---|
| `WIFI_CHECAGEM_MS` | 500 ms | amostragem do status; barato e mais rápido que a meta de 15 s |
| `WIFI_TIMEOUT_MS` | 10 s | uma associação que não fechou em 10 s não vai fechar; recomeça |
| backoff | 1 → 2 → 4 → 8 → 16 s | não adianta martelar um AP que ainda não voltou |
| `WIFI_HEARTBEAT_MS` | 10 s | log periódico de RSSI, para o print mostrar continuidade |

`WiFi.setAutoReconnect(false)` é deliberado: a pilha do ESP32 reconectaria sozinha, mas **em silêncio**. A reconexão é feita pelo nosso código para que ela apareça no log — é a evidência que a N1 pede, e é o que permite medir quanto tempo a queda durou.

## 2. DHCP: nenhum IP no código

O firmware não fixa endereço. Ao associar, o ESP32 pede configuração ao servidor DHCP do roteador e recebe IP, máscara, gateway e DNS. O log imprime o que foi **recebido**, não o que foi configurado:

```
[WiFi] IP (DHCP): 192.168.0.42   mascara: 255.255.255.0   gateway: 192.168.0.1   DNS: 192.168.0.1
```

Consequência prática: o mesmo binário sobe na rede da faculdade, no roteador de casa e no hotspot do celular do técnico sem recompilar. É também por isso que o painel da coordenação encontra o dispositivo pelo **broker MQTT**, e não pelo IP — o IP pode mudar a cada reconexão.

## 3. RSSI: o número que antecipa a queda

O log imprime o RSSI a cada 10 s, com a leitura em palavras:

| RSSI | Leitura | O que significa no projeto |
|---|---|---|
| ≥ −60 dBm | ótimo | bancada, mesmo cômodo do AP |
| −60 a −70 | bom | operação normal |
| −70 a −80 | fraco | ainda conecta, mas com retransmissão e latência |
| < −80 | instável | quedas intermitentes; é o cenário de campo |

O RSSI é logarítmico e negativo: −80 dBm é **cem vezes** menos potência que −60 dBm. Um valor abaixo de −80 não significa "sem conexão", significa "conexão que vai cair sem avisar" — e é justamente por isso que o RSSI entra no payload de telemetria (`arquitetura-mqtt.md`): a coordenação enxerga a degradação **antes** de o dispositivo sumir.

## 4. Como provocar a queda

Dois caminhos, e eles não provam a mesma coisa.

### A — Bancada (é o que vale)

1. ESP32 conectado ao hotspot do celular ou a um roteador que você controla.
2. Com o monitor serial aberto e a conexão estabelecida, **desligue o Wi-Fi do hotspot / tire o roteador da tomada**.
3. Espere a linha `!!! QUEDA DETECTADA !!!` e as tentativas com backoff.
4. **Ligue o AP de volta.** Sem tocar no código, sem apertar reset, sem novo upload.
5. Espere a linha `=== RECONECTADO ===`, que traz a duração da queda e o novo IP.

Este teste exercita a coisa real: a perda do beacon, o tempo de reassociação e o novo DHCP.

### B — Simulador Wokwi (complementar)

O AP virtual `Wokwi-GUEST` nunca cai sozinho. Para forçar, digite **`d`** no monitor serial do simulador — o firmware chama `WiFi.disconnect()` e a máquina de estados reage como reagiria a uma queda real. O comando **`s`** imprime o status atual sob demanda.

O que o simulador **não** prova: o tempo de volta do AP, a variação de RSSI e a reassociação de rádio. Por isso a evidência do CP06 é a da bancada; a do simulador serve para desenvolver.

## 5. O que precisa aparecer no print

**Evidência 1 — conexão.**

- [ ] as linhas `=== CONECTADO ===` e `IP (DHCP): ...` no monitor serial;
- [ ] o RSSI visível;
- [ ] **relógio do computador visível na mesma captura** (print da tela inteira, não recorte da janela).

**Evidência 2 — reconexão** (uma sequência de 2–3 prints, ou um print único com o log contínuo):

- [ ] (a) estado conectado, com heartbeat `[WiFi] online ... rssi=...`;
- [ ] (b) `!!! QUEDA DETECTADA !!!` e pelo menos uma tentativa de reassociação;
- [ ] (c) `=== RECONECTADO === queda #1 durou X.X s` com o IP novamente obtido.

O trecho `sem upload nem reset` impresso junto da queda existe para o print falar por si: ele mostra que a recuperação foi do firmware, não do operador.

## 6. Log esperado (formato)

```
=== Sentinela de Cadeia Fria ===
Pronto. Estado inicial: FECHADO.
[WiFi] modo estacao (STA). Sem IP fixo: o endereco vem por DHCP.
[WiFi] tentativa 1 de associacao a "..."...
[WiFi] === CONECTADO === em 2140 ms (1 tentativa(s))
[WiFi] IP (DHCP): 192.168.0.42   mascara: 255.255.255.0   gateway: 192.168.0.1   DNS: 192.168.0.1
[WiFi] MAC: 3C:61:05:XX:XX:XX   canal: 6   RSSI: -58 dBm (otimo)
[WiFi] online  ip=192.168.0.42  rssi=-59 dBm (otimo)  uptime=12s

[WiFi] !!! QUEDA DETECTADA !!! (queda #1, status=6) - reconexao automatica iniciada, sem upload nem reset
[WiFi] a logica local segue rodando: estado=FECHADO
[WiFi] tentativa 1 de associacao a "..."...
[WiFi] tentativa expirou (status=6). Nova tentativa em 1000 ms.
[WiFi] tentativa 2 de associacao a "..."...
[WiFi] === RECONECTADO === queda #1 durou 14.5 s (2 tentativa(s), ultima levou 2380 ms)
[WiFi] IP (DHCP): 192.168.0.42   ...
```

Os códigos de `status` são os de `wl_status_t`: `3` = conectado, `6` = desconectado, `1` = SSID não encontrado.

## 7. O que esta tarefa ainda não cobre

- **Reconexão do MQTT** é outra coisa e é a tarefa 10. Ter Wi-Fi de volta não significa ter sessão de broker de volta: as assinaturas de `comando/*` precisam ser refeitas a cada reconexão.
- **Last Will** (`status=offline`) depende do broker, não do Wi-Fi — também tarefa 10.
- **Telemetria perdida durante a queda não é bufferizada** na N1. Store-and-forward é evolução da N2 (RISCO-02).
