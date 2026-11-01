// Главная: что сейчас происходит, кольцо скачанного, разделы архива, «В этот день».
'use strict';

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

const RUN_RESULT = {done: 'готово', stopped: 'остановлен', error: 'с ошибкой'};

function heroState(s, t, rate) {
  const job = s.job, r = s.result;
  const running = isBusy(job);
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
    const lost = t.failed ? ` Не скачались ${plural(t.failed, 'файл', 'файла', 'файлов')} — причины на <a href="#/dashboard">панели</a>.` : '';
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
      mini = stackBar([['', m.done], ['w', m.waiting], ['f', m.failed], ['p', m.pending]], `Скачано ${num(m.done)} из ${num(all)}`);
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
    <img src="${archiveUrl(p.file)}" alt="Фото ${new Date(p.date * 1000).getFullYear()} года" loading="lazy"><span>${new Date(p.date * 1000).getFullYear()}</span></a>`).join('')}</div>` : '';
  return `<div class="card"><div class="card-head"><span class="sec-ico">${icon('calendar')}</span><div class="grow"><h2>В этот день, ${esc(o.day)}</h2>
    <div class="tiny">Что вы писали в этот день в прошлые годы</div></div></div><div class="otd-list">${items}</div>${photos}</div>`;
}

function lastRunLine(r) {
  const run = r && r.last_run;
  if (!run || !run.finished_at) return '';
  return ` · Последний бэкап ${when(run.finished_at)} — ${RUN_RESULT[run.state] || run.state} · <a href="#/dashboard">подробнее</a>`;
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
      <span class="hero-top-end"><span class="heartbeat">${beat}</span>${flagPennant()}</span></div>
    <div class="hero-body">${visual}<div><h1>${esc(h.title)}</h1><p class="sub">${h.sub}</p><div class="row actions">${h.actions}</div></div></div>
    ${stats}
    <div class="hero-what">Что сохраняем: ${esc(what || 'ничего')}${s.settings.download ? ' — с фото и голосовыми' : ' — только текст, без сети'} · <a href="#/setup">изменить</a>${isBusy(job) ? '' : lastRunLine(r)}</div></div>`;
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
      а ссылки возьмутся новые. Причины по группам — на <a href="#/dashboard">панели</a>.</p><div class="t-wrap" tabindex="0" role="region" aria-label="Файлы, которые не скачались"><table class="t">${rows}</table></div>
      <div class="row mt-10"><button class="btn small" data-act="retry" ${isBusy(job) ? 'disabled' : ''}>${icon('refresh')}Попробовать их ещё раз</button></div></div></details></div>`;
  }
  const safety = r && r.index ? `<div class="banner info"><span class="b-icon">${icon('copy')}</span><div><h3>Прежде чем удалять страницу ВК</h3>
    <p>Откройте архив и пролистайте важные переписки. Скопируйте папку <code>${esc(s.settings.folder)}</code> на второй диск или флешку —
    одна копия на одном диске ненадёжна. Что ещё проверить — на <a href="#/dashboard">панели</a>.</p></div></div>` : '';
  $('#screen-home').innerHTML = `<div class="stack">${hero}${flagCard()}${problem}${banner}${r && r.index ? onThisDay() : ''}${r ? sectionCards(s) : ''}${failed}${safety}</div>`;
}

onAct('start', async () => {
  if (!state.settings.archive) { location.hash = '#/setup'; return; }
  await act('/api/start', {});
});
onAct('stop', () => act('/api/stop', {}));
onAct('retry-now', () => act('/api/retry-now', {}));
onAct('retry', () => act('/api/retry-failed', {}));
onAct('open-folder', () => act('/api/open-folder', {}));
