"""Copenhagen morning weather, fetched server-side from Open-Meteo.

One attempt per Copenhagen hour, normally from 08:00 to 11:00.
The optional Halloween mode keeps weather available throughout the day.
No dependencies; works with the server's Python 3.7+ baseline.
"""
import datetime as dt
import json
import math
import threading
import time
import urllib.parse
import urllib.request


UTC = dt.timezone.utc
SNOW_CODES = {71, 73, 75, 77, 85, 86}
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
RAIN_MM = 0.2
RAIN_PROBABILITY = 50
SNOW_CM = 0.1
COAT_FEELS_LIKE = 5
HOURLY_FIELDS = ("weather_code", "snowfall", "rain", "showers",
                 "precipitation_probability", "apparent_temperature")
PARAMS = {
    "latitude": 55.6761,
    "longitude": 12.5683,
    "current": "temperature_2m,apparent_temperature,weather_code,rain,showers,snowfall",
    "hourly": ",".join(HOURLY_FIELDS),
    "timezone": "Europe/Copenhagen",
    "timeformat": "unixtime",
    "forecast_days": 2,
}
FORECAST_URL = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(PARAMS)


def copenhagen_time(timestamp):
    """Apply Copenhagen's current EU DST rules even on hosts without tzdata.

    Since 1996: summer time starts/ends at 01:00 UTC on the last Sunday
    of March/October. This keeps Windows and Python 3.7 installs dependency-free.
    """
    utc = dt.datetime.fromtimestamp(timestamp, UTC)
    transitions = []
    for month in (3, 10):
        last = dt.datetime(utc.year, month, 31, 1, tzinfo=UTC)
        transitions.append(last - dt.timedelta(days=(last.weekday() + 1) % 7))
    offset = 2 if transitions[0] <= utc < transitions[1] else 1
    return utc.astimezone(dt.timezone(dt.timedelta(hours=offset)))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Missing or invalid weather reading")
    return value


def day_period(timestamp):
    hour = copenhagen_time(timestamp).hour
    if hour < 12:
        return "this morning"
    if hour < 17:
        return "this afternoon"
    if hour < 22:
        return "this evening"
    return "tonight"


