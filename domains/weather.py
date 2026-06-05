"""
Wetter-Domäne via Open-Meteo (kostenlos, kein API-Key).
Stadt wird aus den Settings gelesen (Default: Berlin).
"""
import httpx

from core import db

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "klar", 1: "überwiegend klar", 2: "teils bewölkt", 3: "bedeckt",
    45: "Nebel", 48: "Reifnebel", 51: "leichter Niesel", 53: "Niesel", 55: "starker Niesel",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen",
    71: "leichter Schnee", 73: "Schnee", 75: "starker Schnee",
    80: "Regenschauer", 81: "Schauer", 82: "heftige Schauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "schweres Gewitter",
}


async def _city() -> str:
    return db.get_setting("weather_city", "Berlin") or "Berlin"


async def get_weather(city: str | None = None) -> dict:
    city = city or await _city()
    async with httpx.AsyncClient(timeout=10) as c:
        g = await c.get(GEOCODE, params={"name": city, "count": 1, "language": "de"})
        results = g.json().get("results")
        if not results:
            return {"error": f"Stadt '{city}' nicht gefunden"}
        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        f = await c.get(FORECAST, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
            "timezone": "Europe/Berlin", "forecast_days": 3,
        })
        data = f.json()

    cur = data.get("current", {})
    daily = data.get("daily", {})
    days = []
    for i in range(len(daily.get("time", []))):
        days.append({
            "date": daily["time"][i],
            "max": daily["temperature_2m_max"][i],
            "min": daily["temperature_2m_min"][i],
            "code": WMO.get(daily["weather_code"][i], "?"),
            "rain_prob": daily.get("precipitation_probability_max", [None]*9)[i],
        })
    return {
        "city": loc["name"],
        "now": {
            "temp": cur.get("temperature_2m"),
            "feels": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind": cur.get("wind_speed_10m"),
            "desc": WMO.get(cur.get("weather_code"), "?"),
        },
        "forecast": days,
    }
