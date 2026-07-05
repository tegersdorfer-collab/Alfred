export type LogEntry = { speaker: 'user' | 'alfred'; text: string };

export const MAX_LOG_ENTRIES = 12;

function ensureContainer(): HTMLElement {
  let el = document.getElementById('conversation-log');
  if (!el) {
    el = document.createElement('div');
    el.id = 'conversation-log';
    document.body.appendChild(el);
  }
  return el;
}

export function appendToLog(entry: LogEntry): void {
  const text = entry.text.trim();
  if (!text) return;

  const container = ensureContainer();
  const line = document.createElement('div');
  line.className = `log-entry log-${entry.speaker}`;
  const prefix = entry.speaker === 'user' ? '🗣️' : '🔊';
  line.textContent = `${prefix} ${text}`;
  container.appendChild(line);

  while (container.children.length > MAX_LOG_ENTRIES) {
    container.removeChild(container.firstElementChild!);
  }
  container.scrollTop = container.scrollHeight;
}
