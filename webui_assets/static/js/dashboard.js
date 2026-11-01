// «Панель»: всё об архиве на одном экране — что сохранено, что ещё качается и почему,
// сколько места, как прошли запуски и можно ли уже удалять страницу ВК.
'use strict';

const DASH_EVERY = 5000;   // панель тяжелее статуса: обновляем её реже
let dashError = '';        // текст ошибки, если сводку получить не удалось

async function loadDashboard(force = false) {
  if (loadDashboard.busy || (!force && dashAt && Date.now() - dashAt < DASH_EVERY)) return;
  loadDashboard.busy = true;
  try {
    dash = await api('/api/dashboard');
    dashAt = Date.now();
    dashError = '';
  } catch (e) {
    // Программа не отвечает — об этом уже говорит полоса сверху; ошибку самой панели — показать
    if (!e.offline) dashError = e.message;
  } finally {
    loadDashboard.busy = false;
  }
  render();
}

const KPIS = [
  ['messages', 'chat', ['сообщение', 'сообщения', 'сообщений']],
  ['chats', 'users', ['беседа', 'беседы', 'бесед']],
  ['photos', 'image', ['фото', 'фото', 'фото']],
  ['friends', 'users', ['друг', 'друга', 'друзей']],
  ['posts', 'wall', ['запись на стене', 'записи на стене', 'записей на стене']],
  ['tracks', 'music', ['трек', 'трека', 'треков']],
  ['videos', 'video', ['видео', 'видео', 'видео']],
  ['docs', 'file', ['документ', 'документа', 'документов']],
];
const STEPS = [['import', 'Разбор архива'], ['download', 'Скачивание файлов'], ['render', 'Страницы'], ['waiting', 'Докачка']];
const RUN_PILL = {done: ['ok', 'Готово'], stopped: ['', 'Остановлен'], error: ['err', 'Ошибка']};
// Файлы, которые не относятся к разделу из «Настройки»
const EXTRA_TITLES = {profile: 'Аватар профиля'};

const copyBtn = (text, what) => `<button type="button" class="btn small ghost icon-btn" data-act="copy" data-copy="${esc(text)}" aria-label="Скопировать ${what}" title="Скопировать">${icon('copy')}</button>`;
const sectionTitle = (key) => ((state.sections || []).find((x) => x.key === key) || {}).title || EXTRA_TITLES[key] || key;

function kpis(d) {
  const c = d.content || {};
  const t = mediaTotals(d);
  const tiles = KPIS.map(([k, ico, unit]) => `<div class="kpi" data-k="${k}"><span class="kpi-ico">${icon(ico)}</span>
    <b>${num(c[k])}</b><span>${word(c[k] || 0, ...unit)}</span></div>`);
  if (t.all) {
    tiles.push(`<div class="kpi accent" data-k="files"><span class="kpi-ico">${icon('folder')}</span><b>${num(t.done)}</b>
      <span>${word(t.done, 'файл скачан', 'файла скачано', 'файлов скачано')} из ${num(t.all)} · ${bytes(t.bytes)}</span></div>`);
  }
  return `<div class="kpis">${tiles.join('')}</div>`;
}

function readinessCard(d) {
  const ok = d.checks.filter((c) => c.ok).length, all = d.checks.length;
  const items = d.checks.map((c) => `<li class="${c.ok ? 'ok' : 'bad'}" data-check="${c.key}"><span class="ck">${icon(c.ok ? 'check' : 'alert')}</span>
    <div class="min0"><b><span class="sr-only">${c.ok ? 'Выполнено:' : 'Не выполнено:'}</span> ${esc(c.title)}</b><div class="tiny">${esc(c.hint)}</div></div></li>`).join('');
  const verdict = ok === all ? 'Всё, что программа может проверить сама, в порядке' : 'Пока рано: сначала исправьте отмеченное';
  return `<div class="card" id="dash-ready"><div class="card-head"><span class="sec-ico">${icon('shield')}</span>
    <div class="grow"><h2>Можно ли удалять страницу ВК</h2><div class="tiny">${verdict}</div></div>
    <span class="badge${ok === all ? ' ok' : ' warn'}" id="dash-score">${ok} из ${all}</span></div>
    <ul class="checklist">${items}</ul>
    <p class="tiny mt-12">И то, чего программа проверить не может: пролистайте важные переписки в архиве и скопируйте его папку
      на второй диск или флешку — одна копия на одном диске ненадёжна.</p></div>`;
}

