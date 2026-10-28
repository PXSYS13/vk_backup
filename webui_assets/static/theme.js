// Тема до отрисовки страницы: сохранённый выбор или тема системы. Без него страница мигала бы светлой.
(function () {
  var theme = null;
  try { theme = localStorage.getItem('vk-backup-theme'); } catch (e) { /* приватный режим */ }
  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
