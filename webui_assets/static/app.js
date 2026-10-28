// Бэкап ВКонтакте — страница программы. Без библиотек и без запросов куда-либо, кроме этой программы.
'use strict';

const VK_DATA_PAGE = 'https://vk.com/data_protection?section=rules&scroll_to_archive=1';
let state = null;
let security = null;
let insights = null;       // /api/stats: цифры и «В этот день»
let insightsKey = null;    // для какого архива они посчитаны
let form = null;           // черновик настроек, пока человек их правит
const speed = [];          // [время, скачано файлов, байт] — для скорости и «осталось ≈»
const search = {q: '', res: null, busy: false, timer: null};

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

// ── Иконки (контурные, 24×24) ──
const ICONS = {
  logo: '<path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8"/><rect x="1.5" y="3" width="21" height="5" rx="1.5"/><path d="M12 11v6"/><path d="m9 14 3 3 3-3"/>',
  home: '<path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
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
  server: '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01"/><path d="M6 17h.01"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17v4"/><path d="M17 19h4"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  copy: '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.help}</svg>`;
function hydrateIcons(root = document) {
  for (const el of root.querySelectorAll('[data-icon]')) { el.innerHTML = icon(el.dataset.icon === 'vk' ? 'logo' : el.dataset.icon); el.removeAttribute('data-icon'); }
}

// ── Сеть с программой ──
async function api(path, body) {
  const opts = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) throw new Error((data && data.detail) || `Ошибка ${r.status}`);
  return data;
}

function toast(text) {
  let el = $('.toast');
  if (!el) { el = document.createElement('div'); el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.textContent = text;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.remove(), 4500);
}

async function act(path, body) {
  try {
    const res = await api(path, body);
    if (res && res.msg) toast(res.msg);
    await refresh();
    return res;
  } catch (e) {
    toast(e.message);
    return null;
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
  if (seconds < 90) return 'меньше 2 минут';
  const m = Math.round(seconds / 60);
  if (m < 60) return plural(m, 'минута', 'минуты', 'минут');
  const h = Math.floor(m / 60);
  return `${plural(h, 'час', 'часа', 'часов')} ${m % 60 ? plural(m % 60, 'минута', 'минуты', 'минут') : ''}`.trim();
}

// ── Главная ──
function ring(t, spinning) {
  const C = 2 * Math.PI * 94;
  const arc = (cls, from, len) => (len > 0 ? `<circle class="${cls}" cx="100" cy="100" r="94" stroke-dasharray="${len} ${C}" stroke-dashoffset="${-from}"/>` : '');
  let arcs = '', center;
  if (spinning || !t.all) {
    arcs = `<circle class="arc-spin" cx="100" cy="100" r="94" stroke-dasharray="${C * 0.18} ${C}"/>`;
    center = `<div class="center"><span class="cap">разбираю<br>архив</span></div>`;
  } else {
    const d = C * t.done / t.all, w = C * t.waiting / t.all, f = C * t.failed / t.all;
    arcs = arc('arc-done', 0, d) + arc('arc-wait', d, w) + arc('arc-fail', d + w, f);
    const pct = Math.floor(t.done * 100 / t.all);
    center = `<div class="center"><span class="pct">${pct}<span class="pct-sign">%</span></span><span class="cap">файлов<br>сохранено</span></div>`;
  }
  return `<div class="ring" role="img" aria-label="Сохранено ${t.all ? Math.floor(t.done * 100 / t.all) : 0}% файлов"><svg viewBox="0 0 200 200"><circle class="track" cx="100" cy="100" r="94"/>${arcs}</svg>${center}</div>`;
}

function stat(cls, label, value, sub) {
  return `<div class="stat ${cls}"><div class="s-label"><span class="s-dot"></span>${label}</div><div class="s-value">${value}</div><div class="s-sub">${sub}</div></div>`;
}

function heroState(s, t, rate) {
  const job = s.job, r = s.result;
  const running = job.state === 'running' || job.state === 'stopping';
  const mins = job.started_at ? Math.max(1, Math.round((Date.now() / 1000 - job.started_at) / 60)) : 0;
  const nextAt = job.next_retry ? clock(job.next_retry) : '';
  const start = r ? (job.state === 'stopped' ? 'Продолжить' : 'Сохранить ещё раз') : 'Сохранить мой ВК';
  const openBtn = r && r.index ? `<a class="btn" href="/archive/index.html" target="_blank" rel="noopener">${icon('external')}Открыть архив</a>` : '';
  const stopBtn = `<button class="btn" data-act="stop" ${job.state === 'stopping' ? 'disabled' : ''}>${icon('stop')}Остановить</button>`;
  const startBtn = `<button class="btn big primary" data-act="start">${icon('play')}${start}</button>`;
  if (job.state === 'stopping') return {pill: ['wait', 'Останавливаю'], title: 'Останавливаю', sub: 'Дописываю то, что уже скачивается. Скачанное сохранится.', actions: stopBtn};
  if (running && job.step === 'waiting') {
    return {
      pill: ['wait', `Ждём ВК · повтор в ${nextAt}`],
      title: 'Всё, что ВК отдаёт сейчас, уже скачано',
      sub: `Ждут серверов ВК: ${plural(t.waiting, 'файл', 'файла', 'файлов')}. Следующая попытка в ${nextAt}. Архив уже можно открыть — докачанное добавится в него само. Только не закрывайте окно программы.`,
      actions: `<button class="btn big primary" data-act="retry-now">${icon('refresh')}Попробовать сейчас</button>${openBtn}${stopBtn}`,
    };
  }
  if (running && job.step === 'import') return {pill: ['live', `Разбираю архив · ${mins} мин`], title: 'Разбираю архив ВК', sub: esc(job.text || 'Читаю переписки, фото и стену из архива…'), actions: stopBtn, spinning: true};
  if (running && job.step === 'render') return {pill: ['live', 'Собираю страницы'], title: 'Собираю страницы архива', sub: 'Переписки как в Telegram, фото по альбомам, стена, друзья — ещё немного.', actions: stopBtn};
  if (running) {
    const left = rate && rate.files > 0 ? `, осталось ≈ ${eta(t.pending / rate.files)}` : '';
    return {
      pill: ['live', `Идёт скачивание · ${mins} мин`],
      title: 'Скачиваем ваши фото и голосовые',
      sub: `Ничего делать не нужно: программа сама скачивает файлы по ссылкам из архива${left}. Если ВК какие-то файлы не отдаст — повторит их сама.`,
      actions: stopBtn,
    };
  }
  if (job.state === 'error') return {pill: ['err', 'Ошибка'], title: 'Что-то пошло не так', sub: esc(job.problem_text), actions: startBtn + openBtn, art: 'alert'};
  if (job.state === 'stopped') return {pill: ['', 'Остановлено'], title: 'Остановлено', sub: 'Скачанное сохранено. Нажмите «Продолжить» — уже скачанное второй раз не качается.', actions: startBtn + openBtn};
  if (r && r.index) {
    const lost = t.failed ? ` Не скачались ${plural(t.failed, 'файл', 'файла', 'файлов')}: ссылки в архиве устарели — помогает свежий архив.` : '';
    return {
      pill: ['ok', job.state === 'done' ? 'Готово' : 'Архив сохранён'],
      title: t.failed ? 'Архив готов' : 'Всё сохранено',
      sub: `${plural(r.messages, 'сообщение', 'сообщения', 'сообщений')}, ${plural(r.photos, 'фото', 'фото', 'фото')}, ${plural(r.friends, 'друг', 'друга', 'друзей')} — на вашем компьютере и открываются без интернета.${lost}`,
      actions: `<a class="btn big primary" href="/archive/index.html" target="_blank" rel="noopener">${icon('external')}Открыть архив</a><button class="btn" data-act="open-folder">${icon('folder')}Открыть папку</button><button class="btn ghost" data-act="start">${icon('refresh')}${start}</button>`,
      art: t.all ? null : 'ok',
    };
  }
  return {pill: ['', 'Готово к запуску'], title: 'Всё готово к запуску', sub: `Архив: <code>${esc(s.settings.archive)}</code>. Нажмите кнопку — программа разберёт его и скачает фото и голосовые.`, actions: startBtn, art: 'logo'};
}

function onboarding() {
  return `<div class="card hero"><div class="hero-top"><span class="pill"><span class="pdot"></span>Начало</span>
      <span class="heartbeat">${icon('shield')}Без пароля и доступа к аккаунту</span></div>
    <div class="hero-body"><div class="hero-art">${icon('logo')}</div><div>
      <h1>Сохраните свой ВКонтакте на компьютер</h1>
      <p class="sub">Переписки с фото и голосовыми, альбомы, стена, друзья и музыка — в одной папке, открываются без интернета.
        Работает с официальным архивом, который ВК сам выдаёт по запросу: программе не нужен ни пароль, ни доступ к аккаунту.</p>
      <div class="row actions"><a class="btn big primary" href="#/setup">${icon('play')}Начать — 3 шага</a>
        <a class="btn" href="${VK_DATA_PAGE}" target="_blank" rel="noreferrer noopener">${icon('external')}Заказать архив у ВК</a></div>
    </div></div>
    <ol class="how">
      <li><span class="n">1</span><div><b>Закажите архив</b>ВК готовит его от нескольких часов до пары дней и пришлёт сообщение</div></li>
      <li><span class="n">2</span><div><b>Укажите ZIP-файл</b>Программа сама найдёт его в «Загрузках»</div></li>
      <li><span class="n">3</span><div><b>Нажмите «Сохранить»</b>Дальше всё сама: разберёт, скачает фото, соберёт страницы</div></li>
    </ol></div>`;
}

const SECTIONS_UI = {
  messages: {icon: 'chat', value: (r) => r.messages, unit: ['сообщение', 'сообщения', 'сообщений'], sub: (r) => `в ${plural(r.chats, 'беседе', 'беседах', 'беседах')}`},
  photos: {icon: 'image', value: (r) => r.photos, unit: ['фото', 'фото', 'фото'], sub: () => 'в альбомах'},
  wall: {icon: 'wall', value: (r) => r.posts, unit: ['запись', 'записи', 'записей'], sub: () => 'на стене, с комментариями'},
  friends: {icon: 'users', value: (r) => r.friends, unit: ['друг', 'друга', 'друзей'], sub: () => 'таблица для Excel и текст'},
  music: {icon: 'music', value: (r) => r.tracks, unit: ['трек', 'трека', 'треков'], sub: () => 'список для переноса'},
  videos: {icon: 'video', value: (r) => r.videos, unit: ['видео', 'видео', 'видео'], sub: () => 'ссылками и обложками'},
  docs: {icon: 'file', value: (r) => r.docs, unit: ['файл', 'файла', 'файлов'], sub: () => 'документы'},
};

function sectionCards(s) {
  const r = s.result;
  const cards = [];
  if (r.messages && r.stats_page) {
    cards.push(`<a class="sec promo" href="#/stats"><div class="sec-top"><span class="sec-ico">${icon('sparkles')}</span>
      <div><div class="sec-title">Мой ВК в цифрах</div><div class="sec-sub">годы, собеседники, часы</div></div></div>
      <div class="sec-num">${esc(insights && insights.years ? plural(insights.years.length, 'год', 'года', 'лет') : '★')}</div>
      <div class="sec-foot">Посмотреть статистику →</div></a>`);
  }
  for (const x of s.sections) {
    const ui = SECTIONS_UI[x.key];
    if (!ui) continue;
    const n = ui.value(r) || 0;
    const m = (r.media || {})[x.key];
    let mini = '', foot = '';
    if (m) {
      const all = (m.pending || 0) + (m.waiting || 0) + (m.done || 0) + (m.failed || 0);
      const w = (v) => (all ? (v * 100 / all).toFixed(2) : 0);
      mini = `<div class="mini" aria-hidden="true">${m.done ? `<span data-w="${w(m.done)}"></span>` : ''}${m.waiting ? `<span class="w" data-w="${w(m.waiting)}"></span>` : ''}${m.failed ? `<span class="f" data-w="${w(m.failed)}"></span>` : ''}</div>`;
      foot = `файлов скачано ${num(m.done)} из ${num(all)}${m.waiting ? ` · ждут ВК ${num(m.waiting)}` : ''}`;
    }
    const inner = `<div class="sec-top"><span class="sec-ico">${icon(ui.icon)}</span><div><div class="sec-title">${esc(x.title)}</div>
      <div class="sec-sub">${esc(ui.sub(r))}</div></div></div>
      <div class="sec-num">${num(n)}<small>${word(n, ...ui.unit)}</small></div>${mini}${foot ? `<div class="sec-foot">${esc(foot)}</div>` : ''}`;
    cards.push(n && r.index ? `<a class="sec" href="${archiveUrl(x.key + '/index.html')}" target="_blank" rel="noopener">${inner}</a>`
      : `<div class="sec${n ? '' : ' off'}">${inner}</div>`);
  }
  return `<div><div class="page-head"><h2>Что в архиве</h2><span class="tiny">Карточка открывает раздел архива в новой вкладке</span></div>
    <div class="sec-grid mt-12">${cards.join('')}</div></div>`;
}

function onThisDay() {
  const o = insights && insights.on_this_day;
  if (!o || (!o.messages.length && !o.photos.length)) return '';
  const items = o.messages.map((m) => {
    const year = new Date(m.date * 1000).getFullYear();
    const text = m.text.length > 220 ? m.text.slice(0, 220) + '…' : m.text;
    const inner = `<div class="yr">${year}<small>${plural(new Date().getFullYear() - year, 'год', 'года', 'лет')} назад</small></div>
      <div><div class="tiny">${esc(whoWhere(m))} · ${clock(m.date)}${m.that_day > 1 ? ` · ${plural(m.that_day, 'сообщение', 'сообщения', 'сообщений')} в тот день` : ''}</div>
      <div class="q">${esc(text)}</div></div>`;
    return m.page ? `<a class="otd" href="${archiveUrl(m.page)}" target="_blank" rel="noopener">${inner}</a>` : `<div class="otd">${inner}</div>`;
  }).join('');
  const photos = o.photos.length ? `<div class="thumbs">${o.photos.map((p) => `<a href="${archiveUrl(p.file)}" target="_blank" rel="noopener">
    <img src="${archiveUrl(p.file)}" alt="" loading="lazy"><span>${new Date(p.date * 1000).getFullYear()}</span></a>`).join('')}</div>` : '';
  return `<div class="card"><div class="card-head"><span class="sec-ico">${icon('calendar')}</span><div class="grow"><h2>В этот день, ${esc(o.day)}</h2>
    <div class="tiny">Что вы писали в этот день в прошлые годы</div></div></div><div class="otd-list">${items}</div>${photos}</div>`;
}

function renderHome() {
  const s = state;
  const r = s.result;
  if (!s.settings.archive && !r) { $('#screen-home').innerHTML = `<div class="stack">${onboarding()}</div>`; return; }
  const job = s.job;
  const t = mediaTotals(r);
  const rate = trackSpeed(job);
  const h = heroState(s, t, rate);
  const visual = h.art ? `<div class="hero-art ${h.art === 'ok' ? 'ok' : ''}">${h.art === 'ok' ? `<span>${icon('check')}</span>` : icon(h.art)}</div>` : ring(t, h.spinning);
  const beat = rate && rate.bytes > 0 ? `${icon('activity')}${bytes(rate.bytes)}/с · ${num(Math.round(rate.files * 60))} файлов в минуту`
    : `${icon('shield')}Сетевой замок · только файлы ВК`;
  let stats = '';
  if (t.all) {
    const left = rate && rate.files > 0 ? `осталось ≈ ${eta(t.pending / rate.files)}` : (t.pending ? 'в очереди на скачивание' : 'очередь пуста');
    stats = `<div class="stats">
      ${stat('ok', 'Скачано', num(t.done), `${bytes(t.bytes)} · из ${plural(t.all, 'файла', 'файлов', 'файлов')}`)}
      ${stat('wait', 'Ждут ВК', num(t.waiting), t.waiting ? (job.next_retry ? `повтор в ${clock(job.next_retry)}` : 'программа повторит сама') : 'серверы ВК отвечают')}
      ${stat('run', 'В очереди', num(t.pending), left)}
      ${stat('err', 'Не скачались', num(t.failed), t.failed ? 'ссылка устарела — нужен свежий архив' : 'всё в порядке')}</div>`;
  } else if (r) {
    stats = `<div class="stats">${stat('ok', 'Сообщений', num(r.messages), `в ${plural(r.chats, 'беседе', 'беседах', 'беседах')}`)}
      ${stat('', 'Фото', num(r.photos), 'в альбомах')}${stat('', 'Друзей', num(r.friends), 'со ссылками')}${stat('', 'Записей', num(r.posts), 'на стене')}</div>`;
  }
  const what = s.sections.filter((x) => s.settings.sections.includes(x.key)).map((x) => x.title).join(', ');
  const hero = `<div class="card hero"><div class="hero-top"><span class="pill ${h.pill[0]}"><span class="pdot"></span>${esc(h.pill[1])}</span>
      <span class="heartbeat">${beat}</span></div>
    <div class="hero-body">${visual}<div><h1>${esc(h.title)}</h1><p class="sub">${h.sub}</p><div class="row actions">${h.actions}</div></div></div>
    ${stats}
    <div class="hero-what">Что сохраняем: ${esc(what || 'ничего')}${s.settings.download ? ' — с фото и голосовыми' : ' — только текст, без сети'} · <a href="#/setup">изменить</a></div></div>`;
  let banner = '';
  if (t.waiting) {
    const rounds = (job.rounds || []).slice().reverse().map((x) => `<span>${clock(x.time)} — из ${plural(x.tried, 'файла', 'файлов', 'файлов')}, ждавших ВК, скачано ${num(x.got)}</span>`).join('');
    banner = `<div class="banner"><span class="b-icon">${icon('server')}</span><div><h3>Часть файлов лежит на серверах ВК, которые сейчас не отвечают</h3>
      <p>Они не потеряны: программа пробует их снова каждые 10 минут, пока открыта. Не удаляйте страницу ВК, пока всё не скачается.
      Если файл долго не скачивается — закажите свежий архив и укажите его в «Настройке»: ссылки в нём новые.</p>
      ${rounds ? `<div class="rounds">${rounds}</div>` : ''}</div></div>`;
  }
  const problem = job.problem ? `<div class="card err">${esc(job.problem_text)}</div>` : '';
  let failed = '';
  if (r && (r.failed || []).length) {
    const rows = r.failed.map((f) => `<tr><td><code>${esc(f.path)}</code></td><td>${esc(f.error)}</td></tr>`).join('');
    failed = `<div class="card"><details data-key="failed"><summary>Какие файлы не скачались (${num(t.failed)})</summary><div>
      <p class="tiny">Чаще всего ссылка из архива устарела: ВК подписывает ссылки на файлы, и они живут не вечно.
      Закажите свежий архив, укажите его в «Настройке» и нажмите «Сохранить ещё раз»: скачанное второй раз не качается,
      а ссылки возьмутся новые.</p><table class="t">${rows}</table>
      <div class="row mt-10"><button class="btn small" data-act="retry" ${job.state === 'running' ? 'disabled' : ''}>${icon('refresh')}Попробовать их ещё раз</button></div></div></details></div>`;
  }
  const safety = r && r.index ? `<div class="banner info"><span class="b-icon">${icon('copy')}</span><div><h3>Прежде чем удалять страницу ВК</h3>
    <p>Откройте архив и пролистайте важные переписки. Скопируйте папку <code>${esc(s.settings.folder)}</code> на второй диск или флешку —
    одна копия на одном диске ненадёжна.</p></div></div>` : '';
  $('#screen-home').innerHTML = `<div class="stack">${hero}${problem}${banner}${r && r.index ? onThisDay() : ''}${r ? sectionCards(s) : ''}${failed}${safety}</div>`;
}

// ── Настройка ──
function stepCard(n, done, title, body) {
  return `<div class="card"><div class="step${done ? ' done' : ''}"><span class="step-num">${done ? '✓' : n}</span>
    <div class="step-body"><h2>${title}</h2>${body}</div></div></div>`;
}

function renderSetup() {
  const s = state;
  const set = form || s.settings;
  const running = s.job.state === 'running' || s.job.state === 'stopping';
  const dis = running ? 'disabled' : '';
  const hasArchive = !!s.settings.archive;
  const step1 = stepCard(1, hasArchive, 'Закажите архив у ВКонтакте', `
    <p class="muted">ВК сам выгружает все ваши данные: переписки с 2006 года, фото, друзей, стену, список музыки.
    Программе не нужны ни пароль, ни доступ к аккаунту — только этот архив.</p>
    <ol class="steps steps-gap">
      <li>Откройте страницу ВК «Защита данных» — кнопка ниже, она откроется в вашем браузере.</li>
      <li>Нажмите «Загрузить архив» (или «Запросить архив»), отметьте <b>все</b> разделы и подтвердите паролем.</li>
      <li>Дождитесь сообщения от ВК, что архив готов (от нескольких часов до пары дней), и скачайте ZIP-файл. Ссылки на фото в архиве со временем устаревают — запускайте программу сразу.</li>
    </ol>
    <a class="btn" href="${VK_DATA_PAGE}" target="_blank" rel="noreferrer noopener">${icon('external')}Открыть «Защиту данных» ВК</a>
    <p class="tiny mt-8">Ссылка открывается в вашем браузере. Сама программа к сайту ВК не обращается.</p>`);
  const checks = s.sections.map((x) => `<label class="check"><input type="checkbox" name="sec" value="${x.key}"
      ${set.sections.includes(x.key) ? 'checked' : ''} ${dis}> ${esc(x.title)}</label>`).join('');
  const step2 = stepCard(2, hasArchive, 'Укажите архив и папку для результата', `
    <label class="field"><span>Архив ВК — ZIP-файл или папка, куда вы его распаковали</span>
      <input type="text" id="f-archive" value="${esc(set.archive)}" placeholder="C:\\Users\\…\\Downloads\\Archive.zip" ${dis}></label>
    <div class="row"><button class="btn small" data-act="find" ${dis}>${icon('search')}Найти в «Загрузках»</button><span class="tiny" id="found"></span></div>
    <label class="field"><span>Куда сохранить архив с фото и страницами</span>
      <input type="text" id="f-folder" value="${esc(set.folder)}" ${dis}></label>
    <div class="field"><span>Что сохранить</span><div class="checks">${checks}</div></div>
    <label class="check"><input type="checkbox" id="f-download" ${set.download ? 'checked' : ''} ${dis}>
      Скачать фото, голосовые и файлы по ссылкам из архива</label>
    <p class="tiny under-check">В архиве ВК фото и голосовые — ссылками. Без этой галочки программа
      не выходит в интернет вообще и делает страницы только из текста.</p>`);
  const step3 = stepCard(3, !!s.result, 'Сохраните', `
    <p class="muted">Программа разберёт архив, скачает файлы и соберёт страницы, которые откроются в любом браузере без интернета.</p>
    <div class="row mt-14">
      <button class="btn big primary" data-act="save-start" ${dis}>${icon('play')}Сохранить настройки и начать</button>
      <button class="btn" data-act="save" ${dis}>Только сохранить</button></div>
    ${running ? '<p class="tiny mt-8">Бэкап идёт — настройки можно поменять после остановки.</p>' : ''}`);
  $('#screen-setup').innerHTML = `<div class="stack"><div><h1>Настройка</h1>
    <p class="muted">Три шага. Всё хранится только на этом компьютере, в файле <code>settings.json</code> рядом с программой.</p></div>
    ${step1}${step2}${step3}</div>`;
}

function readForm() {
  const archive = $('#f-archive'); const folder = $('#f-folder'); const download = $('#f-download');
  if (!archive) return null;
  return {
    archive: archive.value, folder: folder.value, download: download.checked,
    sections: [...document.querySelectorAll('input[name=sec]:checked')].map((x) => x.value),
  };
}

// ── Поиск ──
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
  if (!res) { box.innerHTML = `<div class="empty">${icon('search')}Ищет по тексту всех сообщений архива — без интернета.<br>Например: имя, адрес, «пароль от wi-fi», «день рождения».</div>`; return; }
  if (!res.hits.length) { box.innerHTML = `<div class="empty">${icon('search')}Ничего не нашлось по запросу «${esc(res.query)}»</div>`; return; }
  const rows = res.hits.map((m) => {
    const who = m.out ? 'Вы' : (m.from || m.chat);
    const inner = `${avatar(m.chat, m.peer_id)}<div><div class="who">${esc(m.chat)}</div>
      <div class="q">${m.peer_id >= CHAT_OFFSET || m.out ? `<span class="tiny">${esc(who)}:</span> ` : ''} ${m.text ? highlight(m.text, res.query) : '<span class="tiny">вложение</span>'}</div></div>
      <div class="when">${esc(day(m.date))}<br>${clock(m.date)}</div>`;
    return m.page ? `<a class="hit" href="${archiveUrl(m.page)}" target="_blank" rel="noopener" title="Открыть переписку на этом сообщении">${inner}</a>` : `<div class="hit">${inner}</div>`;
  }).join('');
  box.innerHTML = `<p class="tiny mb-10">${res.more ? `Показаны ${num(res.hits.length)} самых новых — уточните запрос, чтобы увидеть остальные` : `Найдено: ${plural(res.hits.length, 'сообщение', 'сообщения', 'сообщений')}`}. Нажмите на сообщение — откроется переписка на этом месте.</p>
    <div class="hits">${rows}</div>`;
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
    <div class="search-box">${icon('search')}<input type="search" id="q" placeholder="Что найти? Например: адрес, имя, номер" value="${esc(search.q)}" autocomplete="off" aria-label="Что найти"></div>
    <div id="search-results"></div></div>`;
  renderSearchResults();
  setTimeout(() => { const q = $('#q'); if (q) q.focus(); }, 0);
}