function nowCard(s) {
  const job = s.job;
  const running = isBusy(job);
  const at = STEPS.findIndex(([k]) => k === job.step);
  const steps = STEPS.map(([, label], i) => {
    const cls = running ? (i < at ? 'done' : i === at ? 'now' : '') : '';
    const said = cls === 'done' ? '<span class="sr-only">готово:</span> ' : '';
    return `<li class="${cls}" ${cls === 'now' ? 'aria-current="step"' : ''}><span class="pn" aria-hidden="true">${cls === 'done' ? icon('check') : i + 1}</span><span>${said}${esc(label)}</span></li>`;
  }).join('');
  let text, btn = '';
  if (running) {
    text = `${esc(job.text || 'Работаю…')}${job.started_at ? ` · идёт ${duration(Date.now() / 1000 - job.started_at)}` : ''}`;
    btn = `<button class="btn" data-act="stop" ${job.state === 'stopping' ? 'disabled' : ''}>${icon('stop')}Остановить</button>`;
  } else {
    const last = s.result && s.result.last_run;
    text = job.state === 'error' ? esc(job.problem_text)
      : last && last.finished_at ? `Бэкап не идёт. Последний закончился ${esc(when(last.finished_at))}.` : 'Бэкап не идёт.';
    if (s.settings.archive) btn = `<button class="btn primary" data-act="start">${icon('play')}${job.state === 'stopped' ? 'Продолжить' : 'Сохранить ещё раз'}</button>`;
  }
  return `<div class="card" id="dash-now"><div class="card-head"><span class="sec-ico">${icon('activity')}</span>
    <div class="grow"><h2>Сейчас</h2><div class="tiny">${text}</div></div></div>
    <ol class="pipeline" aria-label="Шаги бэкапа">${steps}</ol>${btn ? `<div class="row mt-14">${btn}</div>` : ''}</div>`;
}

