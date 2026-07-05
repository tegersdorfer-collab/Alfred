export function initChatInput(baseUrl: string, onReply: (text: string) => void): void {
  const wrap = document.createElement('div');
  wrap.id = 'chat-input-wrap';
  wrap.innerHTML = `<input type="text" id="chat-input" placeholder="Nachricht an Alfred …" autocomplete="off" />`;
  document.body.appendChild(wrap);

  const input = wrap.querySelector<HTMLInputElement>('#chat-input')!;

  input.addEventListener('keydown', async (e) => {
    if (e.key !== 'Enter') return;
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.disabled = true;
    try {
      const res = await fetch(`${baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      onReply(data.response ?? '');
    } catch {
      onReply('Fehler beim Senden — Verbindung zu Alfred geprüft?');
    } finally {
      input.disabled = false;
      input.focus();
    }
  });
}
