export async function fetchRadarFrameTimes(
  fetchImpl: typeof fetch = fetch,
): Promise<number[]> {
  try {
    const res = await fetchImpl('https://api.rainviewer.com/public/weather-maps.json');
    const data = await res.json();
    const past = data?.radar?.past;
    if (!Array.isArray(past)) return [];
    return past.slice(-4).map((frame: { time: number }) => frame.time);
  } catch {
    return [];
  }
}

export function radarTileUrl(time: number, z: number, x: number, y: number): string {
  return `https://tilecache.rainviewer.com/v2/radar/${time}/256/${z}/${x}/${y}/2/1_1.png`;
}