function filesCard(d) {
  const entries = Object.entries(d.media || {});
  if (!entries.length) {
    const why = d.download ? 'В архиве нет файлов по ссылкам — или он ещё разбирается.'
      : 'Фото, голосовые и файлы по ссылкам не скачивались: галочка «Скачать фото…» снята.';
    return `<div class="card" id="dash-files"><h2>Файлы по разделам</h2><p class="muted">${why}
      ${d.download ? '' : '<a href="#/setup">Открыть настройку</a>'}</p></div>`;
  }
  const rows = entries.map(([key, m]) => {
    const all = m.pending + m.waiting + m.done + m.failed;
    return `<tr><th scope="row">${esc(sectionTitle(key))}</th>
      <td class="bar-cell">${stackBar([['', m.done], ['w', m.waiting], ['f', m.failed], ['p', m.pending]], `${sectionTitle(key)}: скачано ${num(m.done)} из ${num(all)}`)}</td>
      <td class="num">${num(m.done)}</td><td class="num">${num(m.waiting)}</td><td class="num">${num(m.pending)}</td>
      <td class="num">${num(m.failed)}</td><td class="num">${bytes(m.bytes)}</td></tr>`;
  }).join('');
  return `<div class="card" id="dash-files"><div class="card-head"><div class="grow"><h2>Файлы по разделам</h2>
    <div class="legend"><span><i class="ok"></i>скачано</span><span><i class="w"></i>ждут ВК</span><span><i class="f"></i>не скачались</span><span><i class="p"></i>в очереди</span></div></div></div>
    <div class="t-wrap" tabindex="0" role="region" aria-label="Файлы по разделам"><table class="t files-t"><thead><tr><th>Раздел</th><th></th><th class="num">Скачано</th><th class="num">Ждут ВК</th>
      <th class="num">В очереди</th><th class="num">Не скачались</th><th class="num">Объём</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function reasonsCard(d) {
  const list = d.reasons.map((r) => `<li data-code="${esc(r.code)}"><b class="r-num">${num(r.count)}</b>
    <div class="min0"><b>${esc(r.title)}</b><div class="tiny">${esc(r.hint)}</div></div></li>`).join('');
  const body = list ? `<ul class="reasons">${list}</ul><div class="row mt-12">
      <button class="btn small" data-act="retry" ${isBusy(state.job) ? 'disabled' : ''}>${icon('refresh')}Попробовать ещё раз</button>
      <span class="tiny">Файлы вернутся в очередь; нажмите «Сохранить ещё раз», чтобы скачать их.</span></div>`
    : `<p class="muted">Все файлы, которые программа уже пробовала, скачались.</p>`;
  const waiting = mediaTotals(d).waiting;
  const note = waiting ? `<p class="tiny mt-12">Ещё ${plural(waiting, 'файл ждёт', 'файла ждут', 'файлов ждут')} серверов ВК: они не потеряны,
    программа пробует их снова каждые 10 минут, пока открыта.</p>` : '';
  return `<div class="card" id="dash-reasons"><h2>Почему файлы не скачались</h2>${body}${note}</div>`;
}

function archiveCard(d) {
  const a = d.archive;
  let body;
  if (!a.path) body = `<p class="muted">Архив ещё не указан.</p>`;
  else if (!a.exists) body = `<p><code>${esc(a.path)}</code></p><p class="warn-text">Архива по этому пути нет: его переместили или удалили.</p>`;
  else {
    const age = a.age_days === 0 ? 'сегодня' : plural(a.age_days, 'день', 'дня', 'дней') + ' назад';
    body = `<div class="path-row"><code>${esc(a.path)}</code>${copyBtn(a.path, 'путь к архиву')}</div>
      <dl class="facts-list">${a.size != null ? `<dt>Размер</dt><dd>${bytes(a.size)}</dd>` : ''}
        <dt>Скачан с ВК</dt><dd>${esc(when(a.modified))} · ${esc(age)}</dd>
        ${d.imported_at ? `<dt>Разобран программой</dt><dd>${esc(when(d.imported_at))}</dd>` : ''}</dl>`;
  }
  return `<div class="card" id="dash-archive"><div class="card-head"><span class="sec-ico">${icon('archive')}</span>
    <div class="grow"><h2>Архив ВК</h2><div class="tiny">ZIP-файл или папка, которые прислал ВК</div></div>
    <a class="btn small" href="#/setup">Изменить</a></div>${body}</div>`;
}

function folderCard(d) {
  const f = d.folder;
  const busy = isBusy(state.job) ? 'disabled' : '';
  let disk = '';
  if (f.disk_total) {
    const used = f.disk_total - f.disk_free;
    disk = `<div class="disk mt-12">${stackBar([['used', used], ['p', f.disk_free]], `Диск занят на ${Math.round(used * 100 / f.disk_total)}%`)}
      <div class="tiny mt-8">на диске свободно ${bytes(f.disk_free)} из ${bytes(f.disk_total)}</div></div>`;
  }
  const open = f.index ? `<a class="btn small" href="/archive/index.html" target="_blank" rel="noopener">${icon('external')}Открыть архив</a>` : '';
  return `<div class="card" id="dash-folder"><div class="card-head"><span class="sec-ico">${icon('disk')}</span>
    <div class="grow"><h2>Папка с результатом</h2><div class="tiny">Страницы архива, фото и база vk_backup.db</div></div></div>
    <div class="path-row"><code>${esc(f.path)}</code>${copyBtn(f.path, 'путь к папке')}</div>
    ${d.ready ? `<dl class="facts-list"><dt>Фото и файлы</dt><dd>${bytes(f.files_bytes)}</dd><dt>База</dt><dd>${bytes(f.db_bytes)}</dd></dl>` : ''}
    ${disk}
    <div class="row mt-14">${open}
      <button class="btn small" data-act="open-folder" ${f.exists ? '' : 'disabled'}>${icon('folder')}Открыть папку</button>
      <button class="btn small" data-act="render" ${d.ready ? busy : 'disabled'} title="Собрать страницы архива из базы заново">${icon('refresh')}Пересобрать страницы</button></div></div>`;
}

function runsCard(d) {
  if (!d.runs.length) return `<div class="card" id="dash-runs"><h2>История запусков</h2><p class="muted">Запусков ещё не было.</p></div>`;
  const job = state.job;
  const rows = d.runs.map((r) => {
    // «running» в истории: либо этот самый запуск идёт сейчас, либо программу закрыли посреди него
    const live = r.state === 'running' && isBusy(job) && job.started_at === r.started_at;
    const [cls, label] = live ? ['live', 'Идёт'] : r.state === 'running' ? ['wait', 'Прерван'] : RUN_PILL[r.state] || ['', r.state];
    const took = r.started_at && r.finished_at ? duration(r.finished_at - r.started_at) : live ? duration(Date.now() / 1000 - r.started_at) : '—';
    return `<tr><td>${r.started_at ? esc(when(r.started_at)) : '—'}</td><td>${esc(took)}</td>
      <td><span class="pill sm ${cls}" ${r.problem_text ? `title="${esc(r.problem_text)}"` : ''}><span class="pdot"></span>${esc(label)}</span></td>
      <td class="num">${r.download === false ? 'без файлов' : num(r.files)}</td><td class="num">${r.download === false ? '—' : bytes(r.bytes)}</td></tr>`;
  }).join('');
  return `<div class="card" id="dash-runs"><h2>История запусков</h2><div class="t-wrap" tabindex="0" role="region" aria-label="История запусков"><table class="t">
    <thead><tr><th>Начат</th><th>Длился</th><th>Итог</th><th class="num">Скачано</th><th class="num">Объём</th></tr></thead>
    <tbody>${rows}</tbody></table></div></div>`;
}

function networkCard(d) {
  const n = d.network;
  return `<div class="card" id="dash-network"><div class="card-head"><span class="sec-ico${n.installed ? '' : ' bad'}">${icon('wifi')}</span>
    <div class="grow"><h2>Сеть</h2><div class="tiny">${n.installed ? 'Сетевой замок включён: только файловые серверы ВК' : 'Сетевой замок выключен — перезапустите программу'}</div></div></div>
    <div class="mini-stats"><div><b>${num(n.hosts)}</b><span>${word(n.hosts, 'сервер ВК', 'сервера ВК', 'серверов ВК')}</span></div>
      <div><b>${num(n.requests)}</b><span>${word(n.requests, 'запрос', 'запроса', 'запросов')}</span></div>
      <div><b>${num(n.blocked)}</b><span>не пущено замком</span></div></div>
    <p class="mt-12"><a href="#/security">Подробнее о безопасности →</a></p></div>`;
}

function renderDashboard() {
  const el = $('#screen-dashboard');
  const head = `<div class="page-head"><div><h1>Панель</h1>
    <p class="muted">Всё об архиве на одном экране: что сохранено, что ещё качается и почему, сколько места.</p></div>
    <button class="btn" data-act="dash-refresh">${icon('refresh')}Обновить</button></div>`;
  if (!dash && dashError) {
    el.innerHTML = `<div class="stack">${head}<div class="card err" role="alert">Не получилось загрузить панель: ${esc(dashError)}.
      Нажмите «Обновить», чтобы попробовать ещё раз.</div></div>`;
    return;
  }
  if (!dash) {
    el.innerHTML = `<div class="stack">${head}<div class="card"><p class="muted">Загружаю…</p></div></div>`;
    loadDashboard(true);
    return;
  }
  if (!dash.ready) {
    el.innerHTML = `<div class="stack">${head}<div class="card empty">${icon('grid')}Архива ещё нет — панель заполнится после первого бэкапа.<br>
      <a href="#/setup">Перейти к настройке</a></div><div class="dash-2">${archiveCard(dash)}${folderCard(dash)}</div>${networkCard(dash)}</div>`;
    return;
  }
  el.innerHTML = `<div class="stack">${head}${kpis(dash)}
    <div class="dash-2">${readinessCard(dash)}${nowCard(state)}</div>${fiveCard(dash)}
    ${filesCard(dash)}${reasonsCard(dash)}
    <div class="dash-2">${archiveCard(dash)}${folderCard(dash)}</div>
    <div class="dash-2">${runsCard(dash)}${networkCard(dash)}</div></div>`;
}

onAct('dash-refresh', () => loadDashboard(true));
onAct('render', () => act('/api/render', {}));
