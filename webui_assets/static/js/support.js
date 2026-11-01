// «Поддержать» и флажок «От автора». Одно предложение «Будем на связи»: канал, где автор пишет
// о сбоях ВК и Яндекса, и донат, на который живут бесплатные программы. Без всплывающих окон:
// флажок на главной сам раскрывается после бэкапа и успокаивается. Программа по этим ссылкам
// ничего не запрашивает, открывает их сам человек; что флажок уже показан — помнит только браузер.
'use strict';

const LINKS = {
  telegram: 'https://t.me/davronsv',
  donate: 'https://dalink.to/davronsvv',
  youtube: 'https://www.youtube.com/@davronsv',
  github: 'https://github.com/PXSYS13/vk_backup',
  issues: 'https://github.com/PXSYS13/vk_backup/issues/new',
  yadisk: 'https://github.com/PXSYS13/yadisk_backup',
  icloud: 'https://github.com/PXSYS13/icloud_backup',
};
const PROMOS = {
  yadisk: {icon: 'disk', name: 'Яндекс Бэкап', ask: 'А Яндекс Диск?',
    text: 'Сохраняет весь Диск на компьютер и работает, даже когда Яндекс недоступен.'},
  icloud: {icon: 'image', name: 'iCloud Бэкап', ask: 'Фото в iCloud?',
    text: 'Скачивает всю библиотеку Фото на компьютер, если вы больше не платите за iCloud+. Бета-версия.'},
};
const FLAG_KEY = 'vkb.flag';
const FLAG_VISITS = 3;         // столько заходов на главную карточка открыта сама, дальше — только флажок
const FLAG_AGAIN_DAYS = 30;    // после нового бэкапа покажем снова не раньше, чем через месяц
const FLAG_AGAIN_CLICKED = 90; // …а если человек уже переходил по ссылке — через три
let flagVisitPending = false;  // зашли на главную: засчитать заход, когда станет известен бэкап

const link = (key, label, cls = 'btn', ico = '') => `<a class="${cls}" data-link="${key}" href="${LINKS[key]}"
  target="_blank" rel="noopener noreferrer">${ico ? icon(ico) : ''}${label}</a>`;

// ── Что помнит браузер: только время показа и отметки, никаких «на что нажали» ──
// Браузер не даёт localStorage (запрещены данные сайтов) — помним до перезагрузки страницы
let flagMemory = {};
function flagState() {
  try {
    const raw = localStorage.getItem(FLAG_KEY);
    const s = raw === null ? flagMemory : JSON.parse(raw);
    return s && typeof s === 'object' ? {...s} : {};
  } catch (e) {
    return {...flagMemory};
  }
}
function saveFlag(patch) {
  const s = {...flagState(), ...patch};
  flagMemory = s;
  try { localStorage.setItem(FLAG_KEY, JSON.stringify(s)); } catch (e) { /* хватит памяти страницы */ }
  return s;
}
const dismissedFor = (where) => (flagState().dismissed || {})[where];

// Последний бэкап закончился удачно и сейчас ничего не идёт: только тогда уместно о чём-то просить
function finishedBackupId() {
  const r = state && state.result, run = r && r.last_run;
  if (!r || !r.index || !run || run.state !== 'done' || !run.finished_at) return null;
  if (isBusy(state.job) || state.job.state === 'error' || state.job.problem) return null;
  return run.finished_at;
}

// Закончился новый удачный бэкап: пора ли снова показать предложение. Пауза считается от прошлого
// показа до конца этого бэкапа — просто зайти через месяц, без нового бэкапа, мало
function noteBackup(id) {
  const f = flagState();
  if (f.hidden || f.lastBackupId === id) return;
  const pause = (f.clickedAt ? FLAG_AGAIN_CLICKED : FLAG_AGAIN_DAYS) * 864e5;
  if (f.lastFullAt && id * 1000 < f.lastFullAt + pause) return;
  saveFlag({lastFullAt: Date.now(), lastBackupId: id, visits: 0, expanded: null, dismissed: {}, clickedAt: null});
}

function noteHomeVisit(id) {
  const f = flagState();
  if (f.lastBackupId === id) saveFlag({visits: (f.visits || 0) + 1});
}

