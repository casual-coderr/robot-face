import datetime as dt
import functools
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import server
from weather import MorningWeather, copenhagen_time, parse_forecast


def stamp(text):
    return dt.datetime.fromisoformat(text).timestamp()


def forecast(now, code=0, snow_code=None):
    hour = int(now // 3600) * 3600
    times = [hour + i * 3600 for i in range(-12, 37)]
    return {
        "current": {"time": now, "temperature_2m": 8.2, "apparent_temperature": 5.8,
                    "weather_code": code, "rain": 0, "showers": 0, "snowfall": 0},
        "hourly": {"time": times,
                   "weather_code": [snow_code if t == hour + 3 * 3600 and snow_code else 0 for t in times],
                   "snowfall": [0] * len(times), "rain": [0] * len(times),
                   "showers": [0] * len(times), "precipitation_probability": [0] * len(times),
                   "apparent_temperature": [10] * len(times)},
    }


def change_hour(data, timestamp, **values):
    index = data["hourly"]["time"].index(timestamp)
    for key, value in values.items():
        data["hourly"][key][index] = value


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = stamp("2026-10-31T08:00:00+01:00")
        self.calls = []
        self.fail = False

        def fetch():
            self.calls.append(self.now)
            if self.fail:
                raise OSError("offline")
            return forecast(self.now, 61)
        self.weather = MorningWeather(fetch=fetch, clock=lambda: self.now)

    def test_only_one_attempt_per_morning_hour(self):
        for hour in range(24):
            for minute in (0, 15, 30, 59):
                self.now = stamp("2026-10-30T%02d:%02d:00+01:00" % (hour, minute))
                self.weather.refresh_if_due()
        self.assertEqual([copenhagen_time(t).hour for t in self.calls], [8, 9, 10])

    def test_start_mid_window_and_next_day(self):
        self.now += 37 * 60
        self.weather.refresh_if_due()
        self.weather.refresh_if_due()
        self.assertEqual(len(self.calls), 1)
        self.now += 86400
        self.weather.refresh_if_due()
        self.assertEqual(len(self.calls), 2)

    def test_failures_retry_next_hour_and_expire(self):
        self.weather.refresh_if_due()
        self.now += 3600
        self.fail = True
        self.weather.refresh_if_due()
        self.assertEqual(self.weather.state()["status"], "cached")
        self.assertEqual(self.weather.state()["valid_for"], 1800)
        self.weather.refresh_if_due()
        self.assertEqual(len(self.calls), 2)
        self.now += 1800
        self.assertEqual(self.weather.state()["status"], "unavailable")
        self.now += 1800
        self.fail = False
        self.weather.refresh_if_due()
        self.assertEqual(self.weather.state()["status"], "ok")

    def test_greeting_and_weather_boundaries(self):
        for time, greeting, enabled in [("05:59:59", False, False), ("06:00:00", True, False),
                                        ("07:59:59", True, False), ("08:00:00", False, True),
                                        ("10:59:59", False, True), ("11:00:00", False, False)]:
            self.now = stamp("2026-10-30T%s+01:00" % time)
            state = self.weather.state()
            self.assertEqual((state["greeting"], state["enabled"]), (greeting, enabled))
        self.assertEqual(self.calls, [])  # Reading state never calls the upstream API.

    def test_halloween_mode_weather_and_return_to_normal(self):
        self.weather.mode = lambda: "halloween"
        for hour in (11, 18, 21, 23):
            self.now = stamp("2026-10-31T%02d:30:00+01:00" % hour)
            self.weather.refresh_if_due()
            self.weather.refresh_if_due()
            state = self.weather.state()
            self.assertTrue(state["halloween"])
            self.assertTrue(state["enabled"])
            self.assertEqual(state["status"], "ok")
            self.assertEqual(state["window_remaining"], (23 - hour) * 3600 + 1800)
        self.assertEqual(len(self.calls), 4)
        self.now = stamp("2026-11-01T00:00:00+01:00")
        self.assertTrue(self.weather.state()["halloween"], "Selected mode survives midnight")
        self.weather.mode = lambda: "normal"
        state = self.weather.state()
        self.assertFalse(state["halloween"])
        self.assertFalse(state["enabled"])
        self.weather.refresh_if_due()
        self.assertEqual(len(self.calls), 4)
        self.now = stamp("2026-10-31T20:00:00+01:00")
        self.assertFalse(self.weather.state()["halloween"], "Date cannot enable Halloween")

    def test_mode_commands_save_selection_and_api_state(self):
        original_path, original_weather = server.MODE_PATH, server.weather
        with tempfile.TemporaryDirectory() as folder:
            server.MODE_PATH = os.path.join(folder, "face-mode.json")
            server.weather = self.weather
            self.weather.mode = server.face_mode
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(server.Handler, directory=server.ROOT))
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%s" % httpd.server_port
                self.assertEqual(server.face_mode(), "normal")
                for mode in ("halloween", "normal"):
                    with urllib.request.urlopen(base + "/api/command?name=" + mode) as response:
                        self.assertEqual(json.load(response), {"ok": True, "mode": mode})
                    with open(server.MODE_PATH, encoding="utf-8") as f:
                        self.assertEqual(json.load(f)["mode"], mode)
                    with urllib.request.urlopen(base + "/api/state") as response:
                        state = json.load(response)
                    self.assertEqual(state["mode"], mode)
                    self.assertEqual(state["weather"]["halloween"], mode == "halloween")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()
                server.MODE_PATH, server.weather = original_path, original_weather

    def test_copenhagen_dst_independent_of_host(self):
        cases = [("2026-03-29T00:59:59+00:00", 1, 1), ("2026-03-29T01:00:00+00:00", 3, 2),
                 ("2026-10-25T00:59:59+00:00", 2, 2), ("2026-10-25T01:00:00+00:00", 2, 1)]
        for text, hour, offset in cases:
            local = copenhagen_time(stamp(text))
            self.assertEqual(local.hour, hour)
            self.assertEqual(local.utcoffset().total_seconds(), offset * 3600)

    def test_snow_forecast_takes_coat_priority_over_rain(self):
        state = parse_forecast(forecast(self.now, 61, 85), self.now)
        self.assertEqual((state["kind"], state["condition"], state["snow_later"]), ("snow", "Rain", True))
        self.assertEqual(parse_forecast(forecast(self.now, 71), self.now)["condition"], "Snow")
        self.assertEqual(parse_forecast(forecast(self.now, 0), self.now)["kind"], "none")
        self.assertEqual(state["advice"], "Put on a warm coat")
        self.assertNotIn("umbrella", state["advice"])

    def test_two_afternoon_rain_hours_trigger_umbrella_in_dry_morning(self):
        data = forecast(self.now)
        for hours in (6, 7):
            change_hour(data, self.now + hours * 3600, rain=0.4)
        state = parse_forecast(data, self.now)
        self.assertEqual((state["kind"], state["condition"]), ("rain", "Clear"))
        self.assertEqual(state["summary"], "Rain this afternoon")
        self.assertEqual(state["advice"], "Take an umbrella")

    def test_snow_late_tonight_is_included_beyond_six_hours(self):
        data = forecast(self.now)
        change_hour(data, self.now + 15 * 3600, snowfall=0.2)
        state = parse_forecast(data, self.now)
        self.assertEqual(state["kind"], "snow")
        self.assertEqual(state["summary"], "Snow tonight")

    def test_rain_thresholds_avoid_trace_and_low_probability(self):
        for amount, probability, expected in [(0.1, 49, "none"), (0.2, 0, "rain"), (0, 50, "rain")]:
            data = forecast(self.now)
            change_hour(data, self.now + 6 * 3600, rain=amount, precipitation_probability=probability)
            state = parse_forecast(data, self.now)
            self.assertEqual(state["kind"], expected)
            if probability == 50:
                self.assertEqual(state["summary"], "Rain risk this afternoon")

    def test_snow_probability_is_not_treated_as_rain(self):
        data = forecast(self.now)
        change_hour(data, self.now + 6 * 3600, weather_code=73, precipitation_probability=90)
        state = parse_forecast(data, self.now)
        self.assertEqual(state["kind"], "snow")
        self.assertFalse(state["rain_later"])

    def test_cold_without_snow_gets_coat_and_beats_umbrella(self):
        data = forecast(self.now)
        change_hour(data, self.now + 6 * 3600, rain=0.3)
        change_hour(data, self.now + 11 * 3600, apparent_temperature=4.9)
        state = parse_forecast(data, self.now)
        self.assertEqual(state["kind"], "cold")
        self.assertEqual(state["summary"], "Cold this evening")
        self.assertEqual(state["min_feels_like"], 4.9)
        self.assertFalse(state["snow_later"])
        self.assertEqual(state["advice"], "Put on a warm coat")
        data["current"]["apparent_temperature"] = 5
        change_hour(data, self.now + 11 * 3600, apparent_temperature=5)
        self.assertEqual(parse_forecast(data, self.now)["kind"], "rain")

    def test_past_and_tomorrow_instant_weather_are_excluded(self):
        data = forecast(self.now)
        for hours in (-2, 16, 17):  # 06:00 today, 00:00 and 01:00 tomorrow.
            change_hour(data, self.now + hours * 3600, weather_code=73, apparent_temperature=-5)
        for hours in (-2, 17):
            change_hour(data, self.now + hours * 3600, snowfall=1, rain=2, precipitation_probability=100)
        self.assertEqual(parse_forecast(data, self.now)["kind"], "none")

    def test_last_hour_of_today_is_included(self):
        data = forecast(self.now)
        # Midnight's rain amount describes the preceding 23:00-24:00 hour.
        change_hour(data, self.now + 16 * 3600, rain=0.2)
        state = parse_forecast(data, self.now)
        self.assertEqual(state["summary"], "Rain tonight")
        self.assertEqual(state["forecast_until"], stamp("2026-11-01T00:00:00+01:00"))

    def test_entire_day_must_be_available_and_finite(self):
        for field, value in [("rain", None), ("apparent_temperature", float("nan")),
                             ("precipitation_probability", 101)]:
            data = forecast(self.now)
            change_hour(data, self.now + 15 * 3600, **{field: value})
            with self.assertRaises(ValueError):
                parse_forecast(data, self.now)
        data = forecast(self.now)
        index = data["hourly"]["time"].index(self.now + 15 * 3600)
        for values in data["hourly"].values():
            values.pop(index)
        with self.assertRaises(ValueError):
            parse_forecast(data, self.now)

    def test_daily_boundary_around_dst_uses_local_midnight(self):
        for today, tomorrow in [("2026-03-28T08:00:00+01:00", "2026-03-29T00:00:00+01:00"),
                                 ("2026-03-29T08:00:00+02:00", "2026-03-30T00:00:00+02:00"),
                                 ("2026-10-24T08:00:00+02:00", "2026-10-25T00:00:00+02:00"),
                                 ("2026-10-25T08:00:00+01:00", "2026-10-26T00:00:00+01:00")]:
            now = stamp(today)
            state = parse_forecast(forecast(now), now)
            self.assertEqual(state["forecast_until"], stamp(tomorrow))

    def test_rain_and_snow_amounts_without_weather_code(self):
        data = forecast(self.now)
        data["current"]["showers"] = 0.2
        self.assertEqual(parse_forecast(data, self.now)["kind"], "rain")
        data["current"]["snowfall"] = 0.1
        self.assertEqual(parse_forecast(data, self.now)["kind"], "snow")

    def test_reject_missing_invalid_and_outdated_data(self):
        for key, value in [("temperature_2m", None), ("temperature_2m", float("nan")),
                           ("weather_code", True), ("time", self.now - 7200)]:
            data = forecast(self.now)
            data["current"][key] = value
            with self.assertRaises(ValueError):
                parse_forecast(data, self.now)
        data = forecast(self.now)
        data["hourly"]["snowfall"] = []
        with self.assertRaises(ValueError):
            parse_forecast(data, self.now)

    def test_api_json_and_jsonp_use_cached_weather(self):
        self.weather.refresh_if_due()
        original = server.weather
        server.weather = self.weather
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(server.Handler, directory=server.ROOT))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%s" % httpd.server_port
            with urllib.request.urlopen(base + "/api/state") as response:
                state = json.load(response)
            self.assertEqual(state["weather"]["kind"], "rain")
            with urllib.request.urlopen(base + "/api/state?cb=onState") as response:
                body = response.read().decode()
            self.assertTrue(body.startswith("onState("))
            self.assertEqual(json.loads(body[8:-2])["weather"]["location"], "Copenhagen, Denmark")
            self.assertEqual(len(self.calls), 1)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
            server.weather = original


if __name__ == "__main__":
    unittest.main()
