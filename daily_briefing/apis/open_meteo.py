"""Open-Meteo API client — no key required."""

from __future__ import annotations

import requests

WMO_CODES: dict[int, str] = {
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


def fetch_forecast(
    latitude: float,
    longitude: float,
    timezone: str = "America/Detroit",
    forecast_days: int = 1,
) -> dict:
    """Fetch current conditions and hourly forecast from Open-Meteo.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        timezone: IANA timezone name used to align the hourly data.
        forecast_days: Number of forecast days to request.

    Returns:
        Raw Open-Meteo JSON response dict with 'current' and 'hourly' keys.

    Raises:
        requests.RequestException: On network or HTTP errors.
    """
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weathercode,windspeed_10m",
            "hourly": "temperature_2m,weathercode,windspeed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": timezone,
            "forecast_days": forecast_days,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
