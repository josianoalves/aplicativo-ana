'use strict';

const pages = [
  ['dashboard', 'Dashboard', '▦', 'Acompanhe a operação de afiliados e as próximas execuções.'],
  ['pesquisa', 'Pesquisa de produtos', '⌕', 'Consulte as ofertas coletadas e os dados disponibilizados pela Shopee.'],
  ['selecionados', 'Produtos selecionados', '★', 'Confira as oportunidades aprovadas e os motivos da seleção.'],
  ['alta', 'Produtos em alta', '↗', 'Compare os produtos com crescimento observado entre pesquisas.'],
  ['agentes', 'Agentes de IA', '✦', 'Acompanhe a sequência de trabalho e a última atividade de cada agente.'],
  ['videos', 'Produção de vídeos', '▷', 'Adicione material autorizado e confira as variações produzidas.'],
  ['publicacoes', 'Publicações', '⇧', 'Baixe os arquivos para publicar e registre o resultado após a confirmação na Shopee.'],
  ['links', 'Links de afiliados', '↔', 'Consulte os links rastreáveis associados a cada produto.'],
  ['historico', 'Histórico', '◷', 'Revise as execuções, decisões e falhas registradas.'],
  ['configuracoes', 'Configurações', '⚙', 'Ajuste os horários, a pesquisa e o volume de produção.'],
];

const stages = [
  ['research', 'Pesquisa de produtos', 'Consulta o catálogo de ofertas de afiliados.'],
  ['analyze', 'Análise comercial', 'Classifica as oportunidades com base nas métricas disponíveis.'],
  ['select', 'Seleção', 'Registra as melhores oportunidades e as razões da escolha.'],
  ['script', 'Roteiro', 'Prepara texto comercial e narração para cada produto.'],
  ['video', 'Produção de vídeo', 'Monta variações verticais usando material autorizado.'],
  ['links', 'Links de afiliados', 'Gera links rastreáveis para produtos selecionados.'],
  ['publish', 'Preparação da publicação', 'Organiza vídeo, legenda e link para envio.'],
];

const byId = id => document.getElementById(id);
const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
const reais = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const date = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Fortaleza' });
const present = value => value !== null && value !== undefined && value !== '';
const fmt = (value, formatter = number) => present(value) && Number.isFinite(Number(value)) ? formatter.format(Number(value)) : '—';
const time = value => present(value) && Number.isFinite(Date.parse(value)) ? date.format(new Date(value)) : '—';
const isSelected = product => Boolean(product.selected);
const selected = () => state.products.filter(isSelected);
const productName = id => state.products.find(product => String(product.id) === String(id))?.name || 'Produto ' + id;
const normalize = value => String(value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();

let state;
let section;
let needsRender = true;
let busy = false;
let editing = false;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    if (name === 'class') node.className = value;
    else if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else if (name === 'checked') node.checked = value;
    else node.setAttribute(name, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child);
  return node;
}

function panel(title, ...children) {
  return el('article', { class: 'panel' }, title && el('h2', {}, title), children);
}

function empty(message) {
  return el('p', { class: 'empty' }, message);
}

function safeLink(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
      return el('a', { href: parsed.href, target: '_blank', rel: 'noopener noreferrer' }, label);
    }
  } catch {}
  return '—';
}

function productLink(product) {
  const link = safeLink(product.url || product.product_url, product.name);
  return typeof link === 'string' ? product.name : link;
}

function badge(value, style = '') {
  return present(value) ? el('span', { class: 'badge ' + style }, value) : '—';
}

function table(headers, rows, message) {
  if (!rows.length) return empty(message);
  return el('div', { class: 'scroll', tabindex: '0', role: 'region', 'aria-label': 'Tabela de dados' },
    el('table', {},
      el('thead', {}, el('tr', {}, headers.map(header => el('th', { scope: 'col' }, header)))),
      el('tbody', {}, rows.map(row => el('tr', {}, row.map(value => el('td', {}, value ?? '—')))))));
}

function reasons(value) {
  if (Array.isArray(value) && value.length) return el('ul', { class: 'reason-list' }, value.map(item => el('li', {}, item)));
  return value || '—';
}

function scoreChart() {
  const values = ['A', 'B', 'C'].map(grade => [grade, state.products.filter(product => product.grade === grade).length]);
  return chart('Produtos por classificação', values);
}

