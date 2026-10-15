(() => {
  const field = document.getElementById('q');
  const form = field?.form;
  if (!form || !field.defaultValue.trim()) return;
  let submitting = false;
  function refreshWhenCleared() {
    if (field.value !== '' || submitting) return;
    submitting = true;
    form.requestSubmit();
  }
  field.addEventListener('input', refreshWhenCleared);
  field.addEventListener('search', refreshWhenCleared);
})();
