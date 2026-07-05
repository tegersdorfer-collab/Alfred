export type Tone = { freq: number; durationMs: number; type: OscillatorType };

export const TONES: Record<string, Tone> = {
  widget: { freq: 880, durationMs: 90, type: 'sine' },
  alert: { freq: 660, durationMs: 140, type: 'triangle' },
  addressed: { freq: 1100, durationMs: 70, type: 'sine' },
};

let sharedCtx: AudioContext | null = null;

/** Nur für Tests — erzwingt eine frische AudioContext-Instanz beim nächsten playTone(). */
export function _resetForTests(): void {
  sharedCtx = null;
}

function getContext(): AudioContext | null {
  try {
    if (!sharedCtx) sharedCtx = new AudioContext();
    return sharedCtx;
  } catch {
    return null;
  }
}

export function playTone(tone: Tone): void {
  try {
    const ctx = getContext();
    if (!ctx) return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = tone.type;
    osc.frequency.setValueAtTime(tone.freq, ctx.currentTime);
    gain.gain.setValueAtTime(0.05, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + tone.durationMs / 1000);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + tone.durationMs / 1000);
  } catch {
    // Sound-Feedback ist rein kosmetisch — nie einen Crash riskieren
  }
}