function chart(title, values) {
  if (!values.length) return panel(title, empty('Os dados aparecerão após as primeiras execuções.'));
  const max = Math.max(1, ...values.map(([, value]) => value));
  return panel(title, el('div', { class: 'chart' }, values.map(([label, value]) =>
    el('div', { class: 'chart-row' }, el('span', {}, label),
      el('meter', { min: 0, max, value, 'aria-label': label }), el('strong', {}, fmt(value))))));
}

function dashboard() {
  const counts = state.counts || {};
  const totalEstimated = counts.estimated_commission ?? counts.estimated;
  const confirmed = counts.confirmed_commission ?? counts.confirmed;
  const tiles = [
    ['Produtos pesquisados', fmt(counts.products ?? state.products.length)],
    ['Produtos selecionados', fmt(counts.selected ?? selected().length)],
    ['Vídeos produzidos', fmt(counts.videos ?? state.videos.length)],
    ['Vídeos publicados', fmt(counts.published ?? state.videos.filter(v => v.publication_id).length)],
    ['Links gerados', fmt(counts.links ?? state.products.filter(p => p.link).length)],
    ['Comissão estimada', fmt(totalEstimated, reais)],
    ['Comissão confirmada', fmt(confirmed, reais)],
    ['Última execução', time(state.last_run?.finished || state.last_run)],
    ['Próxima execução', state.paused ? 'Pausada' : time(state.next_run)],
  ];
  const ready = state.videos.filter(video => video.status === 'ready' || video.filename).length;
  const published = state.videos.filter(video => video.publication_id).length;
  const logs = state.logs.slice(0, 5);
  return [
    state.configured ? null : panel('Conexão com a Shopee', el('p', { class: 'muted' },
      'Preencha as credenciais da Open API no arquivo .env e reinicie o Radar para consultar o catálogo.'),
      safeLink('https://affiliate.shopee.com.br/open_api', 'Acessar Open API de Afiliados')),
    el('div', { class: 'metrics' }, tiles.map(([label, value]) =>
      panel(null, el('p', { class: 'metric-label' }, label), el('p', { class: 'metric-value' }, value)))),
    el('div', { class: 'grid' }, scoreChart(), chart('Produção e publicação', [['Vídeos produzidos', ready], ['Publicações', published]])),
    lastReport(),
    panel('Atividade recente', logTable(logs)),
  ];
}

function lastReport() {
  const report = state.last_run;
  if (!report?.finished) return null;
  const totals = [
    ['Encontrados', report.found], ['Selecionados', report.selected], ['Descartados', report.discarded],
    ['Vídeos produzidos', report.videos], ['Links gerados', report.links], ['Publicações', report.publications],
  ];
  return panel('Relatório da última execução',
    el('p', {}, time(report.finished), ' · ', statusBadge(report.status)),
    el('dl', { class: 'report' }, totals.flatMap(([label, value]) =>
      [el('dt', {}, label), el('dd', {}, fmt(value))])),
    report.failure ? el('p', {}, 'Falha na etapa de ', stageName(report.failure), '.') : null);
}

function productRows(products, mode) {
  if (mode === 'links') {
    return table(['Produto', 'Link rastreável'], products.map(product =>
      [productLink(product), safeLink(product.link, 'Abrir link de afiliado')]), 'Nenhum link gerado.');
  }
  if (mode === 'alta') {
    return table(['Produto', 'Variação de vendas', 'Vendas informadas', 'Nota'],
      products.map(product => [productLink(product), fmt(product.trend * 100) + '%', fmt(product.sales), fmt(product.score)]),
      'O crescimento precisa de duas pesquisas com métricas de vendas disponíveis.');
  }
  if (mode === 'selecionados') {
    return table(['Produto', 'Nota', 'Classificação', 'Motivos', 'Link de afiliado'],
      products.map(product => [productLink(product), fmt(product.score), badge(product.grade, product.grade === 'A' ? 'good' : ''), reasons(product.reasons),
        safeLink(product.link, 'Abrir link')]), 'Nenhum produto selecionado.');
  }
  return table(['Produto', 'Preço', 'Vendas', 'Visualizações', 'Nota dos clientes', 'Avaliações', 'Comissão', 'Classificação', 'Análise'],
    products.map(product => [productLink(product), fmt(product.price, reais), fmt(product.sales), fmt(product.views),
      fmt(product.rating), fmt(product.reviews), present(product.commission_rate) ? fmt(Number(product.commission_rate) * 100) + '%' : '—',
      badge(product.grade), reasons(product.reasons)]), 'Nenhum produto encontrado.');
}

