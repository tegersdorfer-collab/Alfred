const TARGET_SAMPLE_RATE = 16000;

class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // `sampleRate` is the AudioWorkletGlobalScope's actual running rate — NOT
    // guaranteed to equal the `{ sampleRate: 16000 }` hint passed to the
    // AudioContext constructor in voice-capture-stream.ts. Some WebKit/webview
    // builds (Tauri's macOS webview in particular) silently ignore that hint
    // and run at the hardware's native rate (44100/48000) instead — without
    // this resampler, every downstream 16kHz-PCM consumer (Silero VAD,
    // openWakeWord) would receive audio at the wrong effective pitch/speed and
    // detect nothing at all, regardless of how loud or clear the speech is.
    this._ratio = TARGET_SAMPLE_RATE / sampleRate;
    this._carry = 0; // fractional leftover position between process() calls, for continuity across blocks
  }

  process(inputs) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0];
      const resampled = this._resample(channelData);
      const pcm16 = new Int16Array(resampled.length);
      for (let i = 0; i < resampled.length; i++) {
        const s = Math.max(-1, Math.min(1, resampled[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      if (pcm16.length > 0) {
        this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
      }
    }
    return true;
  }

  // Lineare Interpolation, kein-Op wenn sampleRate bereits 16000 ist (ratio=1).
  _resample(input) {
    if (this._ratio === 1) return input;

    const outLength = Math.floor(input.length * this._ratio + this._carry);
    const output = new Float32Array(Math.max(0, outLength));
    let srcPos = 0;
    for (let i = 0; i < output.length; i++) {
      srcPos = i / this._ratio;
      const i0 = Math.floor(srcPos);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = srcPos - i0;
      output[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    // Restposition für nahtlose Fortsetzung im nächsten process()-Aufruf merken
    this._carry = input.length * this._ratio - output.length;
    return output;
  }
}
registerProcessor('pcm-worklet', PCMWorkletProcessor);
