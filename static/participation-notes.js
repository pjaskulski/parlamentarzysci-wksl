(() => {
  const dialog = document.getElementById('participation-dialog');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  let opener;
  document.querySelectorAll('.participation-note > summary').forEach(summary => {
    summary.setAttribute('aria-haspopup', 'dialog');
    summary.addEventListener('click', event => {
      event.preventDefault();
      opener = summary;
      dialog.querySelector('h2').textContent = summary.dataset.noteTitle;
      document.getElementById('participation-dialog-text').textContent = Array.from(summary.nextElementSibling.querySelectorAll('p')).map(p => p.textContent.trim()).join('\n\n');
      dialog.showModal();
      document.body.classList.add('participation-dialog-open');
    });
  });
  dialog.querySelector('button').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    document.body.classList.remove('participation-dialog-open');
    opener?.focus();
  });
  dialog.addEventListener('click', event => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right ||
        event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
})();
