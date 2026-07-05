"""Unit-Tests für domains/weather.py: Geocoding + Forecast (Open-Meteo)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from domains import weather


def _fake_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    return resp


class TestGetWeather:
    def test_gibt_lat_lon_der_stadt_zurueck(self, monkeypatch):
        geocode_response = _fake_response({
            "results": [{"name": "Nürnberg", "latitude": 49.4521, "longitude": 11.0767}]
        })
        forecast_response = _fake_response({
            "current": {
                "temperature_2m": 20.0, "apparent_temperature": 19.5,
                "relative_humidity_2m": 60, "wind_speed_10m": 10, "weather_code": 3,
            },
            "daily": {
                "time": ["2026-07-05"], "temperature_2m_max": [24.0], "temperature_2m_min": [18.0],
                "weather_code": [3], "precipitation_probability_max": [15],
            },
        })

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[geocode_response, forecast_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("domains.weather.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(weather.get_weather("Nürnberg"))

        assert result["lat"] == 49.4521
        assert result["lon"] == 11.0767
        assert result["city"] == "Nürnberg"
