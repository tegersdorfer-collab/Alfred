export function tweenNumber(
  el: HTMLElement,
  from: number,
  to: number,
  durationMs: number,
  format: (n: number) => string = (n) => String(n),
): void {
  if (durationMs <= 0) {
    el.textContent = format(to);
    return;
  }

  const start = performance.now();
  el.textContent = format(from);

  function step(nowMs: number): void {
    const elapsed = nowMs - start;
    const t = Math.min(1, elapsed / durationMs);
    const value = from + (to - from) * t;
    el.textContent = format(t >= 1 ? to : Math.round(value));
    if (t < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}
