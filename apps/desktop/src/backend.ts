export type HealthStatus = { ok: boolean; checks?: Record<string, string> };

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryFetchHealth(
  baseUrl: string,
  fetchImpl: typeof fetch,
): Promise<HealthStatus> {
  const res = await fetchImpl(`${baseUrl}/health`, { method: 'GET' });
  const data = await res.json();
  return { ok: !!data.ok, checks: data.checks };
}

export async function checkBackendHealth(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): Promise<HealthStatus> {
  try {
    return await tryFetchHealth(baseUrl, fetchImpl);
  } catch {
    await delay(1500);
    try {
      return await tryFetchHealth(baseUrl, fetchImpl);
    } catch {
      return { ok: false };
    }
  }
}
