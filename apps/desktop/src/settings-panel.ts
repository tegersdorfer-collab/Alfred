import { getBaseUrl, setBaseUrl } from './config';

export function initSettingsPanel(): void {
  const panel = document.createElement('div');
  panel.id = 'settings-panel';
  panel.innerHTML = `
    <form id="settings-form">
      <label for="settings-base-url">Backend-Adresse (z.B. Tailscale-Hostname des Macs für Remote-Clients)</label>
      <input type="text" id="settings-base-url" autocomplete="off" /><span class="settings-status-dot"></span>
      <div class="settings-hint">Enter zum Speichern &amp; Neuladen · Escape zum Abbrechen</div>
    </form>
  `;
  document.body.appendChild(panel);

  const form = panel.querySelector<HTMLFormElement>('#settings-form')!;
  const input = panel.querySelector<HTMLInputElement>('#settings-base-url')!;

  function close(): void {
    panel.classList.remove('visible');
  }

  function open(): void {
    input.value = getBaseUrl();
    panel.classList.add('visible');
    input.focus();
    input.select();
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const url = input.value.trim();
    if (url) {
      setBaseUrl(url);
      close();
      location.reload();
    }
  });

  document.addEventListener('keydown', (e) => {
    const isToggle = (e.metaKey || e.ctrlKey) && e.key === ',';
    if (isToggle) {
      e.preventDefault();
      panel.classList.contains('visible') ? close() : open();
    } else if (e.key === 'Escape' && panel.classList.contains('visible')) {
      close();
    }
  });
}
