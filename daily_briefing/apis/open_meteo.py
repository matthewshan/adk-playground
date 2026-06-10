"""Open-Meteo API client — no key required."""

from __future__ import annotations

import time

import requests

# Open-Meteo occasionally returns transient 5xx/429s; retry those before giving up.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}

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
    retries: int = 2,
) -> dict:
    """Fetch current conditions and hourly forecast from Open-Meteo.

    Retries transient server errors (429/5xx and connection/timeout failures)
    with exponential backoff so a single upstream hiccup doesn't blank out the
    weather section of the briefing.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        timezone: IANA timezone name used to align the hourly data.
        forecast_days: Number of forecast days to request.
        retries: Extra attempts after the first on transient failures.

    Returns:
        Raw Open-Meteo JSON response dict with 'current' and 'hourly' keys.

    Raises:
        requests.RequestException: On non-transient or final-attempt errors.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weathercode,windspeed_10m",
        "hourly": "temperature_2m,weathercode,windspeed_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": timezone,
        "forecast_days": forecast_days,
    }
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/forecast", params=params, timeout=10
            )
            if resp.status_code in _TRANSIENT_STATUS and attempt < retries:
                time.sleep(2**attempt)  # 1s, then 2s
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt >= retries:
                raise
            time.sleep(2**attempt)
    # Unreachable: the loop either returns or raises on the final attempt.
    raise requests.RequestException("Open-Meteo request failed after retries")