function flagOpen(id) {
  const f = flagState();
  if (f.hidden) return false;
  if (f.expanded === id) return true;
  if (f.lastBackupId !== id || (f.dismissed || {}).home === id) return false;
  return (f.visits || 0) <= FLAG_VISITS;
}
// Предложение для этого бэкапа уже показано (или пауза не прошла) — тогда и на других экранах молчим
const offeredFor = (id) => flagState().lastBackupId === id;

function redrawAsks() {
  render.sig = null;
  render();
}

// ── Куски для экранов ──
function promoCard(key, withAsk = false) {
  const p = PROMOS[key];
  if ((flagState().owned || {})[key]) return '';
  return `<div class="app-promo" data-promo="${key}"><span class="sec-ico">${icon(p.icon)}</span>
    <div class="min0"><b>${withAsk ? `${esc(p.ask)} ` : ''}${esc(p.name)}</b><div class="tiny">${esc(p.text)}</div></div>
    <div class="row promo-actions">${link(key, 'Скачать', 'btn small')}
      <button type="button" class="btn small ghost" data-act="promo-own" data-app="${key}">Уже есть</button></div></div>`;
}

function flagPennant() {
  const id = finishedBackupId();
  if (!id || flagState().hidden) return '';
  noteBackup(id);
  if (flagVisitPending) { noteHomeVisit(id); flagVisitPending = false; }
  const open = flagOpen(id);
  const fresh = open && (flagState().visits || 0) <= 1 && !flagState().expanded;
  return `<button type="button" class="pennant${fresh ? ' glow' : ''}" data-act="flag-toggle" aria-expanded="${open}"
    ${open ? 'aria-controls="flag-card"' : ''}>${icon('flag')}От автора</button>`;
}

function flagCard() {
  const id = finishedBackupId();
  if (!id || !flagOpen(id)) return '';
  return `<div class="card flag-card ask flag-ask" id="flag-card"><div class="card-head"><span class="sec-ico">${icon('send')}</span>
    <div class="grow"><h2>Будем на связи</h2><div class="tiny">От автора программы</div></div>
    <button type="button" class="btn small ghost" data-act="flag-later" data-where="home">Не сейчас</button></div>
    <p class="muted">О сбоях ВК и Яндекса пишу в канале. Программы бесплатные, взнос любой суммы — по желанию.</p>
    <div class="row mt-14">${link('telegram', 'Подписаться', 'btn primary', 'send')}${link('donate', 'Поддержать', 'btn', 'heart')}</div>
    ${promoCard('yadisk', true)}</div>`;
}

function fiveCard(d) {
  const id = finishedBackupId();
  if (!id || !d.checks.every((c) => c.ok)) return '';
  noteBackup(id);
  if (flagState().hidden || !offeredFor(id) || dismissedFor('dashboard') === id) return '';
  return `<div class="card five-card ask flag-ask"><div class="card-head"><span class="sec-ico ok">${icon('check')}</span>
    <div class="grow"><h2>5 из 5: копия полная</h2></div>
    <button type="button" class="btn small ghost" data-act="flag-later" data-where="dashboard">Не сейчас</button></div>
    <p class="muted">Все пункты выполнены. Если ВК что-то изменит или сломается, напишу в канале.</p>
    <div class="row mt-14">${link('telegram', 'Подписаться', 'btn primary', 'send')}${link('donate', 'Поддержать', 'btn', 'heart')}</div>
    ${promoCard('icloud', true)}</div>`;
}

function thanksCard(s, years) {
  // Пока идёт бэкап или после ошибки ни о чём не просим — и здесь тоже
  if (!finishedBackupId() || flagState().hidden || !s.messages) return '';
  const total = `${plural(s.messages, 'сообщение', 'сообщения', 'сообщений')} за ${plural(years.length || 1, 'год', 'года', 'лет')}`;
  const summary = `Мой ВКонтакте в цифрах: ${total}. Всё сохранено на компьютере программой VK Backup — ${LINKS.github}`;
  return `<div class="card thanks-card ask"><h2>${esc(total)} — теперь у вас</h2>
    <p class="muted mt-8">Программа бесплатна. Если она пригодилась, можно поддержать любой суммой.</p>
    <div class="row mt-14">${link('donate', 'Поддержать', 'btn primary', 'heart')}${link('telegram', 'Подписаться', 'btn', 'send')}
      <button type="button" class="btn ghost" data-act="copy" data-copy="${esc(summary)}">${icon('copy')}Скопировать итог</button></div></div>`;
}

