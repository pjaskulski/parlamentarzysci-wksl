(() => {
  const dialog = document.getElementById('app-help-dialog');
  const opener = document.getElementById('app-help-open');
  if (!dialog || !opener || typeof dialog.showModal !== 'function') return;
  opener.addEventListener('click', () => {
    dialog.showModal();
    dialog.scrollTop = 0;
    document.body.classList.add('app-help-is-open');
  });
  document.getElementById('app-help-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    document.body.classList.remove('app-help-is-open');
    opener.focus();
  });
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
  document.getElementById('app-help-search').addEventListener('click', event => {
    const search = document.getElementById('search-help-open');
    if (!search) return;
    event.preventDefault();
    dialog.close();
    search.click();
  });
})();
