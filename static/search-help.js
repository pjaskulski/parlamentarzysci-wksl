(() => {
  const dialog = document.getElementById('search-help-dialog');
  const opener = document.getElementById('search-help-open');
  const closer = document.getElementById('search-help-close');
  if (!dialog || !opener || !closer) return;
  opener.addEventListener('click', () => {
    dialog.showModal();
    dialog.scrollTop = 0;
    document.body.classList.add('search-help-is-open');
  });
  closer.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    document.body.classList.remove('search-help-is-open');
    opener.focus();
  });
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
})();
