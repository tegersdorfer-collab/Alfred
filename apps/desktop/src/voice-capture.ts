export type VoiceSegmentResult = { text: string; addressed: boolean };

const SILENCE_THRESHOLD = 0.02;   // RMS-Lautstärke-Schwelle (0..1)
const SILENCE_MS_TO_STOP = 800;   // so lange Stille beendet ein Sprachsegment
const MIN_SEGMENT_MS = 300;       // kürzere "Segmente" werden verworfen (Rauschen)

export function startVoiceCapture(
  baseUrl: string,
  onSegment: (result: VoiceSegmentResult) => void,
): () => void {
  let stopped = false;
  let stream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let recorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let speaking = false;
  let silenceStartedAt: number | null = null;
  let segmentStartedAt = 0;
  let rafId: number | null = null;

  function extensionFor(mimeType: string): string {
    if (mimeType.includes('mp4')) return 'm4a';
    if (mimeType.includes('ogg')) return 'ogg';
    if (mimeType.includes('wav')) return 'wav';
    return 'webm';
  }

  async function uploadSegment(blob: Blob, mimeType: string): Promise<void> {
    try {
      const form = new FormData();
      form.append('audio', blob, `segment.${extensionFor(mimeType)}`);
      const res = await fetch(`${baseUrl}/api/voice/segment`, { method: 'POST', body: form });
      const data = (await res.json()) as VoiceSegmentResult;
      onSegment(data);
    } catch {
      // Netzwerkfehler beim Upload — Segment geht verloren, kein Absturz
    }
  }

  function rms(data: Uint8Array): number {
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / data.length);
  }

  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((mediaStream) => {
      if (stopped) {
        mediaStream.getTracks().forEach((t) => t.stop());
        return;
      }
      stream = mediaStream;
      audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);

      function tick(): void {
        if (stopped || !audioCtx) return;
        analyser.getByteTimeDomainData(data);
        const level = rms(data);
        const now = performance.now();

        if (level > SILENCE_THRESHOLD) {
          silenceStartedAt = null;
          if (!speaking) {
            speaking = true;
            segmentStartedAt = now;
            chunks = [];
            recorder = new MediaRecorder(stream!);
            recorder.ondataavailable = (e) => chunks.push(e.data);
            recorder.start();
          }
        } else if (speaking) {
          if (silenceStartedAt === null) silenceStartedAt = now;
          if (now - silenceStartedAt >= SILENCE_MS_TO_STOP) {
            speaking = false;
            const duration = now - segmentStartedAt;
            const activeRecorder = recorder;
            recorder = null;
            if (activeRecorder && activeRecorder.state !== 'inactive') {
              activeRecorder.onstop = () => {
                if (duration >= MIN_SEGMENT_MS) {
                  const mimeType = activeRecorder.mimeType || 'audio/webm';
                  uploadSegment(new Blob(chunks, { type: mimeType }), mimeType);
                }
              };
              activeRecorder.stop();
            }
          }
        }
        rafId = requestAnimationFrame(tick);
      }
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => {
      // Mikrofon-Zugriff verweigert/nicht verfügbar — Voice-Capture bleibt inaktiv, kein Absturz
    });

  return () => {
    stopped = true;
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (audioCtx) audioCtx.close();
  };
}