function catalog(products, mode) {
  const rows = el('div');
  const filter = el('input', { type: 'search', placeholder: 'Buscar pelo nome' });
  function update() {
    const query = normalize(filter.value).trim();
    rows.replaceChildren(productRows(products.filter(product => normalize(product.name).includes(query)), mode));
  }
  filter.addEventListener('input', update);
  update();
  return panel(null, products.length ? el('div', { class: 'fields' }, el('label', {}, 'Filtrar produtos', filter)) : null, rows);
}

function logTable(logs) {
  return table(['Horário', 'Etapa', 'Estado', 'Registro'], logs.map(log =>
    [time(log.at), stageName(log.stage), statusBadge(log.status), log.message]), 'Nenhuma atividade registrada.');
}

function stageName(value) {
  return stages.find(([key]) => key === value)?.[1] || ({ run: 'Rotina', system: 'Sistema', publication: 'Publicação manual', report: 'Relatório' })[value] || value;
}

function statusBadge(status) {
  const labels = {
    ok: 'Concluída', success: 'Concluída', done: 'Concluída', ready: 'Pronto', error: 'Falha', failed: 'Falha',
    started: 'Iniciada', running: 'Em execução', paused: 'Pausada', skipped: 'Ignorada', pending: 'Pendente',
    retry: 'Nova tentativa', published: 'Publicado', partial: 'Parcial', prepared: 'Preparado',
  };
  return badge(labels[status] || status, ['ok', 'success', 'done', 'ready', 'published', 'prepared'].includes(status) ? 'good' : 'warn');
}

function agents() {
  return el('div', { class: 'grid' }, stages.map(([key, label, description]) => {
    const last = state.logs.find(log => log.stage === key);
    return panel(label, el('p', { class: 'muted' }, description),
      last ? el('div', {}, statusBadge(last.status), el('p', { class: 'muted' }, time(last.at), ' · ', last.message || '')) :
        empty('Aguardando execução.'));
  }));
}

function download(path, id, label) {
  return el('a', { href: '/api/' + path + '?' + new URLSearchParams({ id }), class: 'button secondary', download: '' }, label);
}

function mediaForm() {
  const products = selected();
  if (!products.length) return panel('Material autorizado', empty('Selecione produtos pela rotina para adicionar clipes.'));
  const input = el('input', { type: 'file', accept: '.mp4,.mov,.m4v,.webm', required: '' });
  const picker = el('select', { required: '' }, products.map(product => el('option', { value: product.id }, product.name + (product.has_media ? ' · clipe cadastrado' : ''))));
  const authorized = el('input', { type: 'checkbox', required: '' });
  const submit = el('button', { class: 'button primary' }, 'Adicionar material');
  const form = el('form', { onsubmit: event => {
    event.preventDefault();
    const file = input.files[0];
    if (!file || !authorized.checked) return;
    const params = new URLSearchParams({ id: picker.value, name: file.name });
    perform(submit, 'Material autorizado adicionado.', () => request('media?' + params, file));
  } },
  el('div', { class: 'fields' }, el('label', {}, 'Produto', picker), el('label', {}, 'Arquivo de mídia', input)),
  el('div', { class: 'actions' }, el('label', { class: 'check' }, authorized, 'Tenho autorização para usar este arquivo.'), submit));
  return panel('Material autorizado', el('p', { class: 'muted' },
    'Use um clipe próprio ou liberado para uso comercial pelo vendedor (MP4, MOV, M4V ou WEBM).'), form);
}

function videos() {
  return [mediaForm(), state.videos.length ? el('div', { class: 'grid video-grid' }, state.videos.map(video =>
    panel(productName(video.product_id), el('p', {}, 'Variação ', video.variant, video.voice ? ' · ' + video.voice : '', ' · ', statusBadge(video.status)),
      video.filename ? el('video', { class: 'video', controls: '', preload: 'none', src: '/api/video?' + new URLSearchParams({ id: video.id }),
        'aria-label': 'Prévia do vídeo de ' + productName(video.product_id) }) : null,
      video.filename ? download('video', video.id, 'Baixar MP4') : null))) :
    panel('Vídeos produzidos', empty('Os vídeos aparecerão aqui quando a produção terminar.'))];
}

function publicationForm(video) {
  const publication = el('input', { required: '', maxlength: '200', placeholder: 'Identificador na Shopee', value: video.publication_id });
  const submit = el('button', { class: 'button primary' }, 'Registrar publicação');
  return el('form', { onsubmit: event => {
    event.preventDefault();
    const id = publication.value.trim();
    if (id) perform(submit, 'Publicação registrada.', () => request('published', { id: video.id, publication_id: id }));
  } }, el('div', { class: 'fields' }, el('label', {}, 'Identificador da publicação confirmada', publication)), submit);
}

