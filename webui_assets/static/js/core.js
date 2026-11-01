// Бэкап ВКонтакте — страница программы. Без библиотек и без запросов куда-либо, кроме этой программы.
// Обычные скрипты без сборки: верхние объявления видны всем файлам из js/. Этот — первым:
// состояние, форматирование, иконки, запросы, уведомления и реестр кнопок.
'use strict';

const VK_DATA_PAGE = 'https://vk.com/data_protection?section=rules&scroll_to_archive=1';
const APP_TITLE = 'Бэкап ВКонтакте';
let state = null;
let offline = false;       // программа не ответила на последний опрос
let security = null;
let insights = null;       // /api/stats: цифры и «В этот день»
let insightsKey = null;    // для какого архива они посчитаны
let form = null;           // черновик настроек, пока человек их правит
let dash = null;           // /api/dashboard
let dashAt = 0;            // когда панель загружена: 0 — загрузить при следующем опросе
const speed = [];          // [время, скачано файлов, байт] — для скорости и «осталось ≈»

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = (n) => Number(n || 0).toLocaleString('ru-RU');
// Путь в архиве → адрес в программе. #m123 в конце — место сообщения на странице беседы
function archiveUrl(rel) {
  const m = /^(.*?)(#m\d+)?$/.exec(String(rel));
  return '/archive/' + m[1].split('/').map(encodeURIComponent).join('/') + (m[2] || '');
}

function word(n, one, few, many) {
  const n10 = n % 10, n100 = n % 100;
  return n10 === 1 && n100 !== 11 ? one : (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? few : many);
}
const plural = (n, one, few, many) => `${num(n)} ${word(Number(n || 0), one, few, many)}`;

function bytes(n) {
  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  let i = 0; n = Number(n || 0);
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0).replace('.', ',')} ${units[i]}`;
}

const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
function day(ts) { const d = new Date(ts * 1000); return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`; }
function clock(ts) { const d = new Date(ts * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; }
// «сегодня в 14:23», «вчера в 09:05», «28 октября 2026 в 14:23»
function when(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  return `${days === 0 ? 'сегодня' : days === 1 ? 'вчера' : day(ts)} в ${clock(ts)}`;
}
function duration(sec) {
  sec = Math.max(0, Math.round(Number(sec) || 0));
  if (sec < 60) return plural(sec, 'секунда', 'секунды', 'секунд');
  const m = Math.round(sec / 60);
  if (m < 60) return plural(m, 'минута', 'минуты', 'минут');
  const h = Math.floor(m / 60);
  return `${plural(h, 'час', 'часа', 'часов')} ${m % 60 ? plural(m % 60, 'минута', 'минуты', 'минут') : ''}`.trim();
}
function initials(name) {
  return (String(name || '').split(/\s+/).filter((w) => w && /[\p{L}\p{N}]/u.test(w[0])).slice(0, 2).map((w) => w[0]).join('') || '?').toUpperCase();
}
const CHAT_OFFSET = 2000000000;
// «Вы → Пётр», «Пётр», «Анна в «Друзья»» — без повтора имени, когда переписка личная
function whoWhere(m) {
  if (m.out) return `Вы → ${m.chat}`;
  return m.peer_id >= CHAT_OFFSET ? `${m.from || '?'} в «${m.chat}»` : (m.from || m.chat);
}
const avatar = (name, id) => `<span class="ava c${Math.abs(Number(id) || 0) % 8}">${esc(initials(name))}</span>`;
const isBusy = (job) => job.state === 'running' || job.state === 'stopping';

// ── Иконки (контурные, 24×24) ──
const ICONS = {
  logo: '<path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8"/><rect x="1.5" y="3" width="21" height="5" rx="1.5"/><path d="M12 11v6"/><path d="m9 14 3 3 3-3"/>',
  home: '<path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
  grid: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  chart: '<path d="M3 3v18h18"/><path d="M8 17v-5"/><path d="M13 17V8"/><path d="M18 17v-9"/>',
  sliders: '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.6 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.3 17.7-1.4 1.4"/><path d="m19.1 4.9-1.4 1.4"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  wall: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10"/><path d="M7 12h10"/><path d="M7 16h6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  video: '<path d="m16 13 5.2 3.1a.5.5 0 0 0 .8-.4V8.3a.5.5 0 0 0-.8-.4L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.8 9.8 0 0 1 6.7 2.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.8 9.8 0 0 1-6.7-2.7L3 16"/><path d="M8 16H3v5"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  play: '<path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.8l-12-7.5A1 1 0 0 0 7 4.5z"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  server: '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01"/><path d="M6 17h.01"/>',
  disk: '<path d="M22 12H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/><path d="M6 16h.01"/><path d="M10 16h.01"/>',
  archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17v4"/><path d="M17 19h4"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  copy: '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
  heart: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7z"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  code: '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
  wifi: '<path d="M12 20h.01"/><path d="M2 8.8a15 15 0 0 1 20 0"/><path d="M5 12.9a10 10 0 0 1 14 0"/><path d="M8.5 16.4a5 5 0 0 1 7 0"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.help}</svg>`;
function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll('[data-icon]')) { el.innerHTML = icon(el.dataset.icon === 'vk' ? 'logo' : el.dataset.icon); el.removeAttribute('data-icon'); }
}

