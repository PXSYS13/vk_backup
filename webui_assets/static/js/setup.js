// Настройка: три шага — заказать архив, указать его и папку, сохранить.
'use strict';

// Что нашлось в «Загрузках» и что ответила программа на «Сохранить» — переживает перерисовку
const setupUi = {found: null, note: '', error: ''};

function stepCard(n, done, title, body) {
  return `<div class="card"><div class="step${done ? ' done' : ''}"><span class="step-num">${done ? '✓' : n}</span>
    <div class="step-body"><h2>${title}</h2>${body}</div></div></div>`;
}

function foundList(current) {
  const list = setupUi.found;
  if (!list || list.length < 2) return '';
  const items = list.map((a) => {
    const name = a.path.split(/[\\/]/).pop();
    const on = a.path === current;
    return `<button type="button" class="found-item${on ? ' on' : ''}" data-act="pick-archive" data-path="${esc(a.path)}" aria-pressed="${on}">
      <span class="found-ico">${icon(on ? 'check' : 'archive')}</span><span class="min0"><b>${esc(name)}</b>
      <span class="tiny">${bytes(a.size)}${a.modified ? ` · скачан ${esc(when(a.modified))}` : ''}</span></span></button>`;
  }).join('');
  return `<div class="found-list" role="group" aria-label="Найденные архивы ВК">${items}</div>`;
}

function renderSetup() {
  const s = state;
  const set = form || s.settings;
  const running = isBusy(s.job);
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
      <input type="text" id="f-archive" value="${esc(set.archive)}" placeholder="C:\\Users\\…\\Downloads\\Archive.zip" spellcheck="false" ${dis}></label>
    <div class="row"><button class="btn small" data-act="find" ${dis}>${icon('search')}Найти в «Загрузках»</button><span class="tiny" id="found" aria-live="polite">${esc(setupUi.note)}</span></div>
    ${foundList(set.archive)}
    <label class="field"><span>Куда сохранить архив с фото и страницами</span>
      <input type="text" id="f-folder" value="${esc(set.folder)}" spellcheck="false" ${dis}></label>
    <div class="field"><span>Что сохранить</span><div class="checks">${checks}</div></div>
    <label class="check"><input type="checkbox" id="f-download" ${set.download ? 'checked' : ''} ${dis}>
      Скачать фото, голосовые и файлы по ссылкам из архива</label>
    <p class="tiny under-check">В архиве ВК фото и голосовые — ссылками. Без этой галочки программа
      не выходит в интернет вообще и делает страницы только из текста.</p>
    ${setupUi.error ? `<div class="form-error" id="setup-error" role="alert">${icon('alert')}<span>${esc(setupUi.error)}</span></div>` : ''}`);
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

// Перерисовать настройку сейчас, сохранив то, что человек уже ввёл
function redrawSetup() {
  form = readForm() || form;
  keepFocus($('#screen-setup'), renderSetup);
  markBusy($('#screen-setup'));
}

async function saveSettings() {
  try {
    const res = await api('/api/settings', readForm());
    setupUi.error = '';
    form = null;
    toast(res.msg);
    await refresh();
    redrawSetup();
    return true;
  } catch (e) {
    setupUi.error = e.message;
    toast(e.message, 'err');
    redrawSetup();
    return false;
  }
}

onAct('save', saveSettings);
onAct('save-start', async () => {
  if (await saveSettings() && await act('/api/start', {})) location.hash = '#/home';
});
onAct('find', async () => {
  setupUi.note = 'Ищу…';
  setupUi.found = null;
  redrawSetup();
  try {
    const d = await api('/api/find-archives');
    setupUi.found = d.archives;
    if (!d.archives.length) {
      setupUi.note = `В папке ${d.folder} архивов ВК не нашлось`;
    } else {
      form = {...(readForm() || state.settings), archive: d.archives[0].path};
      setupUi.note = d.archives.length > 1 ? `Нашлось ${d.archives.length} — взял самый свежий, можно выбрать другой` : 'Нашёл';
    }
  } catch (err) {
    setupUi.note = err.message;
  }
  keepFocus($('#screen-setup'), renderSetup);
});
onAct('pick-archive', (btn) => {
  form = {...(readForm() || state.settings), archive: btn.dataset.path};
  keepFocus($('#screen-setup'), renderSetup);
});
