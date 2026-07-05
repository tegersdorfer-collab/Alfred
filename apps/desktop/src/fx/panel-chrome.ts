const BRACKET_SVG = `
<svg class="panel-brackets" viewBox="0 0 100 100" preserveAspectRatio="none">
  <path class="bracket bracket-tl" d="M2,14 L2,2 L14,2" />
  <path class="bracket bracket-tr" d="M86,2 L98,2 L98,14" />
  <path class="bracket bracket-bl" d="M2,86 L2,98 L14,98" />
  <path class="bracket bracket-br" d="M98,86 L98,98 L86,98" />
</svg>`;

const GREEBLE_HTML = `<div class="panel-greeble">${Array.from({ length: 8 })
  .map(() => '<span></span>')
  .join('')}</div>`;

export function applyPanelChrome(el: HTMLElement, options: { greeble?: boolean } = {}): void {
  el.classList.add('panel-chrome');

  if (!el.querySelector('svg.panel-brackets')) {
    el.insertAdjacentHTML('afterbegin', BRACKET_SVG);
    const paths = el.querySelectorAll<SVGPathElement>('.panel-brackets .bracket');
    paths.forEach((path) => {
      let length = 200;
      try {
        length = path.getTotalLength();
      } catch {
        // jsdom has no SVG geometry engine; a fixed fallback is fine for dash-length purposes.
      }
      path.style.strokeDasharray = `${length}`;
      path.style.strokeDashoffset = `${length}`;
      path.getBoundingClientRect(); // force layout so the transition below actually animates
      path.style.transition = 'stroke-dashoffset 500ms ease-out';
      requestAnimationFrame(() => {
        path.style.strokeDashoffset = '0';
      });
    });
  }

  if (options.greeble && !el.querySelector('.panel-greeble')) {
    el.insertAdjacentHTML('beforeend', GREEBLE_HTML);
  }
}
