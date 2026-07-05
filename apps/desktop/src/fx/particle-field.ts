type Particle = { x: number; y: number; r: number; vx: number; vy: number; alpha: number };

export function startParticleField(
  canvas: HTMLCanvasElement,
  options: { density?: number; tint?: string } = {},
): () => void {
  const density = options.density ?? 60;
  const tint = options.tint ?? '#00e5ff';
  const ctx = canvas.getContext('2d');
  if (!ctx) return () => {};

  const particles: Particle[] = Array.from({ length: density }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    r: Math.random() * 1.4 + 0.3,
    vx: (Math.random() - 0.5) * 0.08,
    vy: (Math.random() - 0.5) * 0.08,
    alpha: Math.random() * 0.5 + 0.1,
  }));

  let frameId = 0;
  let running = true;

  function draw(): void {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      p.x = (p.x + p.vx + canvas.width) % canvas.width;
      p.y = (p.y + p.vy + canvas.height) % canvas.height;
      ctx.beginPath();
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = tint;
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function tick(): void {
    if (!running) return;
    if (document.hidden) {
      running = false;
      return;
    }
    draw();
    frameId = requestAnimationFrame(tick);
  }

  function handleVisibility(): void {
    if (document.hidden) {
      running = false;
      cancelAnimationFrame(frameId);
    } else if (!running) {
      running = true;
      frameId = requestAnimationFrame(tick);
    }
  }

  document.addEventListener('visibilitychange', handleVisibility);
  frameId = requestAnimationFrame(tick);

  return () => {
    running = false;
    cancelAnimationFrame(frameId);
    document.removeEventListener('visibilitychange', handleVisibility);
  };
}