function resultsForm(video) {
  const commission = el('input', { type: 'number', step: '0.01', min: '0', required: '', value: video.confirmed_commission });
  const submit = el('button', { class: 'button secondary' }, 'Salvar resultado');
  return el('form', { onsubmit: event => {
    event.preventDefault();
    perform(submit, 'Comissão confirmada registrada.', () =>
      request('results', { id: video.id, confirmed_commission: commission.valueAsNumber }));
  } }, el('div', { class: 'fields' }, el('label', {}, 'Comissão confirmada pela Shopee (R$)', commission)), submit);
}

function publications() {
  const list = state.videos.filter(video => ['ready', 'published'].includes(video.status));
  return [
    panel('Envio pela Shopee', el('p', { class: 'muted' },
      'Baixe o pacote com vídeo, legenda e referência do produto. No app Shopee, marque o produto antes de publicar. Registre o identificador depois da confirmação.')),
    ...list.map(video => panel(productName(video.product_id),
      el('p', {}, 'Variação ', video.variant, video.voice ? ' · ' + video.voice : '', ' · ', statusBadge(video.publication_id ? 'published' : video.status)),
      video.caption ? el('p', {}, video.caption) : null,
      el('div', { class: 'actions publication-actions' }, download('package', video.id, 'Baixar pacote'), safeLink(video.link, 'Abrir link de afiliado')),
      video.publication_id ? el('p', {}, 'Publicação ', video.publication_id, video.published_at ? ' · ' + time(video.published_at) : '') : publicationForm(video),
      video.publication_id ? resultsForm(video) : null)),
    list.length ? null : panel('Pacotes disponíveis', empty('A publicação precisa de um vídeo concluído e de um link de afiliado do produto.')),
  ];
}

function settings() {
  const settings = state.settings;
  const submit = el('button', { class: 'button primary' }, 'Salvar configurações');
  const keyword = el('textarea', { name: 'keywords', maxlength: 400 },
    (settings.keywords || '').split(',').join('\n'));
  const quantities = [
    ['limit', 'Limite de produtos pesquisados', 1, 100], ['select', 'Máximo de produtos selecionados', 1, 10],
    ['variants', 'Variações por produto', 2, 3], ['duration', 'Duração do vídeo (segundos)', 15, 45],
  ];
  const inputs = Object.fromEntries(quantities.map(([key, , min, max]) =>
    [key, el('input', { type: 'number', name: key, value: settings[key], min, max, required: '' })]));
  const timeInputs = Object.fromEntries(stages.slice(0, 5).map(([key]) =>
    [key, el('input', { type: 'time', name: key, value: settings.times?.[key], required: '' })]));
  const backup = el('button', { class: 'button secondary', type: 'button', onclick: () =>
    perform(backup, 'Backup concluído.', () => request('backup', {})) }, 'Fazer backup do banco');
  const form = el('form', { onsubmit: event => {
    event.preventDefault();
    const keywords = keyword.value.split(/[\n,]+/).map(value => value.trim()).filter(Boolean);
    const body = { keywords: keywords.join(','),
      ...Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.valueAsNumber])),
      times: Object.fromEntries(Object.entries(timeInputs).map(([key, input]) => [key, input.value])),
    };
    perform(submit, 'Configurações salvas.', () => request('settings', body));
  } },
  el('div', { class: 'fields' }, el('label', {}, 'Palavras-chave', el('small', {}, 'Use uma por linha. Se deixar em branco, a pesquisa consulta ofertas gerais.'), keyword)),
  el('div', { class: 'fields' }, quantities.map(([key, label]) => el('label', {}, label, inputs[key]))),
  el('h3', {}, 'Horários em Brasília e Fortaleza'),
  el('div', { class: 'fields' }, stages.slice(0, 5).map(([key, label]) => el('label', {}, label, timeInputs[key]))),
  submit);
  return [panel('WhatsApp diário', el('p', { class: 'muted' }, state.whatsapp_mode
      ? 'Modo WhatsApp ativo. O Radar consulta as ofertas gerais e envia três links por ordem de vendas. A pesquisa manual também pode disparar o envio do dia.'
      : 'Modo WhatsApp desativado. Configure a conta Meta e ative RADAR_MODO_WHATSAPP no arquivo .env.')),
    panel('Pesquisa e produção', form),
    panel('Dados locais', el('p', { class: 'muted' }, 'O backup será salvo na pasta de dados do Radar.'), backup)];
}

