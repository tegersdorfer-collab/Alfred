export const DEFAULT_BASE_URL = 'http://macbook-air-von-timo.tail7e29ff.ts.net:7779';

const STORAGE_KEY = 'alfred_base_url';

export function getBaseUrl(): string {
  return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_BASE_URL;
}

export function setBaseUrl(url: string): void {
  localStorage.setItem(STORAGE_KEY, url.replace(/\/+$/, ''));
}