def parse_forecast(data, fetched_at):
    current = data["current"]
    temperature = number(current["temperature_2m"])
    observed_at = number(current["time"])
    if not fetched_at - 5400 <= observed_at <= fetched_at + 900:
        raise ValueError("Weather observation is out of date")
    code = number(current["weather_code"])
    feels_like = number(current["apparent_temperature"])
    snow_now = code in SNOW_CODES or number(current["snowfall"]) >= SNOW_CM
    raining = code in RAIN_CODES or number(current["rain"]) + number(current["showers"]) >= RAIN_MM
    local = copenhagen_time(fetched_at)
    # Construct tomorrow's midnight in Copenhagen so DST days remain correct.
    next_date = local.date() + dt.timedelta(days=1)
    midnight_utc = dt.datetime.combine(next_date, dt.time(), tzinfo=UTC).timestamp()
    # Copenhagen's DST changes at 01:00 UTC, after both local and UTC midnight.
    midnight = midnight_utc - copenhagen_time(midnight_utc).utcoffset().total_seconds()
    hourly = data["hourly"]
    times = hourly["time"]
    if not times or any(len(hourly[field]) != len(times) for field in HOURLY_FIELDS):
        raise ValueError("Incomplete daily forecast")
    rows = {}
    for i, raw_time in enumerate(times):
        timestamp = number(raw_time)
        if timestamp in rows:
            raise ValueError("Duplicate forecast hour")
        # Ignore yesterday and tomorrow except midnight's preceding-hour totals.
        if fetched_at <= timestamp <= midnight:
            row = {field: number(hourly[field][i]) for field in HOURLY_FIELDS}
            if any(row[field] < 0 for field in ("rain", "showers", "snowfall")) or not 0 <= row["precipitation_probability"] <= 100:
                raise ValueError("Invalid precipitation forecast")
            rows[timestamp] = row
    # Precipitation is a preceding-hour total: midnight includes 23:00-24:00.
    # Requiring every remaining hour avoids silently claiming an incomplete day is dry.
    next_hour = int(fetched_at // 3600 + 1) * 3600
    expected_hours = range(next_hour, int(midnight) + 1, 3600)
    if any(timestamp not in rows for timestamp in expected_hours):
        raise ValueError("Missing forecast hours before midnight")
    rain_at = fetched_at if raining else None
    snow_at = fetched_at if snow_now else None
    cold_at = fetched_at if feels_like < COAT_FEELS_LIKE else None
    min_feels_like = feels_like
    rain_amount_at = fetched_at if raining else None
    for timestamp in sorted(rows):
        row = rows[timestamp]
        # Weather codes and apparent temperatures are instantaneous; next day's
        # midnight values must not influence today's recommendation.
        instant_today = timestamp < midnight
        snow_code = row["weather_code"] in SNOW_CODES
        snow_amount = timestamp > fetched_at and row["snowfall"] >= SNOW_CM
        if snow_at is None and ((instant_today and snow_code) or snow_amount):
            snow_at = max(fetched_at, timestamp - 3600) if snow_amount else timestamp
        if instant_today:
            min_feels_like = min(min_feels_like, row["apparent_temperature"])
            if cold_at is None and row["apparent_temperature"] < COAT_FEELS_LIKE:
                cold_at = timestamp
        if timestamp > fetched_at:
            wet = row["rain"] + row["showers"] >= RAIN_MM
            likely_rain = row["precipitation_probability"] >= RAIN_PROBABILITY and not (snow_code or row["snowfall"] >= SNOW_CM)
            if wet or likely_rain:
                onset = max(fetched_at, timestamp - 3600)
                if rain_at is None:
                    rain_at = onset
                if wet and rain_amount_at is None:
                    rain_amount_at = onset
    if snow_now:
        condition = "Snow"
    elif raining:
        condition = "Rain"
    elif code in (95, 96, 97, 99):
        condition = "Thunderstorm"
    elif code in (45, 48):
        condition = "Fog"
    else:
        condition = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast"}.get(code, "Cloudy")
    if snow_at is not None:
        kind, summary, reason_at = "snow", "Snow " + day_period(snow_at), snow_at
        advice = "Put on a warm coat"
    elif cold_at is not None:
        kind, summary, reason_at = "cold", "Cold " + day_period(cold_at), cold_at
        advice = "Put on a warm coat"
    elif rain_at is not None:
        kind, reason_at = "rain", rain_at
        summary = ("Rain " if rain_amount_at == rain_at else "Rain risk ") + day_period(rain_at)
        advice = "Take an umbrella"
    else:
        kind, summary, reason_at = "none", "Dry for the rest of today", None
        advice = "Have a lovely day"
    return {
        "temperature": round(temperature, 1),
        "feels_like": round(feels_like, 1),
        "min_feels_like": round(min_feels_like, 1),
        "condition": condition,
        "summary": summary,
        "reason_at": reason_at,
        "snow_later": snow_at is not None and not snow_now,
        "rain_later": rain_at is not None and not raining,
        "forecast_until": midnight,
        "kind": kind,
        "advice": advice,
        "observed_at": observed_at,
        "fetched_at": fetched_at,
    }


def fetch_forecast():
    request = urllib.request.Request(FORECAST_URL, headers={"User-Agent": "Bit-Robot-Face/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class MorningWeather:
    def __init__(self, fetch=fetch_forecast, clock=time.time, mode=lambda: "normal"):
        self.fetch = fetch
        self.clock = clock
        self.mode = mode
        self.lock = threading.Lock()
        self.cached = None
        self.attempted_hour = None
        self.failed = False

    def refresh_if_due(self):
        timestamp = self.clock()
        local = copenhagen_time(timestamp)
        if not (8 <= local.hour < 11 or self.mode() == "halloween"):
            return
        hour_key = local.strftime("%Y-%m-%dT%H")
        with self.lock:
            if self.attempted_hour == hour_key:
                return
            # Claim before fetching: multiple callers cannot duplicate a request.
            self.attempted_hour = hour_key
        try:
            reading = parse_forecast(self.fetch(), timestamp)
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as err:
            with self.lock:
                self.failed = True
            print("[weather] Copenhagen forecast unavailable: %s" % err, flush=True)
            return
        with self.lock:
            self.cached = reading
            self.failed = False

    def state(self):
        timestamp = self.clock()
        local = copenhagen_time(timestamp)
        halloween = self.mode() == "halloween"
        enabled = 8 <= local.hour < 11 or halloween
        end = (local + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) if halloween else local.replace(hour=11, minute=0, second=0, microsecond=0)
        greeting_end = local.replace(hour=8, minute=0, second=0, microsecond=0)
        result = {"enabled": enabled, "location": "Copenhagen, Denmark",
                  "source": "Open-Meteo", "source_url": "https://open-meteo.com/",
                  "timezone": "Europe/Copenhagen", "window": [0, 24] if halloween else [8, 11],
                  "halloween": halloween,
                  "window_remaining": max(0, int(end.timestamp() - timestamp)) if enabled else 0,
                  "greeting": 6 <= local.hour < 8,
                  "greeting_remaining": max(0, int(greeting_end.timestamp() - timestamp)) if 6 <= local.hour < 8 else 0,
                  "status": "outside_window", "valid_for": 0}
        if not enabled:
            return result
        with self.lock:
            cached = dict(self.cached) if self.cached else None
            failed = self.failed
        if not cached or timestamp - cached["observed_at"] >= 5400:
            result["status"] = "unavailable" if failed or cached else "loading"
            return result
        result.update(cached)
        result["valid_for"] = min(result["window_remaining"], max(0, int(cached["observed_at"] + 5400 - timestamp)))
        result["status"] = "cached" if failed else "ok"
        return result

    def run(self):
        while True:
            self.refresh_if_due()
            time.sleep(10)
