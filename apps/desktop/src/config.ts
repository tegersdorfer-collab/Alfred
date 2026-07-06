export const DEFAULT_BASE_URL = 'http://localhost:7779';

const STORAGE_KEY = 'mantis_base_url';

export function getBaseUrl(): string {
  return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_BASE_URL;
}

export function setBaseUrl(url: string): void {
  localStorage.setItem(STORAGE_KEY, url.replace(/\/+$/, ''));
}
