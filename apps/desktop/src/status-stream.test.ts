import { describe, it, expect, vi } from 'vitest';
import { subscribeStatus } from './status-stream';
import type { EventSourceLike, StatusEvent } from './status-stream';

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

describe('subscribeStatus', () => {
  it('verbindet sich mit der korrekten SSE-URL', () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => (created = new FakeEventSource(url));
    subscribeStatus('http://test:7779', () => {}, factory);
    expect(created!.url).toBe('http://test:7779/api/status/stream');
  });

  it('leitet Status-Events an den Callback weiter', () => {
    let received: StatusEvent | null = null;
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeStatus('http://test:7779', (evt) => { received = evt; }, factory);

    source!.emit({ type: 'autopilot', text: 'Guten Morgen!', detail: 'morning_briefing', ts: 123 });

    expect(received).toEqual({ type: 'autopilot', text: 'Guten Morgen!', detail: 'morning_briefing', ts: 123 });
  });

  it('ignoriert kaputtes JSON ohne zu werfen', () => {
    const onEvent = vi.fn();
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeStatus('http://test:7779', onEvent, factory);

    source!.onmessage?.({ data: 'kein-json{{{' });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it('unsubscribe schließt die Verbindung', () => {
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    const unsubscribe = subscribeStatus('http://test:7779', () => {}, factory);

    unsubscribe();

    expect(source!.closed).toBe(true);
  });
});