const views = {
  dashboard,
  pesquisa: () => catalog(state.products, 'pesquisa'),
  selecionados: () => catalog(selected(), 'selecionados'),
  alta: () => catalog(state.products.filter(product => Number(product.trend) > 0).sort((a, b) => b.trend - a.trend), 'alta'),
  agentes: agents,
  videos,
  publicacoes: publications,
  links: () => catalog(state.products.filter(product => product.link), 'links'),
  historico: () => [lastReport(), panel('Execuções registradas', logTable(state.logs))],
  configuracoes: settings,
};

function route() {
  const requested = location.hash.slice(1);
  if (requested === 'main') return;
  editing = false;
  section = pages.find(([id]) => id === requested) || pages[0];
  for (const link of byId('navigation').children) {
    if (link.hash === '#' + section[0]) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  render();
}

function render() {
  const [id, title, , description] = section;
  document.title = title + ' | RADAR SHOPEE AI';
  const view = views[id];
  byId('view').replaceChildren(el('p', { class: 'kicker' }, 'OPERAÇÃO LOCAL'),
    el('h1', { id: 'title' }, title), el('p', { class: 'intro' }, description),
    ...(state ? [view()].flat().filter(Boolean) : [el('p', { class: 'muted' }, 'Aguardando conexão com o Radar…')]));
  needsRender = !state;
}

function announce(message, error = false) {
  const notice = byId('notice');
  notice.classList.toggle('error', error);
  notice.textContent = message;
  notice.hidden = false;
}

async function request(action, body) {
  const headers = body instanceof File ? { 'Content-Type': 'application/octet-stream' } : { 'Content-Type': 'application/json' };
  if (body !== undefined) headers['X-Radar-Token'] = state.csrf;
  const response = await fetch('/api/' + action, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    body: body === undefined || body instanceof File ? body : JSON.stringify(body),
    cache: 'no-store',
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || data?.error) throw new Error(data?.error || 'O Radar respondeu com o código ' + response.status + '.');
  return data;
}

function updateHeader(connected) {
  const status = byId('connection');
  let text = 'Conexão indisponível';
  let style = 'error';
  if (connected) {
    text = state.running ? 'Rotina em execução' : state.paused ? 'Automações pausadas' : 'Radar disponível';
    style = state.running || state.paused ? 'busy' : 'ready';
  }
  status.className = 'status ' + style;
  status.replaceChildren(el('span', { class: 'dot', 'aria-hidden': 'true' }), text);
  byId('run').disabled = busy || !connected || state.running || state.paused || !state.configured;
  byId('pause').disabled = busy || !connected;
  byId('pause').textContent = state?.paused ? 'Retomar automações' : 'Interromper automações';
}

async function refresh(force = false) {
  try {
    const snapshot = await request('state');
    if (!state || JSON.stringify(snapshot) !== JSON.stringify(state)) needsRender = true;
    state = snapshot;
    updateHeader(true);
    const view = byId('view');
    const playing = Array.from(view.querySelectorAll('video')).some(video => !video.paused);
    if (force || (needsRender && !editing && !playing && !view.contains(document.activeElement))) render();
  } catch (error) {
    updateHeader(false);
    if (!state || force) announce(error.message, true);
  }
}

async function perform(button, message, action) {
  if (busy) return;
  busy = true;
  button.disabled = true;
  updateHeader(true);
  try {
    const result = await action();
    announce(result?.message || message);
    editing = false;
    await refresh(true);
  } catch (error) {
    announce(error.message, true);
  } finally {
    busy = false;
    button.disabled = false;
    updateHeader(Boolean(state));
  }
}

byId('navigation').append(...pages.map(([id, title, icon]) =>
  el('a', { href: '#' + id }, el('span', { class: 'nav-icon', 'aria-hidden': 'true' }, icon), title)));
byId('run').onclick = () => perform(byId('run'), 'Pesquisa iniciada.', () => request('run', {}));
byId('pause').onclick = () => {
  const paused = state.paused;
  perform(byId('pause'), paused ? 'Automações retomadas.' : 'Interrupção solicitada.',
    () => request(paused ? 'resume' : 'pause', {}));
};
byId('view').addEventListener('input', event => {
  if (event.target.closest('form')) editing = true;
});
window.addEventListener('hashchange', route);
route();
refresh();
window.setInterval(() => { if (!busy) refresh(); }, 5000);