function askCard() {
  return `<div class="card ask-card ask"><h2>Не нашли ответ?</h2>
    <p class="muted mt-8">Спросите на GitHub или загляните в канал: там новости и решения частых проблем.</p>
    <div class="row mt-14">${link('telegram', 'В канал', 'btn', 'send')}${link('issues', 'Спросить', 'btn', 'external')}</div></div>`;
}

// ── «Нас поддерживают»: копия общего списка автора, пришедшая с программой ──
const BACKERS_PAGE = 9;
const backers = {data: null, busy: false, shown: BACKERS_PAGE};
const CURRENCY_SIGN = {RUB: '₽', USD: '$', EUR: '€'};
const money = (amount, currency) => `${num(amount)} ${CURRENCY_SIGN[currency] || currency}`;
// «2026-10-30» → «30 октября 2026»: дата без времени, сдвигать её по часовому поясу нельзя
function isoDay(s) {
  const [y, m, d] = String(s).split('-').map(Number);
  return y && m && d ? `${d} ${MONTHS[m - 1]} ${y}` : '';
}

async function loadBackers() {
  if (backers.busy || backers.data) return;
  backers.busy = true;
  try {
    backers.data = await api('/api/supporters');
  } catch (e) {
    backers.data = {supporters: [], top: [], people: 0};
  } finally {
    backers.busy = false;
  }
  if (routeName() === 'support') redrawAsks();
}

function backerCard(x, i) {
  return `<li class="supporter"><div class="supporter-top">${avatar(x.name, i)}
    <div class="min0 grow"><div class="supporter-name">${esc(x.name)}</div><div class="tiny">${esc(isoDay(x.date))}</div></div>
    ${x.amount != null ? `<div class="supporter-sum">${esc(money(x.amount, x.currency))}</div>` : ''}</div>
    ${x.message ? `<blockquote>«${esc(x.message)}»</blockquote>` : ''}</li>`;
}

function topBackerCard(p, i) {
  const since = p.donations > 1 ? `${plural(p.donations, 'донат', 'доната', 'донатов')}, первый — ${isoDay(p.since)}` : isoDay(p.since);
  return `<li class="top-supporter"><span class="top-rank">${i + 1}</span>${avatar(p.name, i)}
    <div class="min0 grow"><div class="supporter-name">${esc(p.name)}</div><div class="tiny">${esc(since)}</div></div>
    <div class="supporter-sum">${p.sums.map((s) => esc(money(s.amount, s.currency))).join(' + ')}</div></li>`;
}

function backersSection() {
  const d = backers.data;
  if (!d) {
    loadBackers();
    return '<div class="card" id="supporters"><h2>Нас поддерживают</h2><p class="muted mt-8">Загружаю…</p></div>';
  }
  const list = d.supporters || [], top = d.top || [];
  const people = d.people ? `Спасибо ${num(d.people)} ${word(d.people, 'человеку', 'людям', 'людям')}, которые помогли проекту` : '';
  const topBlock = top.length ? `<h3 class="mt-14">Больше всех помогли</h3>
    <p class="tiny">Все донаты одного человека складываются. Здесь те, кто поддержал на ${esc(money(d.top_min_rub || 500, 'RUB'))} и больше.</p>
    <ol class="top-supporters mt-8">${top.map(topBackerCard).join('')}</ol>` : '';
  const listBlock = list.length ? `<ul class="supporters mt-14">${list.slice(0, backers.shown).map(backerCard).join('')}</ul>
    ${backers.shown < list.length ? '<div class="row mt-12 center-row"><button type="button" class="btn" data-act="supporters-more">Показать ещё</button></div>' : ''}`
    : `<div class="empty">${icon('heart')}Здесь появятся имена тех, кто поддержал проект</div>`;
  return `<div class="card" id="supporters"><h2>Нас поддерживают</h2>
    <p class="muted" id="supporters-count">${esc(people)}</p>${topBlock}${listBlock}
    <p class="tiny mt-12">Список общий для всех программ автора${d.updated ? `, обновлён ${esc(isoDay(d.updated))}` : ''}.
      Новые имена приходят с новой версией программы: сама она за списком в интернет не ходит.</p></div>`;
}

