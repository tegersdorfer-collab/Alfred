import { describe, it, expect, vi } from 'vitest';
import { subscribeUiState } from './ui-state-client';
import type { EventSourceLike, UiEvent } from './ui-state-client';

class FakeEventSource implements EventSourceLike {
  onmessage: ((ev: { data: string }) => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  emit(data: object): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  close(): void {
    this.closed = true;
  }
}

describe('subscribeUiState', () => {
  it('verbindet sich mit der korrekten SSE-URL', () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => (created = new FakeEventSource(url));
    subscribeUiState('http://test:7779', () => {}, factory);
    expect(created!.url).toBe('http://test:7779/api/ui/stream');
  });

  it('leitet eingehende Multi-Slot-Events an den Callback weiter', () => {
    let received: UiEvent | null = null;
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', (evt) => { received = evt; }, factory);

    source!.emit({
      layout: 'single',
      slots: { main: { widget: 'sleep', payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] } } },
      ts: 123,
    });

    expect(received).toEqual({
      layout: 'single',
      slots: { main: { widget: 'sleep', payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] } } },
      ts: 123,
    });
  });

  it('ignoriert kaputtes JSON ohne zu werfen', () => {
    const onEvent = vi.fn();
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', onEvent, factory);

    source!.onmessage?.({ data: 'kein-json{{{' });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it('unsubscribe schließt die Verbindung', () => {
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    const unsubscribe = subscribeUiState('http://test:7779', () => {}, factory);

    unsubscribe();

    expect(source!.closed).toBe(true);
  });
});
