/* Sentinela de Cadeia Fria: interface web.
   Fala só com a API do backend (ver backend/API.md); nunca com o broker. */
(() => {
  'use strict';

  const POLL_MS = 2500;
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));

  /* ---------- utilidades ---------- */
  const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch { /* sem storage: vale só nesta aba */ } },
    del(k) { try { sessionStorage.removeItem(k); } catch { /* idem */ } },
  };

  const fmtHora = (iso) => (iso ? new Date(iso).toLocaleTimeString('pt-BR') : '—');
  const fmtDataHora = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—');

  function ha(iso) {
    if (!iso) return 'nunca';
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 5) return 'agora';
    if (s < 60) return `há ${s} s`;
    if (s < 3600) return `há ${Math.floor(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
    return `há ${Math.floor(s / 86400)} d`;
  }

  function fmtDur(seg) {
    if (seg == null) return '—';
    const s = Math.round(seg);
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`;
    return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')} min`;
  }

  const num = (obj, casas = 1) => (obj && obj.valor != null ? Number(obj.valor).toFixed(casas).replace('.', ',') : null);

  /* ---------- sessão e API ---------- */
  let sessao = null; // { token, usuario, perfil }

  class ApiError extends Error {
    constructor(status, msg) { super(msg); this.status = status; }
  }

  function detalhe(dados, status) {
    const d = dados && dados.detail;
    if (Array.isArray(d)) return d.map((e) => (e.msg || '').replace(/^Value error, /, '')).filter(Boolean).join('; ') || 'Dados inválidos';
    if (typeof d === 'string') return d;
    return `Erro ${status}`;
  }

  function setConexao(ok) {
    const el = $('#conexao');
    el.classList.toggle('fora', !ok);
    $('#conexao-txt').textContent = ok ? 'conectado' : 'sem conexão';
  }

  async function api(caminho, { method = 'GET', body } = {}) {
    const cab = { Accept: 'application/json' };
    if (sessao) cab.Authorization = `Bearer ${sessao.token}`;
    if (body !== undefined) cab['Content-Type'] = 'application/json';
    let r;
    try {
      r = await fetch(caminho, { method, headers: cab, body: body !== undefined ? JSON.stringify(body) : undefined });
    } catch {
      setConexao(false);
      throw new ApiError(0, 'Sem conexão com o servidor');
    }
    setConexao(true);
    let dados = null;
    try { dados = await r.json(); } catch { /* corpo vazio */ }
    if (r.status === 401 && caminho !== '/login') {
      sair('Sessão expirada. Entre novamente.');
      throw new ApiError(401, 'Sessão expirada');
    }
    if (!r.ok) throw new ApiError(r.status, detalhe(dados, r.status));
    return dados;
  }

  const ehCoordenacao = () => sessao && sessao.perfil === 'coordenacao';

  /* ---------- login / sair ---------- */
  function mostrarLogin(aviso) {
    $('#tela-app').hidden = true;
    $('#tela-login').hidden = false;
    const el = $('#login-aviso');
    el.hidden = !aviso;
    el.textContent = aviso || '';
    el.className = 'msg erro';
    $('#login-senha').value = '';
    $('#login-usuario').focus();
  }

  function sair(aviso) {
    sessao = null;
    store.del('sentinela.sessao');
    pararPolling();
    mostrarLogin(aviso);
  }

  async function entrar(ev) {
    ev.preventDefault();
    const usuario = $('#login-usuario').value.trim();
    const senha = $('#login-senha').value;
    if (!usuario || !senha) {
      const el = $('#login-aviso');
      el.hidden = false; el.className = 'msg erro'; el.textContent = 'Informe usuário e senha.';
      return;
    }
    const btn = $('#login-enviar');
    btn.disabled = true; btn.textContent = 'Entrando…';
    try {
      const r = await api('/login', { method: 'POST', body: { username: usuario, password: senha } });
      sessao = { token: r.access_token, usuario: r.usuario, perfil: r.perfil };
      store.set('sentinela.sessao', JSON.stringify(sessao));
      iniciarApp();
    } catch (e) {
      const el = $('#login-aviso');
      el.hidden = false; el.className = 'msg erro';
      el.textContent = e.status === 401 ? 'Usuário ou senha inválidos.' : e.message;
    } finally {
      btn.disabled = false; btn.textContent = 'Entrar';
    }
  }

  /* ---------- rótulos ---------- */
  const NOME_ATUADOR = { rele: 'Sinalizador de retenção', buzzer: 'Buzzer', exaustor: 'Exaustor' };
  const NOME_COMANDO = { rele: 'Sinalizador', buzzer: 'Buzzer', reset: 'Reset da quebra', config: 'Configurar orçamento', exaustor: 'Exaustor' };
  const NOME_ACAO = { ligar: 'ligar', desligar: 'desligar', auto: 'voltar ao automático', disparar: 'disparar', silenciar: 'silenciar', reset: 'resetar', orcamentoInicial: 'orçamento inicial' };
  const NOME_EVENTO = {
    abertura: 'Tampa aberta', fechamento: 'Tampa fechada', quebra: 'QUEBRA da cadeia fria', reset: 'Reset da quebra',
    sensor_falha: 'Falha do sensor', sensor_ok: 'Sensor recuperado', modo_alterado: 'Mudança de modo', boot: 'Dispositivo ligado',
  };
  const NOME_MODO = { AUTOMATICO: 'Automático', MANUAL: 'Manual', SEGURO: 'Seguro' };
  const MOTIVO = {
    QUEBRA_ATIVA: 'O sinalizador só pode ser desligado depois do reset da quebra.',
    SEM_QUEBRA: 'O reset só vale quando há uma quebra ativa.',
    DUPLICADO: 'Esse comando já tinha sido recebido; nada foi executado de novo.',
    ACAO_INVALIDA: 'Ação inválida para esse comando (ou dispositivo em modo manual).',
    FORA_DA_FAIXA: 'Valor fora da faixa permitida (30 a 600).',
  };

  const COMANDOS = {
    caixa: [
      { titulo: 'Sinalizador de retenção', comando: 'rele', acoes: [['ligar', 'Ligar'], ['desligar', 'Desligar'], ['auto', 'Automático']] },
      { titulo: 'Buzzer', comando: 'buzzer', acoes: [['disparar', 'Disparar'], ['silenciar', 'Silenciar'], ['auto', 'Automático']] },
      { titulo: 'Quebra', comando: 'reset', acoes: [['reset', 'Resetar quebra']] },
    ],
    estacao: [
      { titulo: 'Exaustor (ventoinha)', comando: 'exaustor', acoes: [['ligar', 'Ligar'], ['desligar', 'Desligar'], ['auto', 'Automático']] },
    ],
  };

  /* ---------- painel: cartões ---------- */
  const cards = new Map(); // id -> elemento
  let orcMax = 120;

  function criarCard(d) {
    const el = document.createElement('article');
    el.className = 'card';
    el.id = `card-${d.id}`;
    el.setAttribute('aria-labelledby', `tit-${d.id}`);
    const caixa = d.tipo === 'caixa';

    let comandos = '';
    if (ehCoordenacao()) {
      const grupos = COMANDOS[d.tipo].map((g) => `
        <div class="grupo-cmd">
          <h4>${esc(g.titulo)}</h4>
          <div class="botoes">${g.acoes.map(([acao, rot]) =>
            `<button type="button" class="btn ${g.comando === 'reset' ? 'btn-perigo' : ''}" data-dev="${esc(d.id)}" data-cmd="${g.comando}" data-acao="${acao}">${esc(rot)}</button>`).join('')}
          </div>
        </div>`).join('');
      const config = caixa ? `
        <form class="grupo-cmd config-orc" data-dev="${esc(d.id)}" novalidate>
          <label for="orc-${esc(d.id)}">Orçamento térmico inicial (30 a 600 u)</label>
          <input id="orc-${esc(d.id)}" type="number" min="30" max="600" step="1" inputmode="numeric" value="120">
          <button type="submit" class="btn">Aplicar</button>
        </form>` : '';
      comandos = `<div class="comandos" role="group" aria-label="Comandos de ${esc(d.nome)}">${grupos}${config}</div>`;
    } else {
      comandos = '<p class="somente-leitura">Perfil técnico: somente leitura. Os comandos ficam com a coordenação.</p>';
    }

    el.innerHTML = `
      <div class="card-topo">
        <div>
          <h3 id="tit-${esc(d.id)}">${esc(d.nome)}</h3>
          <p class="contato" data-f="contato"></p>
        </div>
        <span class="pres" data-f="pres"></span>
      </div>
      <div class="estado-grande" data-f="estado"><span data-f="estado-txt"></span><small data-f="estado-sub"></small></div>
      ${caixa ? `
      <div class="valores">
        <div class="valor"><span>Temperatura</span><strong data-f="temp">—</strong></div>
        <div class="valor"><span>Umidade</span><strong data-f="umid">—</strong></div>
        <div class="valor"><span>Orçamento</span><strong data-f="orc">—</strong><div class="barra" data-f="orc-barra"><div></div></div></div>
      </div>` : ''}
      <div class="meta" data-f="meta"></div>
      <div class="atuadores" data-f="atuadores"></div>
      ${comandos}`;
    return el;
  }

  const f = (el, nome) => el.querySelector(`[data-f="${nome}"]`);

  function medida(el, nome, obj) {
    const alvo = f(el, nome);
    const v = num(obj, nome === 'umid' ? 0 : 1);
    alvo.innerHTML = v == null ? '—' : `${v}<i>${esc(obj.unidade)}</i>`;
  }

  function atualizarCard(d) {
    let el = cards.get(d.id);
    if (!el) {
      el = criarCard(d);
      cards.set(d.id, el);
      const ordem = ['CF-01', 'VENT-01'];
      $('#cards').appendChild(el);
      $$('.card', $('#cards')).sort((a, b) => ordem.indexOf(a.id.slice(5)) - ordem.indexOf(b.id.slice(5))).forEach((c) => $('#cards').appendChild(c));
    }
    const caixa = d.tipo === 'caixa';
    el.classList.toggle('offline', !d.online);

    const pres = f(el, 'pres');
    pres.textContent = d.online ? 'online' : 'offline';
    pres.className = `pres ${d.online ? 'online' : 'offline'}`;
    f(el, 'contato').textContent = d.ultimo_contato ? `Último contato: ${ha(d.ultimo_contato)} (${fmtHora(d.ultimo_contato)})` : 'Ainda não deu sinal';

    // estado grande
    const eg = f(el, 'estado');
    const sub = f(el, 'estado-sub');
    if (caixa) {
      const est = d.estado || '—';
      eg.className = `estado-grande ${d.estado || ''}`;
      f(el, 'estado-txt').textContent = est === 'QUEBRA' ? '⚠ QUEBRA' : est;
      sub.textContent = { FECHADO: 'tampa fechada', EXPOSTO: 'tampa aberta', QUEBRA: 'orçamento esgotado' }[d.estado] || 'aguardando telemetria';
      medida(el, 'temp', d.temperatura);
      medida(el, 'umid', d.umidade);
      const o = d.orcamento;
      const ov = num(o, 1);
      f(el, 'orc').innerHTML = ov == null ? '—' : `${ov}<i>${esc(o.unidade)}</i>`;
      if (o && o.valor != null) {
        orcMax = Math.max(orcMax, o.valor);
        const pct = Math.max(0, Math.min(100, (o.valor / orcMax) * 100));
        const barra = f(el, 'orc-barra');
        barra.firstElementChild.style.width = `${pct}%`;
        barra.className = `barra ${o.valor <= 0 ? 'zero' : pct < 30 ? 'baixo' : ''}`;
      }
    } else {
      const ex = (d.atuadores || {}).exaustor;
      eg.className = `estado-grande ${ex === 'ligado' ? 'LIGADO' : ''}`;
      f(el, 'estado-txt').textContent = ex ? `Exaustor ${ex}` : 'Exaustor —';
      sub.textContent = ex ? '' : 'aguardando estado';
    }

    // etiquetas
    const tags = [];
    if (d.modo) tags.push(`<span class="tag ${esc(d.modo)}">Modo: ${esc(NOME_MODO[d.modo] || d.modo)}</span>`);
    if (caixa) {
      if (d.sensor) tags.push(`<span class="tag ${d.sensor === 'ok' ? 'ok-tag' : 'falha'}">Sensor: ${d.sensor === 'ok' ? 'ok' : 'em falha'}</span>`);
      if (d.aberturas != null) tags.push(`<span class="tag">Aberturas: ${d.aberturas}</span>`);
    }
    if (d.rssi && d.rssi.valor != null) tags.push(`<span class="tag">Wi-Fi: ${Math.round(d.rssi.valor)} ${esc(d.rssi.unidade)}</span>`);
    f(el, 'meta').innerHTML = tags.join('');

    // atuadores
    const nomes = caixa ? ['rele', 'buzzer'] : ['exaustor'];
    f(el, 'atuadores').innerHTML = nomes.map((n) => {
      const v = (d.atuadores || {})[n];
      return `<div><span>${esc(NOME_ATUADOR[n])}</span><strong class="${v === 'ligado' ? 'ligado' : ''}">${v ? esc(v) : '—'}</strong></div>`;
    }).join('');
  }

  function renderDispositivos(lista) {
    lista.forEach(atualizarCard);
    atualizarSeletorDispositivos(lista);
  }

  /* ---------- alertas ---------- */
  function renderAlertas(lista) {
    const el = $('#alertas');
    if (!lista.length) {
      el.innerHTML = '<p class="alerta-ok">✔ Nenhum alerta ativo.</p>';
      return;
    }
    el.innerHTML = lista.map((a) => `
      <div class="alerta ${a.severidade === 'critico' ? 'critico' : 'aviso'}" role="${a.severidade === 'critico' ? 'alert' : 'status'}">
        <span class="icone" aria-hidden="true">${a.severidade === 'critico' ? '⛔' : '⚠'}</span>
        <div>${esc(a.mensagem)}<small>${a.desde ? `desde ${fmtDataHora(a.desde)} (${ha(a.desde)})` : ''}</small></div>
      </div>`).join('');
  }

  /* ---------- comandos ---------- */
  // `sem_efeito`: o dispositivo já estava no estado pedido. É informação, não falha:
  // cor neutra, sem alerta. Tolera backend antigo (campo ausente cai nos casos de baixo).
  const semEfeito = (c) => c.status === 'sem_efeito';
  const rotuloComando = (c) => (semEfeito(c) ? 'já estava assim' : c.rotulo);

  function classePill(c) {
    if (semEfeito(c)) return 'neutro';
    if (!c.concluido) return 'pend';
    if (c.status === 'confirmado') return 'ok';
    if (c.status === 'nao_confirmado') return 'aviso';
    return 'erro';
  }

  function renderComandos(lista) {
    const ul = $('#lista-comandos');
    if (!lista.length) { ul.innerHTML = '<li class="vazio">Nenhum comando enviado ainda.</li>'; return; }
    ul.innerHTML = lista.map((c) => {
      const nome = `${NOME_COMANDO[c.comando] || c.comando}: ${NOME_ACAO[c.acao] || c.acao}${c.valor != null ? ` ${c.valor}` : ''}`;
      const quem = c.origem === 'regra' ? 'regra automática' : `por ${esc(c.usuario || 'usuário')}`;
      let extra = '';
      if (c.motivo && MOTIVO[c.motivo]) extra = ` · ${esc(MOTIVO[c.motivo])}`;
      else if (c.detalhe && !semEfeito(c)) extra = ` · ${esc(c.detalhe)}`;
      return `<li>
        <span class="cmd-nome">${esc(c.dispositivo)} · ${esc(nome)}</span>
        <span class="pill ${classePill(c)}">${esc(rotuloComando(c))}</span>
        <span class="cmd-meta">${fmtHora(c.enviado_em)} · ${quem} · ${esc(c.command_id)}${extra}</span>
      </li>`;
    }).join('');
  }

  function aviso(texto, tipo) {
    const el = $('#aviso');
    el.hidden = !texto;
    el.textContent = texto || '';
    el.className = `msg ${tipo || ''}`;
  }

  // Atualiza a mensagem do botão quando o comando termina (até ~20 s). Só a mais recente vale.
  let ultimoAcompanhado = null;
  async function acompanharComando(id, dev) {
    ultimoAcompanhado = id;
    for (let i = 0; i < 25; i += 1) {
      await new Promise((ok) => setTimeout(ok, 800));
      if (ultimoAcompanhado !== id || !sessao) return;
      let c;
      try { c = await api(`/comandos/${encodeURIComponent(id)}`); } catch { continue; }
      if (!c.concluido && !semEfeito(c)) continue;
      if (semEfeito(c)) aviso(`Já estava assim: ${dev} já estava nesse estado, nada mudou (${id}).`, 'neutro');
      else if (c.status === 'confirmado') aviso(`Comando ${id} confirmado por ${dev}.`, 'ok');
      else if (c.status === 'nao_confirmado') aviso(`Sem confirmação de ${dev} no prazo (${id}). Confira o dispositivo.`, 'aviso');
      else aviso(`${dev} recusou o comando ${id}: ${(c.motivo && MOTIVO[c.motivo]) || c.rotulo}.`, 'erro');
      return;
    }
  }

  async function enviarComando(dev, comando, acao, valor, botao) {
    const corpo = { comando, acao };
    if (valor !== undefined) corpo.valor = valor;
    if (botao) botao.disabled = true;
    try {
      const c = await api(`/dispositivos/${encodeURIComponent(dev)}/comandos`, { method: 'POST', body: corpo });
      aviso(`Comando ${c.command_id} enviado para ${dev}: aguardando confirmação do dispositivo…`, 'ok');
      [300, 900, 1800, 3500].forEach((ms) => setTimeout(tick, ms));
      tick();
      acompanharComando(c.command_id, dev);
    } catch (e) {
      aviso(e.status === 403 ? 'Seu perfil não pode enviar comandos.' : `Não foi possível enviar: ${e.message}`, 'erro');
    } finally {
      if (botao) setTimeout(() => { botao.disabled = false; }, 600);
    }
  }

  function ligarEventosComandos() {
    $('#cards').addEventListener('click', (ev) => {
      const b = ev.target.closest('button[data-cmd]');
      if (!b) return;
      enviarComando(b.dataset.dev, b.dataset.cmd, b.dataset.acao, undefined, b);
    });
    $('#cards').addEventListener('submit', (ev) => {
      const form = ev.target.closest('form.config-orc');
      if (!form) return;
      ev.preventDefault();
      const v = Number($('input', form).value);
      if (!Number.isFinite(v)) { aviso('Informe um número para o orçamento.', 'erro'); return; }
      // A faixa (30–600) é validada pelo dispositivo, que responde com FORA_DA_FAIXA se for o caso.
      enviarComando(form.dataset.dev, 'config', 'orcamentoInicial', v, $('button', form));
    });
  }

  /* ---------- polling ---------- */
  let timer = null;
  let emTick = false;

  async function tick() {
    if (!sessao || emTick || document.hidden) return;
    emTick = true;
    try {
      const [devs, alertas, cmds] = await Promise.all([api('/dispositivos'), api('/alertas'), api('/comandos?limite=10')]);
      renderDispositivos(devs);
      renderAlertas(alertas);
      renderComandos(cmds);
    } catch { /* o indicador de conexão já avisa; tenta de novo no próximo ciclo */ }
    finally { emTick = false; }
  }

  function iniciarPolling() { pararPolling(); tick(); timer = setInterval(tick, POLL_MS); }
  function pararPolling() { if (timer) clearInterval(timer); timer = null; }

  /* ---------- histórico ---------- */
  let grafico = null;
  let dispositivosConhecidos = [];

  function atualizarSeletorDispositivos(lista) {
    const sel = $('#h-dispositivo');
    const ids = lista.map((d) => d.id).join(',');
    if (dispositivosConhecidos.map((d) => d.id).join(',') === ids) { dispositivosConhecidos = lista; return; }
    dispositivosConhecidos = lista;
    const atual = sel.value;
    sel.innerHTML = lista.map((d) => `<option value="${esc(d.id)}">${esc(d.nome)}</option>`).join('');
    if (atual) sel.value = atual;
  }

  const cor = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

  /* Gráfico com eixo de tempo REAL e lacunas visíveis.
     O /historico devolve só os `limite` pontos mais recentes (máx. 5000), então
     paginamos por `ate` até cobrir o período. Se o sistema ficou desligado, o
     intervalo vazio aparece como corte na linha e faixa cinza "sem dados". */
  const PAGINA_HIST = 5000;          // máximo aceito por /historico
  const MAX_PAGINAS_HIST = 8;        // ~40 mil pontos (~55 h a 5 s)
  const ALVO_PONTOS = 1200;          // acima disso, médias por faixa de tempo
  const LIMIAR_LACUNA_MIN_MS = 30000; // lacuna = intervalo > max(30 s, 4× o período típico)
  let reqHist = 0;

  async function buscarPontos(dev, grandeza, desdeMs, ateMs) {
    const paginas = [];
    let ate = ateMs;
    let unidade = null;
    let truncado = false;
    for (let i = 0; i < MAX_PAGINAS_HIST; i += 1) {
      const q = new URLSearchParams({
        grandeza,
        desde: new Date(desdeMs).toISOString(),
        ate: new Date(ate).toISOString(),
        janela: '1',            // a média móvel é recalculada aqui, respeitando as lacunas
        limite: String(PAGINA_HIST),
      });
      const h = await api(`/dispositivos/${encodeURIComponent(dev)}/historico?${q}`);
      const p = h.pontos || [];
      if (p.length && unidade == null) unidade = h.unidade;
      paginas.unshift(p);
      if (p.length < PAGINA_HIST) break;
      const primeiro = new Date(p[0].ts).getTime();
      if (primeiro <= desdeMs) break;
      if (i === MAX_PAGINAS_HIST - 1) { truncado = true; break; }
      ate = primeiro - 1;
    }
    const pontos = paginas.flat()
      .map((p) => ({ x: new Date(p.ts).getTime(), y: Number(p.valor) }))
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
      .sort((a, b) => a.x - b.x);
    return { pontos, unidade, truncado };
  }

  // Quebra a série em segmentos contínuos onde o intervalo entre amostras passa do limiar.
  function segmentar(pontos) {
    const deltas = [];
    for (let i = 1; i < pontos.length; i += 1) deltas.push(pontos[i].x - pontos[i - 1].x);
    deltas.sort((a, b) => a - b);
    const mediana = deltas.length ? deltas[Math.floor(deltas.length / 2)] : 0;
    const limiar = Math.max(LIMIAR_LACUNA_MIN_MS, 4 * mediana);
    const segs = [];
    let atual = [pontos[0]];
    for (let i = 1; i < pontos.length; i += 1) {
      if (pontos[i].x - pontos[i - 1].x > limiar) { segs.push(atual); atual = []; }
      atual.push(pontos[i]);
    }
    segs.push(atual);
    return { segs, limiar };
  }

  // Média móvel dentro do segmento: nunca atravessa uma lacuna.
  function comMediaMovel(seg, n) {
    let soma = 0;
    return seg.map((p, i) => {
      soma += p.y;
      if (i >= n) soma -= seg[i - n].y;
      return { x: p.x, y: p.y, ma: soma / Math.min(i + 1, n) };
    });
  }

  // Reduz pontos por faixa de tempo (média), só para não pesar o gráfico.
  function reduzir(seg, larguraMs) {
    if (!(larguraMs > 0)) return seg;
    const saida = [];
    let b = null;
    const fecha = () => saida.push({ x: b.sx / b.n, y: b.sy / b.n, ma: b.sm / b.n });
    seg.forEach((p) => {
      const k = Math.floor(p.x / larguraMs);
      if (!b || b.k !== k) { if (b) fecha(); b = { k, n: 0, sx: 0, sy: 0, sm: 0 }; }
      b.n += 1; b.sx += p.x; b.sy += p.y; b.sm += p.ma;
    });
    if (b) fecha();
    return saida;
  }

  const PASSOS_X = [1, 2, 5, 10, 15, 30].map((m) => m * 60000).concat([1, 2, 3, 6, 12, 24].map((h) => h * 3600000));
  function ticksX(min, max, maxTicks = 8) {
    const passo = PASSOS_X.find((p) => (max - min) / p <= maxTicks) || PASSOS_X[PASSOS_X.length - 1];
    const off = -new Date(min).getTimezoneOffset() * 60000;   // alinha no horário local
    const ticks = [];
    for (let v = Math.ceil((min + off) / passo) * passo - off; v <= max; v += passo) ticks.push(v);
    return ticks;
  }

  // Faixa cinza + "sem dados" por trás das linhas, nos intervalos sem medição.
  const pluginLacunas = {
    id: 'lacunas',
    beforeDatasetsDraw(chart) {
      const lista = chart.$lacunas || [];
      const { ctx, chartArea, scales } = chart;
      if (!lista.length || !scales.x) return;
      ctx.save();
      lista.forEach((g) => {
        const x0 = Math.max(chartArea.left, scales.x.getPixelForValue(g.ini));
        const x1 = Math.min(chartArea.right, scales.x.getPixelForValue(g.fim));
        if (x1 - x0 < 2) return;
        ctx.globalAlpha = 0.85;
        ctx.fillStyle = cor('--neutro-fundo');
        ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.height);
        ctx.globalAlpha = 1;
        ctx.font = '12px system-ui, sans-serif';
        if (x1 - x0 >= ctx.measureText('sem dados').width + 8) {
          ctx.fillStyle = cor('--texto-2');
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('sem dados', (x0 + x1) / 2, chartArea.top + chartArea.height / 2);
        }
      });
      ctx.restore();
    },
  };

  async function carregarHistorico() {
    const dev = $('#h-dispositivo').value || 'CF-01';
    const info = dispositivosConhecidos.find((d) => d.id === dev);
    const caixa = !info || info.tipo === 'caixa';
    const vazio = $('#grafico-vazio');
    $('#h-grandeza').disabled = !caixa;

    if (caixa) {
      const periodo = Number($('#h-periodo').value);
      const ateMs = Date.now();
      const desdeMs = ateMs - periodo * 1000;
      const minha = ++reqHist;
      try {
        const r = await buscarPontos(dev, $('#h-grandeza').value, desdeMs, ateMs);
        if (minha !== reqHist) return;   // o usuário já mudou o filtro: descarta a resposta velha
        desenharGrafico(r, { desdeMs, ateMs, janela: Number($('#h-janela').value) });
      } catch (e) { vazio.hidden = false; vazio.textContent = `Não foi possível carregar o histórico: ${e.message}`; }
    } else {
      if (grafico) { grafico.destroy(); grafico = null; }
      vazio.hidden = false;
      vazio.textContent = 'A estação de ventilação não mede grandezas. Veja abaixo os eventos dela.';
      $('#grafico-resumo').textContent = '';
    }

    try {
      const ev = await api(`/dispositivos/${encodeURIComponent(dev)}/eventos?limite=20`);
      $('#eventos').innerHTML = ev.length ? ev.map((e) => {
        const det = [];
        if (e.n != null) det.push(`abertura nº ${e.n}`);
        if (e.duracao_s != null) det.push(`duração ${fmtDur(e.duracao_s)}`);
        if (e.temperatura_media != null) det.push(`média ${Number(e.temperatura_media).toFixed(1).replace('.', ',')} °C`);
        if (e.consumo != null) det.push(`consumo ${Number(e.consumo).toFixed(1).replace('.', ',')} u`);
        if (e.orcamento != null) det.push(`orçamento ${Number(e.orcamento).toFixed(1).replace('.', ',')} u`);
        if (e.detalhe) det.push(esc(e.detalhe));
        return `<tr><td>${fmtDataHora(e.ts || e.recebido_em)}</td><td>${esc(NOME_EVENTO[e.evento] || e.evento)}</td><td>${det.join(' · ') || '—'}</td></tr>`;
      }).join('') : '<tr><td colspan="3">Nenhum evento registrado.</td></tr>';
    } catch (e) {
      $('#eventos').innerHTML = `<tr><td colspan="3">Não foi possível carregar os eventos: ${esc(e.message)}</td></tr>`;
    }
  }

  function desenharGrafico(r, ctxHist) {
    const vazio = $('#grafico-vazio');
    const { desdeMs, ateMs, janela } = ctxHist;
    if (typeof Chart === 'undefined') {
      vazio.hidden = false; vazio.textContent = 'Biblioteca de gráficos indisponível (sem acesso à CDN).';
      return;
    }
    if (!r.pontos.length) {
      if (grafico) { grafico.destroy(); grafico = null; }
      vazio.hidden = false; vazio.textContent = 'Sem medições neste período.';
      $('#grafico-resumo').textContent = '';
      return;
    }
    vazio.hidden = true;
    const un = r.unidade || '';
    const nomeGr = $('#h-grandeza').selectedOptions[0].textContent;

    // 1) segmentos contínuos e média móvel sem atravessar lacunas
    const { segs, limiar } = segmentar(r.pontos);
    const comMedia = segs.map((s) => comMediaMovel(s, janela));

    // 2) lacunas (inclui o começo e o fim da janela, se estiverem sem dados)
    const lacunas = [];
    if (segs[0][0].x - desdeMs > limiar) lacunas.push({ ini: desdeMs, fim: segs[0][0].x });
    for (let i = 1; i < segs.length; i += 1) lacunas.push({ ini: segs[i - 1][segs[i - 1].length - 1].x, fim: segs[i][0].x });
    const ultimaX = segs[segs.length - 1][segs[segs.length - 1].length - 1].x;
    if (ateMs - ultimaX > limiar) lacunas.push({ ini: ultimaX, fim: ateMs });

    // 3) menos pontos, se for muito (média por faixa de tempo), sempre dentro de cada segmento
    const larguraMs = r.pontos.length > ALVO_PONTOS * 1.5 ? Math.ceil((ateMs - desdeMs) / ALVO_PONTOS) : 0;
    const reduzidos = comMedia.map((s) => reduzir(s, larguraMs));

    // 4) séries com ponto nulo entre segmentos (a linha corta ali)
    const serieValor = []; const serieMedia = []; const raio = [];
    let fimAnterior = null;
    reduzidos.forEach((seg, i) => {
      if (i > 0) {
        const meio = (fimAnterior + seg[0].x) / 2;
        serieValor.push({ x: meio, y: null }); serieMedia.push({ x: meio, y: null }); raio.push(0);
      }
      seg.forEach((p) => {
        serieValor.push({ x: p.x, y: p.y }); serieMedia.push({ x: p.x, y: p.ma }); raio.push(seg.length === 1 ? 3 : 0);
      });
      fimAnterior = seg[seg.length - 1].x;
    });

    const marca = cor('--marca');
    const texto2 = cor('--texto-2');
    const borda = cor('--borda');
    const spanMs = ateMs - desdeMs;
    const dados = {
      datasets: [
        { label: `${nomeGr} (${un})`, data: serieValor, borderColor: marca, backgroundColor: marca, borderWidth: 1.5, pointRadius: raio, pointHoverRadius: 4, tension: 0, spanGaps: false },
        { label: `Média móvel (${janela} pontos)`, data: serieMedia, borderColor: cor('--aviso'), backgroundColor: cor('--aviso'), borderWidth: 2.5, borderDash: [6, 4], pointRadius: raio, pointHoverRadius: 4, tension: 0, spanGaps: false },
      ],
    };
    const dataTick = (v) => {
      const d = new Date(v);
      const hm = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      return spanMs > 20 * 3600000 ? [hm, d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })] : hm;
    };
    const opcoes = {
      responsive: true, maintainAspectRatio: false, animation: false, parsing: false, normalized: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: texto2, usePointStyle: true, pointStyle: 'line' } },
        tooltip: {
          filter: (item) => item.parsed.y != null,
          callbacks: {
            title: (itens) => (itens.length ? new Date(itens[0].parsed.x).toLocaleString('pt-BR') : ''),
            label: (item) => `${item.dataset.label}: ${Number(item.parsed.y).toFixed(1).replace('.', ',')} ${un}`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear', min: desdeMs, max: ateMs,
          afterBuildTicks: (escala) => { escala.ticks = ticksX(desdeMs, ateMs, Math.max(3, Math.min(10, Math.floor(escala.chart.width / 70)))).map((value) => ({ value })); },
          ticks: { color: texto2, maxRotation: 0, autoSkip: false, callback: dataTick },
          grid: { color: borda },
        },
        y: { ticks: { color: texto2 }, grid: { color: borda }, title: { display: true, text: un, color: texto2 } },
      },
    };
    if (grafico) { grafico.$lacunas = lacunas; grafico.data = dados; grafico.options = opcoes; grafico.update(); }
    else { grafico = new Chart($('#grafico'), { type: 'line', data: dados, options: opcoes, plugins: [pluginLacunas] }); grafico.$lacunas = lacunas; grafico.update(); }

    const ultimo = r.pontos[r.pontos.length - 1];
    const totalLacunaS = lacunas.reduce((t, g) => t + (g.fim - g.ini) / 1000, 0);
    let resumo = `${r.pontos.length} pontos${larguraMs ? ' (agrupados por faixa de tempo para exibir)' : ''} · último valor: ${String(ultimo.y).replace('.', ',')} ${un} às ${fmtHora(new Date(ultimo.x).toISOString())}.`;
    if (lacunas.length) resumo += ` ${lacunas.length} período${lacunas.length > 1 ? 's' : ''} sem dados (${fmtDur(totalLacunaS)} no total), destacado${lacunas.length > 1 ? 's' : ''} em cinza no gráfico.`;
    if (r.truncado) resumo += ' Atenção: o período tem mais dados do que a interface carrega; mostrando só os mais recentes.';
    $('#grafico-resumo').textContent = resumo;
    $('#grafico').setAttribute('aria-label', `Gráfico de ${nomeGr} com média móvel. ${lacunas.length ? `${lacunas.length} período(s) sem dados.` : 'Sem lacunas.'}`);
  }

  /* ---------- indicadores ---------- */
  async function carregarIndicadores() {
    const periodo = Number($('#i-periodo').value);
    const q = new URLSearchParams({ dispositivo: 'CF-01', desde: new Date(Date.now() - periodo * 1000).toISOString() });
    const alvo = $('#indicadores');
    try {
      const i = await api(`/indicadores?${q}`);
      const t = i.aberturas_por_turno || {};
      alvo.innerHTML = `
        <div class="indicador"><span>Tempo acumulado em exposição</span><strong>${fmtDur(i.tempo_exposicao_s)}</strong><small>tampa aberta no período</small></div>
        <div class="indicador ${i.tempo_quebra_s > 0 ? 'critico' : ''}"><span>Tempo em QUEBRA</span><strong>${fmtDur(i.tempo_quebra_s)}</strong><small>${i.quebras ?? 0} quebra(s)</small></div>
        <div class="indicador"><span>Aberturas no período</span><strong>${i.aberturas ?? 0}</strong><small>manhã ${t.manha ?? 0} · tarde ${t.tarde ?? 0} · noite ${t.noite ?? 0}</small></div>
        <div class="indicador"><span>Estado atual</span><strong>${esc(i.estado_atual || '—')}</strong><small>orçamento: ${i.orcamento_atual != null ? String(Number(i.orcamento_atual).toFixed(1)).replace('.', ',') + ' u' : '—'}</small></div>`;
      $('#indicadores-nota').textContent = 'Turnos (horário de Brasília): manhã 06–14 h, tarde 14–22 h, noite 22–06 h.';
    } catch (e) {
      alvo.innerHTML = `<p class="vazio">Não foi possível carregar os indicadores: ${esc(e.message)}</p>`;
    }
  }

  /* ---------- regras ---------- */
  async function carregarRegras() {
    const ro = !ehCoordenacao();
    ['#r-ligar', '#r-desligar', '#r-janela', '#r-ativa', '#r-salvar'].forEach((s) => { $(s).disabled = ro; });
    $('#regras-ro').hidden = !ro;
    try {
      const r = await api('/regras');
      $('#r-ligar').value = r.temp_ligar;
      $('#r-desligar').value = r.temp_desligar;
      $('#r-janela').value = r.janela_s;
      $('#r-ativa').checked = !!r.ativa;
      $('#regras-atualizado').textContent = r.atualizado_em ? `Última alteração: ${fmtDataHora(r.atualizado_em)}` : 'Valores iniciais (ainda não alterados).';
    } catch (e) { msgRegras(`Não foi possível carregar: ${e.message}`, 'erro'); }
  }

  function msgRegras(t, tipo) {
    const el = $('#regras-msg');
    el.hidden = !t; el.textContent = t || ''; el.className = `msg ${tipo || ''}`;
  }

  async function salvarRegras(ev) {
    ev.preventDefault();
    const corpo = {
      temp_ligar: Number($('#r-ligar').value),
      temp_desligar: Number($('#r-desligar').value),
      janela_s: Number($('#r-janela').value),
      ativa: $('#r-ativa').checked,
    };
    if (!(corpo.temp_desligar < corpo.temp_ligar)) { msgRegras('O limite de desligar precisa ser menor que o de ligar (histerese).', 'erro'); return; }
    try {
      await api('/regras', { method: 'PUT', body: corpo });
      msgRegras('Regra salva. Vale a partir de agora.', 'ok');
      carregarRegras();
    } catch (e) { msgRegras(e.status === 403 ? 'Seu perfil não pode alterar a regra.' : `Não foi possível salvar: ${e.message}`, 'erro'); }
  }

  /* ---------- abas ---------- */
  const ABAS = ['painel', 'historico', 'indicadores', 'regras'];
  let abaAtual = 'painel';
  let timerAba = null;

  function mostrarAba(nome) {
    if (!ABAS.includes(nome)) nome = 'painel';
    abaAtual = nome;
    ABAS.forEach((a) => { $(`#aba-${a}`).hidden = a !== nome; });
    $$('.abas a').forEach((a) => {
      if (a.dataset.aba === nome) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    clearInterval(timerAba);
    const carregar = { historico: carregarHistorico, indicadores: carregarIndicadores, regras: carregarRegras }[nome];
    if (carregar) {
      carregar();
      if (nome !== 'regras') timerAba = setInterval(() => { if (!document.hidden) carregar(); }, 10000);
    }
  }

  const abaDoHash = () => location.hash.replace('#', '') || 'painel';

  /* ---------- início ---------- */
  function iniciarApp() {
    $('#tela-login').hidden = true;
    $('#tela-app').hidden = false;
    const perfil = sessao.perfil === 'coordenacao' ? 'coordenação' : 'técnico';
    $('#usuario-chip').textContent = sessao.usuario === sessao.perfil ? perfil : `${sessao.usuario} · ${perfil}`;
    cards.clear();
    $('#cards').innerHTML = '';
    mostrarAba(abaDoHash());
    iniciarPolling();
  }

  function init() {
    $('#form-login').addEventListener('submit', entrar);
    $('#btn-sair').addEventListener('click', () => sair());
    $('#form-regras').addEventListener('submit', salvarRegras);
    ['#h-dispositivo', '#h-grandeza', '#h-periodo', '#h-janela'].forEach((s) => $(s).addEventListener('change', carregarHistorico));
    $('#i-periodo').addEventListener('change', carregarIndicadores);
    window.addEventListener('hashchange', () => { if (sessao) mostrarAba(abaDoHash()); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
    ligarEventosComandos();

    try { sessao = JSON.parse(store.get('sentinela.sessao') || 'null'); } catch { sessao = null; }
    if (sessao && sessao.token) iniciarApp();
    else mostrarLogin();
  }

  init();
})();
