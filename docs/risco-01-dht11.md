# RISCO-01 — Tempo de resposta do DHT11

| | |
|---|---|
| **Registrado em** | Aula 02 — lançamento da N1 |
| **Responsável pela investigação** | Nicholas (experimento) · Vinicius (registro) |
| **Status** | Aberto — aguardando execução do experimento |
| **Impacto se confirmado** | Alto — invalida a medição central do projeto |
| **Bloqueia** | Tarefa 8 (definição do limite de exposição) |

## Enunciado

O DHT11 pode ser lento demais para acompanhar as exposições que o projeto se propõe a medir.

## Por que isso importa

O Sentinela mede eventos de **30 a 60 segundos** — o tempo típico de uma tampa aberta durante o atendimento. Três características do DHT11 conspiram contra isso:

| Característica | Valor | Consequência |
|---|---|---|
| Taxa de amostragem | ~1 leitura/s | numa exposição de 30 s, temos apenas 30 amostras |
| Resolução de temperatura | 1 °C | variações menores que 1 °C são invisíveis |
| Inércia térmica | **desconhecida** | o encapsulamento precisa aquecer antes do elemento sensor responder |

É a terceira que preocupa. As duas primeiras estão no datasheet; a inércia não está, e é justamente ela que determina se o sensor acompanha um degrau térmico rápido.

**O modo de falha é silencioso.** Se o sensor demora a subir, a temperatura média calculada durante a exposição sai menor que a real. O orçamento consome mais devagar do que deveria, o semáforo permanece amarelo quando já deveria estar vermelho, e o aparelho declara segurança numa situação de risco. Um sensor que erra escandalosamente é um problema; um sensor que erra para o lado otimista, sem avisar, é um perigo.

## Experimento

### Materiais

- BlackBoard UNO R3 + DHT11 montados, imprimindo no serial a cada 1 s
- **Termômetro digital de referência** com resposta rápida — *o grupo ainda não tem; providenciar antes do experimento*
- Fonte de calor estável (secador em ar quente a distância fixa, ou ambiente aquecido controlado)
- Cronômetro
- Planilha para registro

### Procedimento

1. Deixar o DHT11 estabilizar em temperatura ambiente por 5 minutos. Anotar a leitura estável e a do termômetro de referência.
2. **Degrau de subida:** expor o sensor abruptamente à fonte de calor (alvo: ~40 °C, dentro da faixa nominal do DHT11), mantendo distância e posição constantes.
3. Registrar a leitura do DHT11 **a cada segundo** até a estabilização, junto com a leitura do termômetro de referência.
4. **Degrau de descida:** remover a fonte de calor e repetir o registro até voltar à temperatura ambiente.
5. Repetir os passos 2 a 4 **cinco vezes**, para ter dispersão e não uma medida solitária.

### O que medir

| Métrica | Definição | Por que importa |
|---|---|---|
| **t₆₃** | tempo para cobrir 63 % do degrau | constante de tempo térmica do sensor |
| **t₉₀** | tempo para cobrir 90 % do degrau | quando a leitura já é confiável |
| **Erro na média de 60 s** | média DHT11 − média referência, ao longo de 60 s | é exatamente o erro que entra no orçamento |
| **Assimetria** | t₉₀ na subida vs. na descida | sensores costumam esfriar mais devagar do que aquecem |

## Critério de decisão

O DHT11 é considerado **inadequado** se qualquer uma destas condições ocorrer:

- **t₉₀ > 30 s** — leva mais tempo para responder do que dura metade das exposições que queremos medir; ou
- **erro na média de 60 s > 2 °C** — o erro se propaga diretamente para o orçamento de exposição.

Caso contrário, o DHT11 é considerado **suficiente para a N1**, com a limitação documentada e o valor de t₉₀ citado no README.

## Plano B

Em ordem de preferência, caso o critério condene o sensor:

| Alternativa | Vantagem | Custo |
|---|---|---|
| **DS18B20** (1-Wire, à prova d'água) | ±0,5 °C, resolução configurável até 0,0625 °C, versão em sonda de aço responde rápido | baixo |
| **LM35** (analógico) | resposta rápida, saída linear, leitura direta por ADC | muito baixo |
| **Termistor NTC 10k** | o mais barato e o mais rápido; exige linearização por software | mínimo |

Qualquer um deles é externo ao kit — daí a dúvida nº 3 dirigida ao professor.

## Mitigação parcial, independente do resultado

Mesmo que o DHT11 passe no critério, vale adotar:

- **calibrar o offset** contra o termômetro de referência e aplicá-lo no firmware;
- **assumir o pior caso** enquanto a leitura ainda não estabilizou — durante os primeiros t₉₀ segundos de exposição, usar a última temperatura estável conhecida **ou** a leitura atual, o que for maior. Errar para o lado seguro é preferível a errar para o lado confortável.

## Registro de resultados

*A preencher após o experimento.*

| Repetição | t₆₃ (s) | t₉₀ (s) | Erro médio 60 s (°C) | Observações |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

**Conclusão:**
