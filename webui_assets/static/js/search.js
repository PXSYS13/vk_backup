// Поиск по перепискам: по базе на этом компьютере, с фильтром по беседе и подгрузкой «ещё».
'use strict';

const SEARCH_PAGE = 100;
const SEARCH_MAX = 500;    // больше программа за раз не отдаёт (SEARCH_LIMIT в webapp/api.py)
const search = {q: '', peer: '', limit: SEARCH_PAGE, res: null, timer: null, chats: null};

function highlight(text, q) {
  const low = text.toLowerCase();
  let i = low.indexOf(q);
  // Длинное сообщение — кусок вокруг первого совпадения
  let start = 0, end = text.length;
  if (text.length > 260 && i > 80) { start = i - 80; }
  if (end - start > 260) end = start + 260;
  let out = start ? '…' : '';
  let pos = start;
  while (i !== -1 && i < end) {
    out += esc(text.slice(pos, i)) + `<mark>${esc(text.slice(i, i + q.length))}</mark>`;
    pos = i + q.length;
    i = low.indexOf(q, pos);
  }
  return out + esc(text.slice(pos, end)) + (end < text.length ? '…' : '');
}

function renderSearchResults() {
  const box = $('#search-results');
  if (!box) return;
  const res = search.res;
  if (!res) { box.innerHTML = `<div class="empty">${icon('search')}Ищет по тексту всех сообщений архива — без интернета.<br>Например: имя, адрес, «пароль от wi-fi», «день рождения».<br><span class="tiny">Клавиша <kbd>/</kbd> — к поиску с любого экрана, <kbd>Esc</kbd> — очистить.</span></div>`; return; }
  if (!res.hits.length) { box.innerHTML = `<div class="empty">${icon('search')}Ничего не нашлось по запросу «${esc(res.query)}»${search.peer ? ' в этой беседе' : ''}</div>`; return; }
  const rows = res.hits.map((m) => {
    const who = m.out ? 'Вы' : (m.from || m.chat);
    const inner = `${avatar(m.chat, m.peer_id)}<div class="min0"><div class="who">${esc(m.chat)}</div>
      <div class="q">${m.peer_id >= CHAT_OFFSET || m.out ? `<span class="tiny">${esc(who)}:</span> ` : ''} ${m.text ? highlight(m.text, res.query) : '<span class="tiny">вложение</span>'}</div></div>
      <div class="when">${esc(day(m.date))}<br>${clock(m.date)}</div>`;
    return m.page ? `<a class="hit" href="${archiveUrl(m.page)}" target="_blank" rel="noopener" title="Открыть переписку на этом сообщении">${inner}</a>` : `<div class="hit">${inner}</div>`;
  }).join('');
  const canMore = res.more && search.limit < SEARCH_MAX;
  const more = canMore ? `<div class="row mt-12 center-row"><button class="btn" data-act="search-more">Показать ещё ${SEARCH_PAGE}</button></div>` : '';
  const shown = res.more ? `Показаны ${num(res.hits.length)} самых новых${canMore ? '' : ' — уточните запрос или выберите беседу, чтобы увидеть остальные'}`
    : `Найдено: ${plural(res.hits.length, 'сообщение', 'сообщения', 'сообщений')}`;
  box.innerHTML = `<p class="tiny mb-10">${shown}. Нажмите на сообщение — откроется переписка на этом месте.</p>
    <div class="hits">${rows}</div>${more}`;
}

function chatOptions() {
  const list = search.chats || [];
  return `<option value="">Во всех беседах</option>` + list.map((c) => `<option value="${c.peer_id}" ${String(c.peer_id) === search.peer ? 'selected' : ''}>${esc(c.title)} · ${plural(c.count, 'сообщение', 'сообщения', 'сообщений')}</option>`).join('');
}

async function loadChats() {
  if (search.chats || loadChats.busy) return;
  loadChats.busy = true;
  try {
    search.chats = (await api('/api/chats')).chats;
    const sel = $('#q-peer');
    if (sel) sel.innerHTML = chatOptions();
  } catch (e) { /* без фильтра поиск всё равно работает */ } finally { loadChats.busy = false; }
}

function renderSearch() {
  const r = state.result;
  if (!r || !r.messages) {
    $('#screen-search').innerHTML = `<div class="stack"><div><h1>Поиск по перепискам</h1></div>
      <div class="card empty">${icon('search')}Здесь будет поиск по всем вашим сообщениям — когда архив будет сохранён.<br><a href="#/home">На главную</a></div></div>`;
    return;
  }
  if ($('#q')) return; // поле уже есть — не сбрасываем то, что человек печатает
  $('#screen-search').innerHTML = `<div class="stack"><div><h1>Поиск по перепискам</h1>
    <p class="muted">${plural(r.messages, 'сообщение', 'сообщения', 'сообщений')} в ${plural(r.chats, 'беседе', 'беседах', 'беседах')}. Поиск идёт по базе на этом компьютере.</p></div>
    <div class="search-bar"><div class="search-box">${icon('search')}<input type="search" id="q" placeholder="Что найти? Например: адрес, имя, номер" value="${esc(search.q)}" autocomplete="off" aria-label="Что найти"></div>
      <select id="q-peer" aria-label="В какой беседе искать">${chatOptions()}</select></div>
    <div id="search-results"></div></div>`;
  renderSearchResults();
  loadChats();
  setTimeout(() => { const q = $('#q'); if (q) q.focus(); }, 0);
}

async function runSearch() {
  const q = search.q.trim();
  if (q.length < 2) { search.res = null; renderSearchResults(); return; }
  const params = new URLSearchParams({q, limit: String(search.limit)});
  if (search.peer) params.set('peer', search.peer);
  const want = params.toString();
  try {
    const res = await api(`/api/search?${want}`);
    // Пока ждали ответа, запрос поменяли — этот ответ уже не нужен
    const now = new URLSearchParams({q: search.q.trim(), limit: String(search.limit)});
    if (search.peer) now.set('peer', search.peer);
    if (now.toString() === want) { search.res = res; renderSearchResults(); }
  } catch (e) { toast(e.message, 'err'); }
}

function clearSearch() {
  search.q = '';
  search.res = null;
  search.limit = SEARCH_PAGE;
  const q = $('#q');
  if (q) q.value = '';
  renderSearchResults();
}

document.addEventListener('input', (e) => {
  if (e.target.id !== 'q') return;
  search.q = e.target.value;
  search.limit = SEARCH_PAGE;
  clearTimeout(search.timer);
  search.timer = setTimeout(runSearch, 250);
});
document.addEventListener('change', (e) => {
  if (e.target.id !== 'q-peer') return;
  search.peer = e.target.value;
  search.limit = SEARCH_PAGE;
  runSearch();
});

onAct('search-more', async () => {
  search.limit += SEARCH_PAGE;
  await runSearch();
});
