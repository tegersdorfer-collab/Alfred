import { describe, it, expect, beforeEach } from 'vitest';
import { appendToLog, MAX_LOG_ENTRIES } from './conversation-log';

describe('appendToLog', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('erstellt den Log-Container beim ersten Eintrag', () => {
    appendToLog({ speaker: 'user', text: 'Wie war mein Schlaf?' });
    const container = document.getElementById('conversation-log');
    expect(container).toBeTruthy();
  });

  it('zeigt Sprecher und Text an', () => {
    appendToLog({ speaker: 'user', text: 'Wie war mein Schlaf?' });
    appendToLog({ speaker: 'alfred', text: 'Sehr gut, 8 Stunden.' });
    const entries = document.querySelectorAll('.log-entry');
    expect(entries.length).toBe(2);
    expect(entries[0].textContent).toContain('Wie war mein Schlaf?');
    expect(entries[1].textContent).toContain('Sehr gut, 8 Stunden.');
    expect(entries[0].className).toContain('log-user');
    expect(entries[1].className).toContain('log-alfred');
  });

  it('begrenzt die Historie auf MAX_LOG_ENTRIES', () => {
    for (let i = 0; i < MAX_LOG_ENTRIES + 5; i++) {
      appendToLog({ speaker: 'user', text: `Nachricht ${i}` });
    }
    const entries = document.querySelectorAll('.log-entry');
    expect(entries.length).toBe(MAX_LOG_ENTRIES);
    // älteste Einträge zuerst entfernt, neueste bleiben
    expect(entries[entries.length - 1].textContent).toContain(`Nachricht ${MAX_LOG_ENTRIES + 4}`);
  });

  it('ignoriert leeren Text', () => {
    appendToLog({ speaker: 'user', text: '' });
    expect(document.querySelectorAll('.log-entry').length).toBe(0);
  });
});
