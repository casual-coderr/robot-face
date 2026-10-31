Bit's Copenhagen morning
=======================

Choose **Halloween** under **Mode** on `/commands` for friendly red eyes, small
horns and a weather strip throughout the day. Taps smile or wink, silently.
Weather refreshes once per hour; weather props pause so the face stays visible.
Choose **Normal** to restore blue eyes and the usual 08:00–11:00 weather window.
Normal is the default. The selection is saved in `face-mode.json` and survives
server and panel restarts; it does not switch automatically on a date.
Explicit naps and reminders still take priority. The offline microSD version
defaults to normal, has no live weather, and accepts `#halloween` for a preview.

Run `python server.py` as usual. Restart an existing server after updating these
files. The connected panel receives the new behavior through `/api/state` (JSON
or the existing JSONP transport). No API key or new Python packages are needed.

* 06:00–08:00 Europe/Copenhagen: Good morning, with an eight-second wave each
  minute: a rounded pale-blue cartoon glove, blue cuff, and small motion marks.
  The happy eyes ease left to make room and gently bounce during the wave.
  Automatic greetings and weather animations are silent. The separate legacy
  08:00 "Good morning! Take vitamins" alert is disabled in both reminder lists.
* 08:00–11:00: weather strip with Celsius temperature, conditions, and clothing advice.
* The server makes one Open-Meteo request per hour at 08:00, 09:00, and 10:00,
  within ten seconds of the hour. Starting during that window fetches immediately.
  Failed requests wait until the next hour; there are no requests outside the window.
* Each request examines the remainder of the Copenhagen calendar day through
  midnight, rather than only current conditions or the next six hours. Past
  hours and tomorrow's conditions do not influence the recommendation.
* Rain now, or at least 0.2 mm of rain/showers in any remaining hour, suggests an
  umbrella. A precipitation probability of 50% or more also qualifies when that
  hour is not expected to be snowy. Trace rainfall alone does not qualify.
* Snow now or in any remaining hour suggests a warm coat. Snow is detected by its
  weather code or at least 0.1 cm of snowfall. A feels-like temperature below 5 C
  now or later today also suggests a coat, even without snow.
* Exactly one recommendation is shown: snow coat first, then cold coat, then
  umbrella. Rain plus snow shows only the coat. Cold plus rain also shows only
  the coat. The rain routine has falling rain; the snow coat has falling flakes;
  the cold-only coat has no flakes.
* The display explains timing, for example "Rain this afternoon", "Snow this
  evening", or "Cold tonight". The temperature is the current reading at the
  latest fetch; the message describes the day's forecast, so it may describe
  rain or snow even while the current conditions are clear.
* Prop routines run for twelve seconds each minute. The weather strip remains
  visible between routines. Reminders, commands, touches, and explicit naps take
  priority, then the morning display resumes.
* During a weather routine the eyes shrink and move closer together, leaving room
  for the umbrella's fabric ribs or the coat's fleece collar, shaped sleeves,
  mittens, pocket seams, and zipper teeth. Eye size and spacing ease back afterward.
* A failed request can reuse a recent observation labeled "Cached". Observations
  expire after 90 minutes; missing or expired readings show "Weather unavailable"
  and hide the weather props. Rain/snow are model estimates, not a local sensor.
* The morning schedule uses Copenhagen time, independent of the host timezone,
  with the current EU daylight-saving rules. The existing general clock/reminders
  retain their host-time behavior.
* Offline microSD/standalone mode keeps its existing clock, reminders, and pet
  behavior; it cannot fetch weather and does not show the server-driven greeting.

Provider: [Open-Meteo](https://open-meteo.com/),
[forecast API documentation](https://open-meteo.com/en/docs).
The free endpoint is for non-commercial use; weather data is CC BY 4.0.
The display and API identify Open-Meteo as the source.
Coordinates: 55.6761 N, 12.5683 E (Copenhagen, Denmark).
The request URL and variables are in `weather.py`.

Validation: `python -m unittest -v test_weather` exercises scheduling, DST,
forecast interpretation, cache expiry, and the server's JSON/JSONP integration
using simulated upstream responses, without contacting the weather service.
