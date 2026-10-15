/* Preferencja dotyczy wyłącznie wyglądu na tym urządzeniu. */
(() => {
  const root = document.documentElement;
  const storageKey = "parliament-theme";
  let toggle;

  function apply(theme) {
    const dark = theme === "dark";
    root.dataset.theme = dark ? "dark" : "light";
    if (toggle) {
      const label = dark ? "Włącz motyw dzienny" : "Włącz motyw nocny";
      toggle.setAttribute("aria-pressed", String(dark));
      toggle.setAttribute("aria-label", label);
      toggle.title = label;
    }
  }

  // Wczytaj preferencję przed CSS, aby uniknąć błysku jasnego tła.
  let theme = "light";
  try {
    if (localStorage.getItem(storageKey) === "dark") theme = "dark";
  } catch (_) {
    // Brak dostępu do pamięci przeglądarki nie blokuje przełącznika.
  }
  apply(theme);

  document.addEventListener("DOMContentLoaded", () => {
    toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    apply(root.dataset.theme);
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(storageKey, next); } catch (_) {}
    });
  });

  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === null) {
      apply(event.key === storageKey ? event.newValue : "light");
    }
  });
})();
