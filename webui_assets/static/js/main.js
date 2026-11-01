// Каркас: маршруты, перерисовка по опросу статуса, тема, подсказки, клавиши. Этот файл — последним.
'use strict';

const ROUTES = ['home', 'dashboard', 'search', 'stats', 'setup', 'security', 'help'];
const POLL_EVERY = 1500;

const routeName = () => {
  const name = location.hash.replace('#/', '') || 'home';
  return ROUTES.includes(name) ? name : 'home';
};

const SCREENS = {
  home: () => {
    const open = [...document.querySelectorAll('#screen-home details[open]')].map((d) => d.dataset.key);
    renderHome();
    for (const k of open) { const d = document.querySelector(`#screen-home details[data-key="${k}"]`); if (d) d.open = true; }
  },
  dashboard: renderDashboard,
  setup: renderSetup,
  search: renderSearch,
  stats: renderStats,
  security: renderSecurity,
  help: () => { if (!$('#screen-help').innerHTML) renderHelp(); },
};

function route() {
  const name = routeName();
  for (const s of document.querySelectorAll('.screen')) s.classList.toggle('hidden', s.id !== `screen-${name}`);
  for (const a of document.querySelectorAll('.nav a')) {
    const on = a.dataset.route === name;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  if (name === 'security') api('/api/security').then((d) => { security = d; render.sig = null; render(); }).catch(() => {});
  if (name === 'dashboard') loadDashboard(true);
  if (name !== 'search') $('#screen-search').innerHTML = '';
  if (name !== 'setup') setupUi.error = '';
  render.sig = null;
  render();
  window.scrollTo(0, 0);
}

// Вкладка браузера тоже показывает, как идут дела: «42% · Бэкап ВКонтакте»
function syncTitle() {
  const job = state.job;
  const t = mediaTotals(state.result);
  let title = APP_TITLE;
  if (offline) title = `Нет связи · ${APP_TITLE}`;
  else if (job.state === 'running' && job.step === 'download' && t.all) title = `${Math.floor(t.done * 100 / t.all)}% · ${APP_TITLE}`;
  else if (job.state === 'running' && job.step === 'waiting') title = `Ждём ВК · ${APP_TITLE}`;
  else if (isBusy(job)) title = `Работаю… · ${APP_TITLE}`;
  if (document.title !== title) document.title = title;
}

function render() {
  if (!state) return;
  const name = routeName();
  const lock = $('#side-lock');
  lock.classList.toggle('bad', !state.network.installed);
  $('#side-lock-text').textContent = state.network.installed ? 'только файлы ВК' : 'выключен!';
  $('#offline').classList.toggle('hidden', !offline);
  syncTitle();
  // Перерисовываем, только если что-то поменялось: иначе сбрасывались бы раскрытые списки и выделение.
  // И не пока человек печатает путь — курсор прыгал бы в начало поля
  const view = name === 'dashboard'
    ? [slowJob(state.job), state.result && state.result.last_run, dash, dashError]
    : [state.job, state.result, insightsKey, name === 'security' ? [state.network, security] : null];
  const sig = JSON.stringify([name, state.settings, view]);
  if (sig === render.sig) return;
  const screen = $(`#screen-${name}`);
  const typing = document.activeElement && document.activeElement.matches('#screen-setup input[type=text]');
  if (name === 'setup' && typing) return;
  // Человек выделяет текст (например, путь, чтобы скопировать) — не стираем выделение перерисовкой
  const sel = window.getSelection();
  if (sel && !sel.isCollapsed && screen.contains(sel.anchorNode)) return;
  render.sig = sig;
  keepFocus(screen, SCREENS[name]);
  applySizes(screen);
  markBusy(screen);
}

// Панели не нужны счётчики, которые меняются каждые полторы секунды: свежие числа она берёт
// из своей сводки раз в несколько секунд, а перерисовка на каждом опросе сбивала бы фокус
const slowJob = (job) => [job.state, job.step, job.started_at, job.problem_text, job.next_retry];

async function refresh() {
  const seq = refresh.seq = (refresh.seq || 0) + 1;
  try {
    const fresh = await api('/api/status');
    if (seq !== refresh.seq) return; // пока ждали, ушёл запрос новее — его ответ и покажем
    state = fresh;
    offline = false;
  } catch (e) {
    if (seq !== refresh.seq) return;
    // Окно программы закрыли или компьютер уснул: скажем об этом, а не будем молча показывать старое.
    // Ошибка самой программы — не повод говорить, что она закрыта: следующий опрос попробует снова
    if (!e.offline) return;
    offline = true;
    $('#offline').classList.remove('hidden');
    if (state) syncTitle();
    return;
  }
  if (state.result && state.result.index && state.job.step !== 'download') loadInsights();
  if (routeName() === 'dashboard') loadDashboard();
  render();
}

// ── Тема ──
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('vk-backup-theme', theme); } catch (e) { /* приватный режим */ }
  syncThemeButton();
}
function syncThemeButton() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  $('#theme-label').textContent = dark ? 'Светлая тема' : 'Тёмная тема';
  $('#theme-toggle .ico').innerHTML = icon(dark ? 'sun' : 'moon');
}
onAct('theme', () => applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'));

// ── Подсказки над графиками ──
document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('[data-tip]');
  const tip = $('#tip');
  if (!el) { tip.classList.add('hidden'); return; }
  tip.textContent = el.dataset.tip;
  tip.classList.remove('hidden');
});
document.addEventListener('mousemove', (e) => {
  const tip = $('#tip');
  if (tip.classList.contains('hidden')) return;
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = `${x}px`;
  tip.style.top = `${e.clientY + 16}px`;
});

document.addEventListener('input', (e) => {
  if (e.target.closest('#screen-setup')) form = readForm();
});

document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-act]');
  if (btn) runAction(btn, e);
});

// «/» — к поиску с любого экрана, Esc в поле поиска — очистить его
document.addEventListener('keydown', (e) => {
  const typing = e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
  // В русской раскладке та же клавиша печатает точку — поэтому смотрим и на саму клавишу (code)
  const slash = e.key === '/' || (e.code === 'Slash' && !e.shiftKey);
  if (slash && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    if (routeName() !== 'search') location.hash = '#/search';
    else if ($('#q')) $('#q').focus();
  } else if (e.key === 'Escape' && e.target.id === 'q') {
    e.preventDefault();
    clearSearch();
  }
});

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', () => {
  hydrateIcons();
  syncThemeButton();
  route();
  refresh();
  setInterval(refresh, POLL_EVERY);
});
