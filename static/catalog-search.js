(() => {
  const role = document.getElementById('role');
  const territory = document.getElementById('territory');
  if (!role || !territory) return;
  function updateTerritory() {
    territory.disabled = role.value !== 'poseł';
    if (territory.disabled) territory.value = '';
  }
  role.addEventListener('change', updateTerritory);
  updateTerritory();
})();
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
