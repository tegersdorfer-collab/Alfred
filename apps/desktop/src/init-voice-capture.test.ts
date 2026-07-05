import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./voice-capture', () => ({
  startVoiceCapture: vi.fn(() => 'stop-http'),
}));
vi.mock('./voice-capture-stream', () => ({
  startVoiceCaptureStream: vi.fn(() => 'stop-ws'),
}));

// main.ts has heavy top-level side effects (subscribes to UI state, wires up
// HUD chrome, etc.) that run on import. We only need initVoiceCapture here,
// so we import it the same way main.test.ts does, relying on jsdom to
// tolerate the rest of main.ts's module-level setup.
import { initVoiceCapture } from './main';
import { startVoiceCapture } from './voice-capture';
import { startVoiceCaptureStream } from './voice-capture-stream';

describe('initVoiceCapture', () => {
  const baseUrl = 'http://localhost:9999';
  const onSegment = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('falls back to startVoiceCapture when the stream-mode fetch rejects', async () => {
    (fetch as any).mockRejectedValue(new Error('network down'));

    await initVoiceCapture(baseUrl, onSegment);

    expect(startVoiceCapture).toHaveBeenCalledWith(baseUrl, onSegment);
    expect(startVoiceCaptureStream).not.toHaveBeenCalled();
  });

  it('uses startVoiceCapture when the mode resolves to "http"', async () => {
    (fetch as any).mockResolvedValue({ json: async () => ({ mode: 'http' }) });

    await initVoiceCapture(baseUrl, onSegment);

    expect(startVoiceCapture).toHaveBeenCalledWith(baseUrl, onSegment);
    expect(startVoiceCaptureStream).not.toHaveBeenCalled();
  });

  it('uses startVoiceCaptureStream when the mode resolves to "websocket"', async () => {
    (fetch as any).mockResolvedValue({ json: async () => ({ mode: 'websocket' }) });

    await initVoiceCapture(baseUrl, onSegment);

    expect(startVoiceCaptureStream).toHaveBeenCalledWith(baseUrl, onSegment);
    expect(startVoiceCapture).not.toHaveBeenCalled();
  });

  it('treats any non-"websocket" mode value as the http fallback', async () => {
    (fetch as any).mockResolvedValue({ json: async () => ({ mode: 'something-else' }) });

    await initVoiceCapture(baseUrl, onSegment);

    expect(startVoiceCapture).toHaveBeenCalledWith(baseUrl, onSegment);
    expect(startVoiceCaptureStream).not.toHaveBeenCalled();
  });
});