async function runSearch() {
  const q = search.q.trim();
  if (q.length < 2) { search.res = null; renderSearchResults(); return; }
  try {
    const res = await api(`/api/search?q=${encodeURIComponent(q)}`);
    if (search.q.trim() === q) { search.res = res; renderSearchResults(); }
  } catch (e) { toast(e.message); }
}

// ── ВК в цифрах ──
function cols(values, labels, tips, second) {
  const peak = Math.max(1, ...values.map((v, i) => v + (second ? second[i] : 0)));
  return `<div class="cols">${values.map((v, i) => {
    const b = second ? second[i] : null;
    const segs = (b !== null ? `<span class="b" data-h="${(b * 100 / peak).toFixed(2)}"></span>` : '') + `<span data-h="${(v * 100 / peak).toFixed(2)}"></span>`;
    return `<div class="col" data-tip="${esc(tips[i])}">${segs}<em>${esc(labels[i])}</em></div>`;
  }).join('')}</div>`;
}

function bars(rows, peak) {
  return `<div class="bars">${rows.map(([label, v, tip]) => `<div class="bar" data-tip="${esc(tip || `${label}: ${num(v)}`)}"><span class="lbl">${esc(label)}</span>
    <span class="trk"><span data-w="${(v * 100 / (peak || 1)).toFixed(2)}"></span></span><span class="val">${num(v)}</span></div>`).join('')}</div>`;
}