// ── Сеть с программой ──
async function api(path, body) {
  const opts = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    // Не ответ с ошибкой, а нет ответа вовсе: программу закрыли или компьютер засыпал
    const err = new Error('Программа не отвечает: окно программы закрыто или компьютер засыпал');
    err.offline = true;
    throw err;
  }
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) throw new Error((data && data.detail) || `Ошибка ${r.status}`);
  return data;
}

// Уведомление внизу справа: ошибки — заметнее и висят дольше, у каждого есть «закрыть»
function toast(text, kind = 'ok') {
  let el = $('.toast');
  if (!el) { el = document.createElement('div'); document.body.appendChild(el); }
  el.className = `toast${kind === 'err' ? ' err' : ''}`;
  el.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  el.innerHTML = `<span>${esc(text)}</span><button type="button" class="toast-x" data-act="toast-close" aria-label="Закрыть уведомление">${icon('x')}</button>`;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.remove(), kind === 'err' ? 9000 : 4500);
}

// Запрос по кнопке: сообщение программы — уведомлением, потом свежий статус
async function act(path, body) {
  try {
    const res = await api(path, body);
    if (res && res.msg) toast(res.msg, res.ok === false ? 'err' : 'ok');
    dashAt = 0;
    await refresh();
    return res;
  } catch (e) {
    toast(e.message, 'err');
    return null;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    // Буфер обмена закрыт (старый браузер или нет разрешения) — по-старому, через выделение
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.className = 'offscreen';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    if (!ok) { toast('Не получилось скопировать — выделите путь и нажмите Ctrl+C', 'err'); return; }
  }
  toast('Скопировано');
}

// ── Кнопки: data-act="имя" → onAct('имя', обработчик) ──
// Пока обработчик работает, кнопка занята: второй щелчок не шлёт второй запрос. Занята —
// через aria-disabled, а не disabled: отключённая кнопка теряет фокус, и человек с клавиатурой
// после каждого нажатия оказывался бы в начале страницы
const ACTIONS = {};
const busyActs = new Set();
function onAct(name, fn) { ACTIONS[name] = fn; }

function setBusy(btn, on) {
  if (on) {
    btn.setAttribute('aria-busy', 'true');
    btn.setAttribute('aria-disabled', 'true');
  } else if (btn.hasAttribute('aria-busy')) {
    btn.removeAttribute('aria-busy');
    btn.removeAttribute('aria-disabled');
  }
}

