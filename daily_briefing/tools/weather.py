"""Weather tool — formats Open-Meteo data for the daily briefing."""

from __future__ import annotations

import requests

from daily_briefing.apis.open_meteo import WMO_CODES, fetch_forecast

_FORECAST_HOURS: dict[int, str] = {
    8: "Morning (8am)",
    13: "Afternoon (1pm)",
    18: "Evening (6pm)",
}


def get_weather(
    latitude: float = 42.96,
    longitude: float = -85.67,
) -> str:
    """Fetch current conditions plus morning/afternoon/evening forecasts.

    Args:
        latitude: Latitude of the location. Default is Grand Rapids, MI.
        longitude: Longitude of the location. Default is Grand Rapids, MI.

    Returns:
        Multi-line string with current conditions and three forecast periods.
    """
    try:
        data = fetch_forecast(latitude, longitude)
    except requests.RequestException as exc:
        # Degrade gracefully — one upstream failure must not abort the whole briefing.
        return f"Weather unavailable: {type(exc).__name__}: {exc}"

    current = data["current"]
    temp = round(current["temperature_2m"])
    code = int(current["weathercode"])
    wind = round(current["windspeed_10m"])
    condition = WMO_CODES.get(code, f"code {code}")
    lines = [f"Now: {temp}°F, {condition}, wind {wind} mph"]

    hourly = data.get("hourly", {})
    h_times: list[str] = hourly.get("time", [])
    h_temps: list[float] = hourly.get("temperature_2m", [])
    h_codes: list[int] = hourly.get("weathercode", [])
    h_winds: list[float] = hourly.get("windspeed_10m", [])

    for i, t in enumerate(h_times):
        hour = int(t[11:13])
        if hour in _FORECAST_HOURS:
            f_temp = round(h_temps[i])
            f_code = int(h_codes[i])
            f_wind = round(h_winds[i])
            f_cond = WMO_CODES.get(f_code, f"code {f_code}")
            lines.append(f"{_FORECAST_HOURS[hour]}: {f_temp}°F, {f_cond}, wind {f_wind} mph")

    return "\n".join(lines)
