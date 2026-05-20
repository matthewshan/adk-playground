"""Weather tool — Open-Meteo (no API key required)."""

from __future__ import annotations

import requests

_WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight showers",
    81: "moderate showers",
    82: "violent showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def get_weather(
    latitude: float = 42.96,
    longitude: float = -85.67,
) -> str:
    """Fetch current conditions plus morning/afternoon/evening forecasts using Open-Meteo.

    Args:
        latitude: Latitude of the location. Default is Grand Rapids, MI.
        longitude: Longitude of the location. Default is Grand Rapids, MI.

    Returns:
        Multi-line string with current conditions and three forecast periods.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weathercode,windspeed_10m",
        "hourly": "temperature_2m,weathercode,windspeed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/Detroit",
        "forecast_days": 1,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    current = data["current"]
    temp = round(current["temperature_2m"])
    code = int(current["weathercode"])
    wind = round(current["windspeed_10m"])
    condition = _WMO_CODES.get(code, f"code {code}")
    lines = [f"Now: {temp}°F, {condition}, wind {wind} mph"]

    hourly = data.get("hourly", {})
    h_times: list[str] = hourly.get("time", [])
    h_temps: list[float] = hourly.get("temperature_2m", [])
    h_codes: list[int] = hourly.get("weathercode", [])
    h_winds: list[float] = hourly.get("windspeed_10m", [])

    _FORECAST_HOURS: dict[int, str] = {
        8: "Morning (8am)",
        13: "Afternoon (1pm)",
        18: "Evening (6pm)",
    }
    for i, t in enumerate(h_times):
        hour = int(t[11:13])
        if hour in _FORECAST_HOURS:
            f_temp = round(h_temps[i])
            f_code = int(h_codes[i])
            f_wind = round(h_winds[i])
            f_cond = _WMO_CODES.get(f_code, f"code {f_code}")
            lines.append(f"{_FORECAST_HOURS[hour]}: {f_temp}°F, {f_cond}, wind {f_wind} mph")

    return "\n".join(lines)
