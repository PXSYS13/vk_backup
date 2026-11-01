// «Мой ВКонтакте в цифрах»: годы, собеседники, часы, дни недели — по базе на этом компьютере.
'use strict';

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
    <div class="grid-2">${yearBars(s.friends_by_year, 'Новые друзья по годам')}${yearBars(s.photos_by_year, 'Фото в альбомах по годам')}</div>${thanksCard(s, years)}</div>`;
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