const KIND_WORDS = {photo: ['фото', 'фото', 'фото'], voice: ['голосовое', 'голосовых', 'голосовых'], sticker: ['стикер', 'стикера', 'стикеров'],
  video: ['видео', 'видео', 'видео'], file: ['файл', 'файла', 'файлов'], call: ['звонок', 'звонка', 'звонков'], gift: ['подарок', 'подарка', 'подарков'],
  audio: ['песня', 'песни', 'песен'], link: ['ссылка', 'ссылки', 'ссылок'], wall: ['запись со стены', 'записи со стены', 'записей со стены']};
const CHRONO = {night: ['Сова', 'чаще всего вы пишете ночью'], morning: ['Жаворонок', 'утром вы пишете больше, чем ночью'], day: ['Дневной человек', 'больше всего сообщений — днём и вечером']};
const WEEKDAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

function renderStats() {
  const el = $('#screen-stats');
  const r = state.result;
  if (!r || !r.messages) {
    el.innerHTML = `<div class="stack"><div><h1>Мой ВКонтакте в цифрах</h1></div><div class="card empty">${icon('chart')}Статистика появится, когда архив с перепиской будет сохранён.<br><a href="#/home">На главную</a></div></div>`;
    return;
  }
  const s = insights;
  if (!s) { el.innerHTML = `<div class="stack"><div><h1>Мой ВКонтакте в цифрах</h1><p class="muted">Считаю…</p></div></div>`; loadInsights(); return; }
  const years = s.years || [];
  const span = years.length ? (years.length > 1 ? `${years[0].year}–${years[years.length - 1].year}` : `${years[0].year}`) : '';
  const pages = Math.floor((s.chars || 0) / 1800);
  const tiles = `<div class="tiles">
    <div class="tile hero-tile"><b>${num(s.messages)}</b><span>${word(s.messages, 'сообщение', 'сообщения', 'сообщений')} за ${span}</span></div>
    <div class="tile"><b>${num(s.sent)}</b><span>написали вы · ${s.messages ? Math.round(s.sent * 100 / s.messages) : 0}%</span></div>
    <div class="tile"><b>${num(s.words)}</b><span>${word(s.words, 'слово', 'слова', 'слов')} от вас — ${plural(pages, 'страница', 'страницы', 'страниц')} книги</span></div>
    <div class="tile"><b>${num(years.length)}</b><span>${word(years.length, 'год', 'года', 'лет')} переписки${s.registered ? ` · в ВК с ${esc(s.registered)}` : ''}</span></div></div>`;
  const best = years.reduce((a, y) => (!a || y.total > a.total ? y : a), null);
  const yearsCard = `<div class="card"><div class="card-head"><div class="grow"><h2>Переписка по годам</h2>
    <div class="tiny">${best ? `Самый разговорчивый год — ${best.year}: ${plural(best.total, 'сообщение', 'сообщения', 'сообщений')}` : ''}</div></div></div>
    <div class="legend"><span><i></i>вы</span><span><i class="b"></i>собеседники</span></div>
    ${cols(years.map((y) => y.sent), years.map((y, i) => (years.length > 12 && i % 2 ? '' : String(y.year))),
      years.map((y) => `${y.year}: ${num(y.total)} — вы ${num(y.sent)}, собеседники ${num(y.total - y.sent)}`), years.map((y) => y.total - y.sent))}</div>`;
  const top = (s.people[0] || {}).count || 1;
  const people = s.people.map((p, i) => {
    const w = (v) => (v * 100 / top).toFixed(2);
    const inner = `<span class="rank">${i + 1}</span>${avatar(p.title, p.peer_id)}<div class="min0"><div class="name">${esc(p.title)}</div>
      <div class="trk" data-tip="${esc(`вы — ${num(p.sent)}, ${p.title} — ${num(p.count - p.sent)}`)}"><span data-w="${w(p.sent)}"></span><span class="b" data-w="${w(p.count - p.sent)}"></span></div></div>
      <div class="cnt">${num(p.count)}<small>${p.first ? `с ${new Date(p.first * 1000).getFullYear()}` : ''}</small></div>`;
    return p.dir ? `<a class="person" href="${archiveUrl(p.dir + '/messages.html')}" target="_blank" rel="noopener">${inner}</a>` : `<div class="person">${inner}</div>`;
  }).join('');
  const peopleCard = people ? `<div class="card"><div class="card-head"><div class="grow"><h2>Главные собеседники</h2><div class="tiny">Нажмите — откроется переписка</div></div></div>
    <div class="legend"><span><i></i>вы</span><span><i class="b"></i>собеседник</span></div><div class="people">${people}</div></div>` : '';
  const hours = s.hours || [];
  const peakHour = hours.indexOf(Math.max(...hours));
  const [chrono, chronoText] = CHRONO[s.chronotype] || CHRONO.day;
  const hoursCard = `<div class="card"><div class="card-head"><div class="grow"><h2>Когда вы пишете</h2>
    <div class="tiny">${esc(chronoText)}. Самый активный час — ${String(peakHour).padStart(2, '0')}:00</div></div><span class="badge">${esc(chrono)}</span></div>
    ${cols(hours, hours.map((_, i) => (i % 3 ? '' : String(i).padStart(2, '0'))), hours.map((v, i) => `${String(i).padStart(2, '0')}:00–${String(i).padStart(2, '0')}:59 — ${plural(v, 'сообщение', 'сообщения', 'сообщений')}`))}</div>`;
  const wd = s.weekdays || [];
  const wdCard = `<div class="card"><h2>Дни недели</h2>${bars(WEEKDAYS.map((d, i) => [d, wd[i]]), Math.max(...wd))}</div>`;
  const fm = s.first_message;
  const firstCard = fm ? `<div class="card"><h2>Самое первое сообщение в архиве</h2><div class="tiny">${esc(day(fm.date))} · ${esc(fm.out ? 'вы' : (fm.from || fm.chat))} · «${esc(fm.chat)}»</div>
    <div class="quote">${esc(fm.text.slice(0, 400))}</div>${fm.page ? `<div class="row mt-12"><a class="btn small" href="${archiveUrl(fm.page)}" target="_blank" rel="noopener">${icon('external')}Открыть переписку</a></div>` : ''}</div>` : '';
  let busyCard = '';
  if (s.busiest) {
    const [y, m, d] = s.busiest.day.split('-').map(Number);
    busyCard = `<div class="card"><h2>Самый разговорчивый день</h2><div class="big-fact">${d} ${MONTHS[m - 1]} ${y}</div>
      <div class="tiny">${plural(s.busiest.count, 'сообщение', 'сообщения', 'сообщений')} за один день</div></div>`;
  }
  const kinds = Object.entries(KIND_WORDS).filter(([k]) => s.kinds[k]).map(([k, w]) => `<div class="kind"><b>${num(s.kinds[k])}</b><span>${word(s.kinds[k], ...w)}</span></div>`).join('');
  const kindsCard = kinds ? `<div class="card"><h2>Что ещё было в переписках</h2><div class="kinds mt-10">${kinds}</div></div>` : '';
  const yearBars = (rows, title) => (rows && rows.length ? `<div class="card"><h2>${title}</h2>${bars(rows.map((x) => [String(x.year), x.count]), Math.max(...rows.map((x) => x.count)))}</div>` : '');
  const groups = (s.groups || []).length ? `<div class="card"><h2>Самые живые беседы</h2>${bars(s.groups.map((g) => [g.title, g.count, `${g.title}: ${num(g.count)}, из них ваших ${num(g.sent)}`]), s.groups[0].count)}</div>` : '';
  el.innerHTML = `<div class="stack">
    <div class="page-head"><div><h1>Мой ВКонтакте в цифрах</h1><p class="muted">Посчитано по вашему архиву на этом компьютере — никуда не отправляется.</p></div>
      ${r.stats_page ? `<a class="btn" href="/archive/stats/index.html" target="_blank" rel="noopener">${icon('external')}Страница в архиве</a>` : ''}</div>
    ${tiles}${yearsCard}<div class="grid-2">${peopleCard}<div class="stack">${hoursCard}${wdCard}</div></div>
    <div class="facts">${firstCard}${busyCard}</div>${kindsCard}${groups}
    <div class="grid-2">${yearBars(s.friends_by_year, 'Новые друзья по годам')}${yearBars(s.photos_by_year, 'Фото в альбомах по годам')}</div></div>`;
}