function renderSupport() {
  const f = flagState();
  const promos = ['yadisk', 'icloud'].map((k) => promoCard(k)).join('');
  $('#screen-support').innerHTML = `<div class="stack">
    <div><h1>Поддержать проект</h1>
      <p class="muted">Программа бесплатная и с открытым кодом — и такой останется. Её делает один человек в свободное время,
        чтобы люди не потеряли свои переписки и фото.</p></div>
    <div class="dash-2">
      <div class="card support-card"><span class="sec-ico">${icon('send')}</span><h2 class="mt-12">Канал в Telegram</h2>
        <p class="muted">Когда ВК или Яндекс сбоят — пишу, что случилось и что делать. Ещё — новые программы и решения частых проблем.</p>
        <div class="row mt-14">${link('telegram', 'Подписаться', 'btn primary', 'send')}</div></div>
      <div class="card support-card"><span class="sec-ico">${icon('heart')}</span><h2 class="mt-12">Поддержать автора</h2>
        <p class="muted">Любая сумма, по желанию: на неё живут эта программа и соседние. В сообщении можно написать название
          программы — мне важно знать, что пригодилось. Имя и сообщение видны всем; не хотите — подпишитесь «Аноним».</p>
        <div class="donate-row mt-14"><div>${link('donate', 'Поддержать', 'btn primary', 'heart')}
          <p class="tiny mt-8">Или наведите камеру телефона на QR-код — откроется та же страница DonationAlerts.</p></div>
          <img class="donate-qr" src="/static/donate-qr.png" width="132" height="132"
            alt="QR-код: поддержать проект через DonationAlerts (dalink.to/davronsvv)"></div></div></div>
    <div class="row">${link('youtube', 'YouTube', 'btn', 'play')}${link('github', 'Код на GitHub', 'btn', 'code')}</div>
    ${backersSection()}
    ${promos ? `<div><h2>Другие программы автора</h2><div class="promos mt-12">${promos}</div></div>` : ''}
    <div class="card"><h2>Без слежки</h2>
      <p class="muted">Программа никуда не сообщает, нажали ли вы на ссылку: ссылки открываются в вашем браузере, а сама она
        к этим сайтам не обращается. Когда флажок «От автора» показали и закрыли, помнит только этот браузер.</p>
      <div class="row mt-12"><button type="button" class="btn small" data-act="flag-hide" aria-pressed="${!!f.hidden}">
        ${icon('flag')}${f.hidden ? 'Показывать флажок' : 'Скрыть флажок'}</button></div></div></div>`;
}

onAct('flag-toggle', () => {
  const id = finishedBackupId();
  if (!id) return;
  const f = flagState();
  saveFlag(flagOpen(id) ? {expanded: null, dismissed: {...(f.dismissed || {}), home: id}} : {expanded: id});
  redrawAsks();
});
onAct('flag-later', (btn) => {
  const f = flagState();
  saveFlag({expanded: null, dismissed: {...(f.dismissed || {}), [btn.dataset.where]: finishedBackupId()}});
  redrawAsks();
});
onAct('flag-hide', () => {
  saveFlag({hidden: !flagState().hidden});
  redrawAsks();
});
onAct('supporters-more', () => {
  backers.shown += BACKERS_PAGE;
  redrawAsks();
});
onAct('promo-own', (btn) => {
  saveFlag({owned: {...(flagState().owned || {}), [btn.dataset.app]: true}});
  redrawAsks();
});

// Перешли в канал или к донату из карточки флажка — значит, увидели: карточки сворачиваются, флажок
// вернётся не раньше чем через три месяца. Запоминаем только время, не то, куда нажали.
// Ссылки в «Помощи», «ВК в цифрах» и на экране «Поддержать» флажок не трогают
document.addEventListener('click', (e) => {
  const a = e.target.closest('.flag-ask a[data-link]');
  const id = finishedBackupId();
  if (!a || !id || !['telegram', 'donate'].includes(a.dataset.link)) return;
  const f = flagState();
  saveFlag({clickedAt: Date.now(), expanded: null, dismissed: {...(f.dismissed || {}), home: id, dashboard: id}});
  setTimeout(redrawAsks, 0);
});
