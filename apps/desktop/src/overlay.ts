// Overlay-Framework — der gemeinsame Lebenszyklus aller Vollbild-Content-Ansichten
// (Health, Wissensgraph, …). Verallgemeinert das Muster, das SP4/SP3 pioniert haben:
// Vollbild-Container am body, öffnen per CustomEvent, schließen per Esc/close, Content
// über einen render-Callback. Plus eine Registry, aus der nav-overlay seine Kacheln
// baut — ein neues Overlay braucht damit nur eine Registrierung.

export interface OverlayOpts {
  id: string;
  openEvent: string;
  render: (container: HTMLElement, api: { close: () => void }) => void | Promise<void>;
  background?: string;
}

export interface OverlayHandle {
  open: () => void;
  close: () => void;
  el: HTMLElement;
}

export function createOverlay(opts: OverlayOpts): OverlayHandle {
  const el = document.createElement('div');
  el.id = opts.id;
  el.style.cssText =
    'position:fixed;inset:0;z-index:200;display:none;overflow:auto;color:#e8fbf7;' +
    `font-family:-apple-system,sans-serif;background:${opts.background ?? 'rgba(8,14,18,0.97)'}`;
  document.body.appendChild(el);

  const close = (): void => { el.style.display = 'none'; };
  const open = (): void => {
    el.style.display = 'block';
    void opts.render(el, { close });
  };

  document.addEventListener(opts.openEvent, () => open());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  return { open, close, el };
}

// ── Registry (nav-overlay liest hieraus seine Kacheln) ────────────────────────

export interface OverlayReg { key: string; label: string; openEvent: string; }

const REGISTRY: OverlayReg[] = [];

export function registerOverlay(reg: OverlayReg): void {
  if (!REGISTRY.some((r) => r.key === reg.key)) REGISTRY.push(reg);
}

export function getOverlays(): OverlayReg[] {
  return [...REGISTRY];
}

// Nur für Tests: Registry leeren.
export function _resetRegistry(): void {
  REGISTRY.length = 0;
}