async function loadInsights() {
  const r = state && state.result;
  if (!r || !r.messages) return;
  const key = JSON.stringify([state.settings.folder, r.messages, r.friends, r.photos, mediaTotals(r).done]);
  if (key === insightsKey || loadInsights.busy) return;
  loadInsights.busy = true;
  try {
    insights = await api('/api/stats');
    insightsKey = key;
    render.sig = null;
    render();
  } catch (e) { /* архива ещё нет — попробуем при следующем обновлении */ } finally { loadInsights.busy = false; }
}

// ── Безопасность ──
function renderSecurity() {
  const net = (security && security.network) || state.network;
  const hosts = (net.hosts || []).map(([h, n]) => `<tr><td><code>${esc(h)}</code></td><td class="num">${num(n)}</td></tr>`).join('');
  const blocked = (net.blocked || []).map((b) => `<tr><td>${esc(b.time)}</td><td>${esc(b.what)}</td><td><code>${esc(b.target)}</code></td></tr>`).join('');
  const code = ((security && security.code) || []).map((c) => `<tr><td><code>${esc(c.path)}</code></td><td><code>${esc(c.sha256)}</code></td></tr>`).join('');
  $('#screen-security').innerHTML = `<div class="stack">
    <div><h1>Безопасность</h1><p class="muted">Как программа обращается с вашими данными — и как проверить это самому, не веря на слово.</p></div>

    <div class="card"><div class="card-head"><span class="sec-ico">${icon('shield')}</span><h2>${net.installed ? 'Сетевой замок включён' : 'Сетевой замок не включён!'}</h2></div>
      <p>Программа может соединиться только с этими серверами ВК, на которых лежат файлы из архива:
      ${net.allowed_domains.map((d) => `<code>*.${esc(d)}</code>`).join(' ')}. Ни сайта vk.com, ни API ВК, ни входа
      в аккаунт в списке нет. Любое другое соединение замок обрывает до того, как оно начнётся, и записывает попытку в журнал.</p>
      <p class="tiny">Журнал всех соединений: <code>${esc(net.log_file || 'logs/network.log')}</code></p></div>

    <div class="card"><h2>С кем программа говорила с момента запуска</h2>
      ${hosts ? `<table class="t"><tr><th>Сервер</th><th>Запросов</th></tr>${hosts}</table>` : '<p class="muted">Ни с кем — ещё ничего не скачивалось.</p>'}
      <h3 class="mt-14">Что замок не пустил</h3>
      ${blocked ? `<table class="t">${blocked}</table>` : '<p class="muted">Ничего. Программа не пыталась соединиться ни с кем лишним.</p>'}</div>

    <div class="card"><h2>Что программа делает и чего не делает</h2>
      <ul class="steps list-steps">
        <li>Не спрашивает пароль и не получает доступ к аккаунту ВК: работает только с архивом, который вы сами скачали.</li>
        <li>Не отправляет ваши данные никуда: ни на свои серверы (их нет), ни в аналитику, ни «проверять обновления».</li>
        <li>Поиск и «ВК в цифрах» считаются по базе на этом компьютере — без интернета.</li>
        <li>Скачивает только файлы по прямым ссылкам из вашего архива — и только с файловых серверов ВК.</li>
        <li>Эта страница доступна только с этого компьютера (<code>127.0.0.1</code>): чужие сайты не могут ни управлять ею, ни заглянуть в архив.</li>
        <li>Готовые страницы архива не загружают ничего из интернета и не содержат скриптов — это запрещено им политикой безопасности браузера.</li>
      </ul></div>

    <div class="card"><h2>Проверьте сами — без веры на слово</h2>
      <ol class="steps">
        <li><b>Посмотрите на соединения со стороны Windows.</b> Пока идёт скачивание, откройте «Монитор ресурсов» (Win+R → <code>resmon</code>) → «Сеть» → «Сетевая активность»
          и найдите <code>python.exe</code>. Или бесплатный TCPView от Microsoft. Все адреса должны принадлежать ВК (<code>userapi.com</code>, <code>okcdn.ru</code>).</li>
        <li><b>Запустите без интернета.</b> Снимите галочку «Скачать фото…» или отключите Wi-Fi: переписки, друзья, стена и музыка всё равно сохранятся — им сеть не нужна.</li>
        <li><b>Прочитайте код.</b> Весь сетевой код — два файла: <code>vkbackup/firewall.py</code> (замок) и <code>vkbackup/net.py</code> (скачивание). Остальное с сетью не работает — это проверяет тест <code>tests/test_audit.py</code>.</li>
        <li><b>Дайте код проверить ИИ или знакомому программисту.</b> Программа маленькая: попросите найти в ней любую передачу данных, кроме скачивания файлов из архива.</li>
        <li><b>Сверьте отпечатки файлов</b> (ниже) с файлами в репозитории на GitHub: совпадают — значит, у вас тот же код, что опубликован.</li>
      </ol>
      <details class="mt-10"><summary>Отпечатки файлов программы (SHA-256)</summary><div><table class="t">${code}</table></div></details></div>
  </div>`;
}