// Перерисовать кусок страницы, вернув фокус туда же: на поле с тем же id или на ту же кнопку
function focusKey(el) {
  if (!el || el === document.body) return null;
  if (el.id) return `#${CSS.escape(el.id)}`;
  if (!el.dataset.act) return null;
  let key = `[data-act="${CSS.escape(el.dataset.act)}"]`;
  for (const attr of ['path', 'copy']) if (el.dataset[attr]) key += `[data-${attr}="${CSS.escape(el.dataset[attr])}"]`;
  return key;
}
function keepFocus(root, draw) {
  const active = document.activeElement;
  const key = active && root.contains(active) ? focusKey(active) : null;
  draw();
  if (!key) return;
  const again = root.querySelector(key);
  if (again && again !== document.activeElement) again.focus({preventScroll: true});
}
// Экран перерисовался, пока запрос ещё идёт: новая кнопка тоже должна быть занята
function markBusy(root) {
  for (const el of root.querySelectorAll('[data-act]')) if (busyActs.has(el.dataset.act)) setBusy(el, true);
}

async function runAction(btn, e) {
  const name = btn.dataset.act;
  const fn = ACTIONS[name];
  if (!fn) { console.error(`Нет обработчика для кнопки «${name}»`); return; }
  if (busyActs.has(name) || btn.getAttribute('aria-disabled') === 'true') return;
  busyActs.add(name);
  setBusy(btn, true);
  try {
    await fn(btn, e);
  } finally {
    busyActs.delete(name);
    for (const el of document.querySelectorAll(`[data-act="${name}"]`)) setBusy(el, false);
  }
}

// ── Сводка по файлам ──
function mediaTotals(r) {
  const t = {pending: 0, waiting: 0, done: 0, failed: 0, bytes: 0};
  for (const m of Object.values((r && r.media) || {})) for (const k in t) t[k] += m[k] || 0;
  t.all = t.pending + t.waiting + t.done + t.failed;
  return t;
}

function trackSpeed(job) {
  const now = Date.now() / 1000;
  if (job.state !== 'running' || job.step !== 'download') { speed.length = 0; return null; }
  const last = speed[speed.length - 1];
  if (last && job.downloaded_now < last[1]) speed.length = 0; // новый круг — счётчики с нуля
  speed.push([now, job.downloaded_now || 0, job.bytes_now || 0]);
  while (speed.length > 2 && now - speed[0][0] > 30) speed.shift();
  if (speed.length < 2) return null;
  const [t0, f0, b0] = speed[0];
  const dt = now - t0;
  return dt < 3 ? null : {files: (job.downloaded_now - f0) / dt, bytes: (job.bytes_now - b0) / dt};
}

function eta(seconds) {
  if (!isFinite(seconds) || seconds <= 0) return '';
  return seconds < 90 ? 'меньше 2 минут' : duration(seconds);
}

// Полоса из частей: [[класс, значение], …] — ширины через data-w, их ставит applySizes
function stackBar(parts, label) {
  const all = parts.reduce((a, [, v]) => a + (v || 0), 0);
  const segs = all ? parts.filter(([, v]) => v).map(([cls, v]) => `<span class="${cls}" data-w="${(v * 100 / all).toFixed(2)}"></span>`).join('') : '';
  return `<div class="mini" role="img" aria-label="${esc(label)}">${segs}</div>`;
}

// Ширина и высота полос — через CSSOM: атрибут style в разметке запрещён политикой безопасности страницы
function applySizes(root) {
  for (const el of root.querySelectorAll('[data-w]')) { el.style.width = `${el.dataset.w}%`; el.removeAttribute('data-w'); }
  for (const el of root.querySelectorAll('[data-h]')) { el.style.height = `${el.dataset.h}%`; el.removeAttribute('data-h'); }
}

onAct('toast-close', (btn) => { const t = btn.closest('.toast'); if (t) t.remove(); });
onAct('copy', (btn) => copyText(btn.dataset.copy || ''));
