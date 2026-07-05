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

export function staggerIn(
  elements: NodeListOf<HTMLElement> | HTMLElement[],
  delayStepMs = 60,
): void {
  Array.from(elements).forEach((el, i) => {
    el.classList.add('stagger-in');
    el.style.animationDelay = `${i * delayStepMs}ms`;
  });
}

export function drawIn(pathEl: SVGPathElement, durationMs = 600): void {
  let length = 200;
  try {
    length = pathEl.getTotalLength();
  } catch {
    // jsdom has no SVG geometry engine; fallback length only affects test environments.
  }
  pathEl.style.strokeDasharray = `${length}`;
  pathEl.style.strokeDashoffset = `${length}`;
  pathEl.style.transition = `stroke-dashoffset ${durationMs}ms ease-out`;
  requestAnimationFrame(() => {
    pathEl.style.strokeDashoffset = '0';
  });
}