// ── Помощь ──
function renderHelp() {
  const faq = [
    ['Почему архив, а не вход через ВК?', 'С сентября 2026 года ВК закрыл сторонним программам доступ к личным сообщениям (так перестал работать Kate Mobile). Официальный архив — единственный надёжный способ получить всю переписку. И он безопаснее: программе не нужен ни пароль, ни ключ доступа к аккаунту.'],
    ['Часть файлов «ждут ВК». Они пропали?', 'Нет. Серверы ВК, где лежат эти фото и голосовые, сейчас не отвечают — так было, например, после сбоя 18 октября 2026 года. Программа скачивает всё, что ВК отдаёт, а остальное пробует снова каждые 10 минут, пока открыта. Кнопка «Попробовать сейчас» — чтобы не ждать. Архив уже можно смотреть: докачанное добавится в него само.'],
    ['Что будет в архиве?', 'Переписки — все, с текстом, датами, фото, голосовыми и файлами. Фото из альбомов. Стена с комментариями. Друзья со ссылками на профили (таблицей для Excel тоже). Список музыки. Видео — ссылками и обложками. И страница «Мой ВКонтакте в цифрах».'],
    ['Чего в архиве не будет — и почему?', 'Сами видео и музыка: ВК кладёт в архив только ссылки и названия. Содержимое пересланных сообщений: ВК пишет только «1 прикреплённое сообщение». Стикеры и подарки — только отметкой. Это ограничения архива ВК, а не программы.'],
    ['Часть фото не скачалась', 'Ссылки на файлы в архиве ВК подписаны и со временем перестают действовать. Закажите свежий архив, укажите его в «Настройке» и нажмите «Сохранить ещё раз»: уже скачанное второй раз не качается, а ссылки возьмутся новые.'],
    ['Как найти старое сообщение?', 'Раздел «Поиск»: введите слово или часть фразы — программа найдёт его во всех переписках и откроет переписку прямо на этом сообщении.'],
    ['Где мой архив и как его открыть?', 'В папке, которую вы выбрали (по умолчанию — backup рядом с программой). Откройте в ней index.html двойным щелчком — интернет и программа для этого не нужны. Пока программа открыта, архив можно смотреть и кнопкой «Открыть архив».'],
    ['Можно удалять страницу ВК?', 'Сначала откройте архив и пролистайте важные переписки: всё ли на месте, открываются ли фото и голосовые. Скопируйте папку архива на второй диск или флешку. Только после этого — удаляйте.'],
    ['Как проверить, что программа ничего не отправляет?', 'Раздел «Безопасность»: там список всех серверов, с которыми программа говорила, и пошаговая проверка средствами самой Windows.'],
  ];
  $('#screen-help').innerHTML = `<div class="stack"><div><h1>Помощь</h1></div><div class="card">
    ${faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><div>${esc(a)}</div></details>`).join('')}</div></div>`;
}

// ── Каркас ──
const routeName = () => {
  const name = location.hash.replace('#/', '') || 'home';
  return ['home', 'search', 'stats', 'setup', 'security', 'help'].includes(name) ? name : 'home';
};

function route() {
  const name = routeName();
  for (const s of document.querySelectorAll('.screen')) s.classList.toggle('hidden', s.id !== `screen-${name}`);
  for (const a of document.querySelectorAll('.nav a')) a.classList.toggle('active', a.dataset.route === name);
  if (name === 'security') api('/api/security').then((d) => { security = d; renderSecurity(); }).catch(() => {});
  if (name !== 'search') $('#screen-search').innerHTML = '';
  render.sig = null;
  render();
  window.scrollTo(0, 0);
}

function render() {
  if (!state) return;
  const name = routeName();
  const lock = $('#side-lock');
  lock.classList.toggle('bad', !state.network.installed);
  $('#side-lock-text').textContent = state.network.installed ? 'только файлы ВК' : 'выключен!';
  // Перерисовываем, только если что-то поменялось: иначе сбрасывались бы раскрытые списки и выделение.
  // И не пока человек печатает путь — курсор прыгал бы в начало поля
  const sig = JSON.stringify([name, state.settings, state.job, state.result, insightsKey, name === 'security' ? state.network : null]);
  if (sig === render.sig) return;
  const typing = document.activeElement && document.activeElement.matches('#screen-setup input[type=text]');
  if (name === 'setup' && typing) return;
  render.sig = sig;
  if (name === 'home') {
    const open = [...document.querySelectorAll('#screen-home details[open]')].map((d) => d.dataset.key);
    renderHome();
    for (const k of open) { const d = document.querySelector(`#screen-home details[data-key="${k}"]`); if (d) d.open = true; }
  }
  if (name === 'setup') renderSetup();
  if (name === 'search') renderSearch();
  if (name === 'stats') renderStats();
  if (name === 'security') renderSecurity();
  if (name === 'help' && !$('#screen-help').innerHTML) renderHelp();
  applySizes($(`#screen-${name}`));
}

