/* Komunikat informacyjny, bez zbierania zgód na reklamę lub analitykę. */
(() => {
  const notice = document.getElementById('storage-notice');
  const closer = document.getElementById('storage-notice-close');
  const details = document.getElementById('browser-storage');
  if (!notice || !closer) return;
  const key = 'parliament-storage-notice-v1';
  let dismissed = false;
  try { dismissed = localStorage.getItem(key) === 'dismissed'; } catch (_) {}
  notice.hidden = dismissed;

  closer.addEventListener('click', () => {
    notice.hidden = true;
    try { localStorage.setItem(key, 'dismissed'); } catch (_) {}
    // Ukryty przycisk nie powinien zatrzymać fokusu klawiatury.
    const summary = details?.querySelector('summary');
    if (summary) summary.focus({preventScroll: true});
  });
  document.getElementById('storage-notice-details')?.addEventListener('click', () => {
    if (details) details.open = true;
  });
})();
