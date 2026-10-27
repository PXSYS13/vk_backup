// Бэкап ВКонтакте — страница программы. Без библиотек и без запросов куда-либо, кроме этой программы.
'use strict';

const VK_DATA_PAGE = 'https://vk.com/data_protection?section=rules&scroll_to_archive=1';
let state = null;
let security = null;
let form = null; // черновик настроек, пока человек их правит

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = (n) => Number(n || 0).toLocaleString('ru-RU');

function plural(n, one, few, many) {
  const n10 = n % 10, n100 = n % 100;
  const w = n10 === 1 && n100 !== 11 ? one : (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? few : many);
  return `${num(n)} ${w}`;
}

function bytes(n) {
  const units = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  let i = 0; n = Number(n || 0);
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

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
  if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
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

// ── Главная ──

function stepCard(n, done, title, body) {
  return `<div class="card"><div class="step${done ? ' done' : ''}"><span class="step-num">${done ? '✓' : n}</span>
    <div class="step-body"><h2>${title}</h2>${body}</div></div></div>`;
}

function renderHome() {
  const s = state;
  const set = form || s.settings;
  const job = s.job;
  const running = job.state === 'running' || job.state === 'stopping';
  const hasArchive = !!s.settings.archive;

  const step1 = stepCard(1, hasArchive, 'Закажите архив у ВКонтакте', `
    <p class="muted">ВК сам выгружает все ваши данные: переписки с 2006 года, фото, друзей, стену, список музыки.
    Программе не нужны ни пароль, ни доступ к аккаунту — только этот архив.</p>
    <ol class="steps" style="margin:10px 0 12px">
      <li>Откройте страницу ВК «Защита данных» — кнопка ниже, она откроется в вашем браузере.</li>
      <li>Нажмите «Загрузить архив» (или «Запросить архив»), отметьте все разделы и подтвердите паролем.</li>
      <li>Дождитесь сообщения от ВК, что архив готов (от нескольких часов до пары дней), и скачайте ZIP-файл.</li>
    </ol>
    <a class="btn" href="${VK_DATA_PAGE}" target="_blank" rel="noreferrer noopener">Открыть «Защиту данных» ВК ↗</a>
    <p class="tiny" style="margin-top:8px">Ссылка открывается в вашем браузере. Сама программа к сайту ВК не обращается.</p>`);

  const checks = s.sections.map((x) => `<label class="check"><input type="checkbox" name="sec" value="${x.key}"
      ${set.sections.includes(x.key) ? 'checked' : ''} ${running ? 'disabled' : ''}> ${esc(x.title)}</label>`).join('');
  const step2 = stepCard(2, hasArchive, 'Укажите архив и папку для результата', `
    <label class="field"><span>Архив ВК — ZIP-файл или папка, куда вы его распаковали</span>
      <input type="text" id="f-archive" value="${esc(set.archive)}" placeholder="C:\\Users\\…\\Downloads\\Archive.zip" ${running ? 'disabled' : ''}></label>
    <div class="row"><button class="btn" data-act="find" ${running ? 'disabled' : ''}>Найти в «Загрузках»</button>
      <span class="tiny" id="found"></span></div>
    <label class="field"><span>Куда сохранить архив с фото и страницами</span>
      <input type="text" id="f-folder" value="${esc(set.folder)}" ${running ? 'disabled' : ''}></label>
    <div class="field"><span>Что сохранить</span><div class="checks">${checks}</div></div>
    <label class="check"><input type="checkbox" id="f-download" ${set.download ? 'checked' : ''} ${running ? 'disabled' : ''}>
      Скачать фото, голосовые и файлы по ссылкам из архива</label>
    <p class="tiny" style="margin:4px 0 12px 26px">В архиве ВК фото и голосовые — ссылками. Без этой галочки программа
      не выходит в интернет вообще и делает страницы только из текста.</p>
    <button class="btn primary" data-act="save" ${running ? 'disabled' : ''}>Сохранить настройки</button>`);

  let progress = '';
  if (job.state !== 'idle') {
    const pct = job.total ? Math.min(100, Math.round(job.done * 100 / job.total)) : null;
    const bar = running ? `<div class="progress${pct === null ? ' indet' : ''}"><div style="width:${pct ?? 30}%"></div></div>` : '';
    const problem = job.problem ? `<div class="card err" style="margin-top:10px">${esc(job.problem_text)}</div>` : '';
    progress = `<div style="margin-top:14px"><div class="row"><span class="dot ${running ? 'run' : job.state === 'done' ? 'ok' : job.state === 'error' ? 'err' : 'warn'}"></span>
      <b>${esc(job.text)}</b></div>${bar}${problem}</div>`;
  }
  const r = s.result;
  let result = '';
  if (r) {
    const media = Object.values(r.media || {});
    const done = media.reduce((a, m) => a + (m.done || 0), 0);
    const failed = media.reduce((a, m) => a + (m.failed || 0), 0);
    const pending = media.reduce((a, m) => a + (m.pending || 0), 0);
    const size = media.reduce((a, m) => a + (m.bytes || 0), 0);
    const stat = (v, label) => `<div class="stat"><b class="num">${num(v)}</b><span>${label}</span></div>`;
    const failedList = (r.failed || []).map((f) => `<tr><td><code>${esc(f.path)}</code></td><td>${esc(f.error)}</td></tr>`).join('');
    result = `<div class="stats">
        ${stat(r.messages, `сообщений в ${plural(r.chats, 'беседе', 'беседах', 'беседах')}`)}
        ${stat(r.photos, 'фото в альбомах')}${stat(r.friends, 'друзей')}${stat(r.posts, 'записей на стене')}
        ${stat(r.tracks, 'треков')}${stat(r.videos, 'видео (ссылками)')}
        <div class="stat"><b class="num">${num(done)}</b><span>файлов скачано · ${bytes(size)}</span></div>
        ${pending ? stat(pending, 'файлов ждут скачивания') : ''}
        ${failed ? `<div class="stat"><b class="num" style="color:var(--err)">${num(failed)}</b><span>файлов не скачалось</span></div>` : ''}
      </div>
      <div class="row" style="margin-top:14px">
        ${r.index ? '<button class="btn primary" data-act="open-archive">Открыть архив</button>' : ''}
        <button class="btn" data-act="open-folder">Открыть папку</button>
        <button class="btn" data-act="render" ${running ? 'disabled' : ''}>Обновить страницы</button>
        ${failed ? `<button class="btn" data-act="retry" ${running ? 'disabled' : ''}>Повторить не скачавшиеся</button>` : ''}
      </div>
      ${failedList ? `<details style="margin-top:10px"><summary>Какие файлы не скачались</summary><div>
        <p class="tiny">Чаще всего ссылка из архива устарела: ВК подписывает ссылки на файлы, и они живут не вечно.
        Помогает свежий архив — закажите новый и укажите его вместо старого: скачанное второй раз не качается.</p>
        <table class="t">${failedList}</table></div></details>` : ''}`;
  }
  const button = running
    ? `<button class="btn big danger" data-act="stop" ${job.state === 'stopping' ? 'disabled' : ''}>Остановить</button>`
    : `<button class="btn big primary" data-act="start" ${hasArchive ? '' : 'disabled'}>${r ? 'Сохранить ещё раз' : 'Сохранить мой ВК'}</button>`;
  const step3 = stepCard(3, job.state === 'done', 'Сохраните', `
    <p class="muted">Программа разберёт архив, скачает файлы по ссылкам и соберёт страницы, которые откроются
    в любом браузере без интернета: переписки как в Telegram, фото по альбомам, стена, друзья, музыка.</p>
    <div class="row" style="margin-top:12px">${button}</div>${progress}${result}`);

  $('#screen-home').innerHTML = `<div class="stack"><div><h1>Сохранить мой ВКонтакте</h1>
    <p class="muted">Всё своё из ВК — на свой компьютер. Без пароля, без доступа к аккаунту, без посредников.</p></div>
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

// ── Безопасность ──

function renderSecurity() {
  const net = (security && security.network) || state.network;
  const hosts = (net.hosts || []).map(([h, n]) => `<tr><td><code>${esc(h)}</code></td><td class="num">${num(n)}</td></tr>`).join('');
  const blocked = (net.blocked || []).map((b) => `<tr><td>${esc(b.time)}</td><td>${esc(b.what)}</td><td><code>${esc(b.target)}</code></td></tr>`).join('');
  const code = ((security && security.code) || []).map((c) => `<tr><td><code>${esc(c.path)}</code></td><td><code>${esc(c.sha256)}</code></td></tr>`).join('');
  $('#screen-security').innerHTML = `<div class="stack">
    <div><h1>Безопасность</h1><p class="muted">Как программа обращается с вашими данными — и как проверить это самому, не веря на слово.</p></div>

    <div class="card ${net.installed ? 'ok' : 'err'}"><h2>${net.installed ? '✓ Сетевой замок включён' : '✕ Сетевой замок не включён'}</h2>
      <p>Программа может соединиться только с этими серверами ВК, на которых лежат файлы из архива:
      ${net.allowed_domains.map((d) => `<code>*.${esc(d)}</code>`).join(' ')}. Ни сайта vk.com, ни API ВК, ни входа
      в аккаунт в списке нет. Любое другое соединение замок обрывает до того, как оно начнётся, и записывает попытку в журнал.</p>
      <p class="tiny">Журнал всех соединений: <code>${esc(net.log_file || 'logs/network.log')}</code></p></div>

    <div class="card"><h2>С кем программа говорила с момента запуска</h2>
      ${hosts ? `<table class="t"><tr><th>Сервер</th><th>Запросов</th></tr>${hosts}</table>` : '<p class="muted">Ни с кем — ещё ничего не скачивалось.</p>'}
      <h3 style="margin-top:14px">Что замок не пустил</h3>
      ${blocked ? `<table class="t">${blocked}</table>` : '<p class="muted">Ничего. Программа не пыталась соединиться ни с кем лишним.</p>'}</div>

    <div class="card"><h2>Что программа делает и чего не делает</h2>
      <ul class="steps" style="padding-left:20px">
        <li>Не спрашивает пароль и не получает доступ к аккаунту ВК: работает только с архивом, который вы сами скачали.</li>
        <li>Не отправляет ваши данные никуда: ни на свои серверы (их нет), ни в аналитику, ни «проверять обновления».</li>
        <li>Скачивает только файлы по прямым ссылкам из вашего архива — и только с файловых серверов ВК.</li>
        <li>Страница программы (эта) доступна только с этого компьютера: <code>127.0.0.1</code>, чужие сайты не могут ею управлять.</li>
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
      <details style="margin-top:10px"><summary>Отпечатки файлов программы (SHA-256)</summary><div><table class="t">${code}</table></div></details></div>
  </div>`;
}

// ── Помощь ──

function renderHelp() {
  const faq = [
    ['Почему архив, а не вход через ВК?', 'С сентября 2026 года ВК закрыл сторонним программам доступ к личным сообщениям (так перестал работать Kate Mobile). Официальный архив — единственный надёжный способ получить всю переписку. И он безопаснее: программе не нужен ни пароль, ни ключ доступа к аккаунту.'],
    ['Что будет в архиве?', 'Переписки — все, с текстом, датами, фото, голосовыми и файлами. Фото из альбомов. Стена с комментариями. Друзья со ссылками на профили (таблицей для Excel тоже). Список музыки. Видео — ссылками и обложками.'],
    ['Чего в архиве не будет — и почему?', 'Сами видео и музыка: ВК кладёт в архив только ссылки и названия. Содержимое пересланных сообщений: ВК пишет только «1 прикреплённое сообщение». Стикеры и подарки — только отметкой. Это ограничения архива ВК, а не программы.'],
    ['Часть фото не скачалась', 'Ссылки на файлы в архиве ВК подписаны и со временем перестают действовать. Закажите свежий архив, укажите его вместо старого и нажмите «Сохранить ещё раз»: уже скачанное второй раз не качается.'],
    ['Где мой архив и как его открыть?', 'В папке, которую вы выбрали (по умолчанию — backup рядом с программой). Откройте в ней index.html двойным щелчком — или кнопкой «Открыть архив». Интернет для этого не нужен, программа тоже.'],
    ['Можно удалять страницу ВК?', 'Сначала откройте архив и пролистайте важные переписки: всё ли на месте, открываются ли фото и голосовые. Скопируйте папку архива на второй диск или флешку. Только после этого — удаляйте.'],
    ['Как проверить, что программа ничего не отправляет?', 'Раздел «Безопасность»: там список всех серверов, с которыми программа говорила, и пошаговая проверка средствами самой Windows.'],
  ];
  $('#screen-help').innerHTML = `<div class="stack"><div><h1>Помощь</h1></div><div class="card">
    ${faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><div>${esc(a)}</div></details>`).join('')}</div></div>`;
}

// ── Каркас ──

function route() {
  const name = (location.hash.replace('#/', '') || 'home');
  for (const s of document.querySelectorAll('.screen')) s.classList.toggle('hidden', s.id !== `screen-${name}`);
  for (const a of document.querySelectorAll('.nav a')) a.classList.toggle('active', a.dataset.route === name);
  if (name === 'security') api('/api/security').then((d) => { security = d; renderSecurity(); }).catch(() => {});
  render.sig = null;
  render();
}

function render() {
  if (!state) return;
  const name = (location.hash.replace('#/', '') || 'home');
  const lock = $('#side-lock');
  lock.classList.toggle('bad', !state.network.installed);
  $('#side-lock-text').textContent = state.network.installed ? 'только файлы ВК' : 'выключен!';
  // Перерисовываем, только если что-то поменялось: иначе сбрасывались бы раскрытые списки и выделение.
  // И не пока человек печатает путь — курсор прыгал бы в начало поля
  const sig = JSON.stringify([name, state.settings, state.job, state.result, name === 'security' ? state.network : null]);
  if (sig === render.sig) return;
  const typing = document.activeElement && document.activeElement.matches('#screen-home input[type=text]');
  if (name === 'home' && typing) return;
  render.sig = sig;
  if (name === 'home') renderHome();
  if (name === 'security') renderSecurity();
  if (name === 'help' && !$('#screen-help').innerHTML) renderHelp();
}

async function refresh() {
  try { state = await api('/api/status'); } catch (e) { return; }
  render();
}

document.addEventListener('input', (e) => {
  if (e.target.closest('#screen-home')) form = readForm();
});

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const a = btn.dataset.act;
  if (a === 'save') {
    const res = await act('/api/settings', readForm());
    if (res && res.ok) form = null;
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
    await act('/api/start', {});
  } else if (a === 'stop') {
    await act('/api/stop', {});
  } else if (a === 'retry') {
    await act('/api/retry-failed', {});
  } else if (a === 'render') {
    await act('/api/render', {});
  } else if (a === 'open-archive') {
    await act('/api/open-archive', {});
  } else if (a === 'open-folder') {
    await act('/api/open-folder', {});
  }
});

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', () => {
  route();
  refresh();
  setInterval(refresh, 1500);
});