// Ширина и высота полос — через CSSOM: атрибут style в разметке запрещён политикой безопасности страницы
function applySizes(root) {
  for (const el of root.querySelectorAll('[data-w]')) { el.style.width = `${el.dataset.w}%`; el.removeAttribute('data-w'); }
  for (const el of root.querySelectorAll('[data-h]')) { el.style.height = `${el.dataset.h}%`; el.removeAttribute('data-h'); }
}

async function refresh() {
  try { state = await api('/api/status'); } catch (e) { return; }
  if (state.result && state.result.index && state.job.step !== 'download') loadInsights();
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
  if (e.target.id === 'q') {
    search.q = e.target.value;
    clearTimeout(search.timer);
    search.timer = setTimeout(runSearch, 250);
  }
});

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const a = btn.dataset.act;
  if (a === 'save' || a === 'save-start') {
    const res = await act('/api/settings', readForm());
    if (res && res.ok) {
      form = null;
      if (a === 'save-start' && await act('/api/start', {})) location.hash = '#/home';
    }
  } else if (a === 'find') {
    const out = $('#found');
    out.textContent = 'Ищу…';
    try {
      const d = await api('/api/find-archives');
      if (!d.archives.length) { out.textContent = `В папке ${d.folder} архивов ВК не нашлось`; return; }
      $('#f-archive').value = d.archives[0].path;
      form = readForm();
      out.textContent = d.archives.length > 1 ? `Нашлось ${d.archives.length}, взял самый свежий` : 'Нашёл';
    } catch (err) { out.textContent = err.message; }
  } else if (a === 'start') {
    if (!state.settings.archive) { location.hash = '#/setup'; return; }
    await act('/api/start', {});
  } else if (a === 'stop') {
    await act('/api/stop', {});
  } else if (a === 'retry-now') {
    await act('/api/retry-now', {});
  } else if (a === 'retry') {
    await act('/api/retry-failed', {});
  } else if (a === 'open-folder') {
    await act('/api/open-folder', {});
  } else if (a === 'theme') {
    applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  }
});

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', () => {
  hydrateIcons();
  syncThemeButton();
  route();
  refresh();
  setInterval(refresh, 1500);
});
