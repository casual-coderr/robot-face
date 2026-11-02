# Bit: architecture and working agreement

Shared reference for everyone changing this project: the owner and the AI assistants
(currently Claude and one other AI). Read it before adding a feature. If a feature does
not fit what is written here, do not work around it: add an entry to the
**Proposals log** (section 11) and let the other side answer before building.

Written by Claude from a full read of `face.html`, `weather.js`, `weather.py`, `server.py`
and `make_standalone.py` on 2026-10-31. Nothing in the findings was run; they come
from reading. The other AI should correct or extend any line it disagrees with, in place,
with a dated note.

## 1. What this is

A desk-pet robot face ("Bit") that runs full screen in the Internet Explorer of an IEI
IOVU-430S panel PC (Windows CE 6.0, 480x272, resistive touch). A Python server feeds it
reminders, commands and weather; two web pages on the PC/phone control it.

```
 panel (CE IE)  --- script-tag polling every 3 s --->  server.py  <--- /commands, /reminders (any browser)
  face.html + weather.js                                  |  ^
  draws everything with divs                              |  +-- reminders.json, face-mode.json
                                                          +-- weather.py -> Open-Meteo (hourly, 08-11 Copenhagen)
 standalone/ (microSD, no PC): same page, no server, own clock, reminders.js, no commands/weather
```

## 2. Platform contract (hard rules, learned on the real panel)

The panel's browser is the most limiting thing in the project. Everything that runs on it
must follow these. Desktop-only code (`commands.html`, `reminders.html`, Python) is free
of them.

| Rule | Why |
|---|---|
| ES3 only: no `JSON.parse`, `Array.indexOf`, `forEach`, `let/const`, arrow functions, trailing commas | CE JScript |
| No canvas, no CSS3 (transforms, radius, opacity animation). Draw with absolutely positioned divs | not supported |
| No XHR/fetch/`Image()` beacons. Talk to the server with injected `<script src=...&cb=fn>` (JSONP) | XHR unreliable, image beacons never arrived |
| Never pass NaN, Infinity or negative sizes to a style. Keep `Math.sin/cos` arguments small (`t % period`) | CE's math returns NaN for huge arguments (clock reads 2008, about 1.2e12 ms) and `style.x = 'NaNpx'` throws "Invalid argument", which froze the whole face once |
| Do not trust the panel's clock for dates. Relative timing (`now()` differences) is fine | clock is wrong |
| Every DOM write is expensive: write only when the value changed (key/cache pattern) | slow CPU |
| Sound = hidden `<embed>` only, and it launches the media player (Windows flag). Panel sounds only for reminders/notices (`SOUND_MODE='alerts'`) | breaks immersion otherwise |
| Text must stay upright: flip/upside-down is OFF | the panel font shows boxes for flipped glyphs |
| `window.name` survives a reload; use it to carry small state across the timed reload | the page reloads every 10 min |
| Report errors with `logToServer(msg)`; the panel has no console | debugging |

## 3. File map

| File | Role | Runs on |
|---|---|---|
| `face.html` | the face: eyes, behaviour, input, polling, commands, routines | panel + desktop |
| `weather.js` | weather strip, umbrella/coat props, morning glove wave | panel + desktop |
| `index.html` | **copy of face.html** served at `/` (kept in sync by hand) | panel |
| `server.py` | HTTP server, notices, reminders, commands, face mode, state JSON | PC/Linux |
| `weather.py` | fetch + interpret Open-Meteo, hourly schedule, cache. Pure functions + injectable clock/fetch | PC/Linux |
| `commands.html`, `reminders.html` | control pages | any browser |
| `reminders.json`, `face-mode.json` | persisted data (do not overwrite on deploy) | PC/Linux |
| `make_standalone.py` | builds `standalone/` for the microSD | PC |
| `make_sounds.py` | generates `sounds/*.wav` | PC |
| `test_weather.py`, `test_weather_browser.cjs` | weather tests (Python unit tests; optional Playwright run) | PC |
| `WEATHER.md` | behaviour spec for weather/morning | doc |
| `archive/` | retired files (preview images, old logs, `sound-test.html`, an old `standalone/` build). Not used by anything; see `archive/README.md` | none |

## 4. Protocol (panel <-> server)

`GET /api/state?cb=onState` returns `onState({...});` every 3 s. Fields:

| Field | Meaning |
|---|---|
| `ts` | server **local** wall time as epoch seconds (read with `getUTC*`). Panel keeps its own offset |
| `night` | `[22.5, 7]`, sleep hours; fractions allowed (22.5 = 22:30) |
| `pace` | `calm` / `normal` / `lively`: how often Bit does small things on its own (persisted in `face-mode.json`) |
| `notice` | the one notice to show: `{id,text,mood,sound,sticky}` or null. Panel dismiss -> `GET /api/ack?id=&cb=onAck` |
| `cmd` | newest command `{id,name,text,mood}`, present for 8 s only (see D5) |
| `mode` | `normal` or `halloween` (persisted in `face-mode.json`) |
| `weather` | object from `weather.py` `state()` (status, kind, advice, `*_remaining` seconds, ...) |
| `sound` | `all` / `alerts` / `off` |
| `build`, `flip` | legacy, unused by the page (see D10) |

**Good pattern, keep it:** send *remaining seconds* (`window_remaining`,
`greeting_remaining`, `valid_for`) and let the panel count down from the moment it received
them. This makes the panel's wrong clock irrelevant. New server-driven displays must do
the same, never send absolute timestamps for the panel to compare with its own `now()`.

Server-to-page controls (`/api/command`, `/api/notify`) are GET so any tool can call them.
The panel only needs `state`, `ack` and `log`.

## 5. Time model

Three different time bases exist today. Say which one a feature uses.

| Base | Used by |
|---|---|
| Server host local time | `/api/state.ts`, clock on screen, night hours, reminders |
| Europe/Copenhagen (fixed, own DST rules) | weather and the morning greeting only |
| Panel `now()` | relative animation timing, idle timers, countdowns of `*_remaining` |

## 6. Face runtime (what happens each frame)

`frame()` -> `frameWork()` every ~50 ms. Each step is wrapped in `safe(name, fn)` so one
failure is logged and the rest keep drawing.

Order in `frameWork()`: blink -> mode -> colour -> stage -> (standalone tick) -> weather prep
-> **either** the running routine (`act`) **or** `wanted()` mood -> gaze overrides
(morning/weather) -> ease eye parameters -> draw eyes -> draw overlays (hearts, paper,
clock, z's, horns, tear, weather).

**Priority, as implemented (the single list; update it when it changes):**
1. notice (reminder/notify), with a 700 ms startle first
2. connection lost ("PC offline")
3. toast (short reaction: poke, command, "good morning")
4. morning greeting, then weather routine
5. Halloween devil face
6. idle face: asleep at night or while dozing, sleepy when drowsy, wistful after a long time alone, otherwise normal, with the idle director's small actions (`beat`) steering gaze and eye shape on top

`act` (routine: song, giggle, love, heart, lookaround, read) is checked before all of this
and owns the eyes while it runs.

State owners (who may write what), as they stand:

| State | Written by |
|---|---|
| `notice`, `shownId`, `connLost`, `serverTs` | `onState`, `localTick` (standalone) |
| `toast` | `toastNow`, `wanted` (chains `next`), `setFaceMode` |
| `act` | `startAct`, `frameWork` (ends it), `setFaceMode` |
| `stage` (`ST_AWAKE/DROWSY/NAP/LONELY`), `napPhase*` | `updateStage` only |
| `lastTouch`, `lastRest`, `drowsyGap`, `lonelyGap` | `touchStart`, `applyColor`, `updateStage`, `runCommand`; always through `resetIdle()` (D6 fixed) |
| `beat`, `beatNext`, `beatPlan`, `poseScale/Gap`, `lookK`, `squash` | the director (`beat*` functions) and `runCommand('behave')`; `drawEye` reads them |
| `napUntil` | `runCommand`, `updateStage`, `reloadNow` (persisted via `window.name`) |
| `weather*`, `morning*` | `weather.js` only, read by `face.html` (two-way coupling, D3) |

## 7. Working rules for any change

1. **Single source of truth.** A list of names (commands, moods, sounds) lives in one place
   and the others derive from it. Today they do not (D2), so until the manifest exists, add
   to *all* places in the checklist in section 8 and tick them in your change note.
2. **One owner per piece of state.** Do not add a new writer for `stage`, `toast`, `act`.
   Call the function that owns it.
3. **Every new draw step goes through `safe()`** and uses the write-on-change key pattern.
4. **No new global without a prefix** for the feature (`weather*`, `paper*`). Prefer a
   function-scoped closure. New features that need many globals are a signal to propose the
   module structure in section 10 first.
5. **Create DOM lazily** and keep the budget: the face currently creates about 90 nodes at
   boot plus a weather pool that grows with the most complex prop. Target at most 400 live
   nodes. Hide, do not remove, and reuse pooled divs.
6. **Test on the panel path.** Desktop success does not prove the panel works. After a
   change, load the page on the panel and read the server log: expect `boot`, `init done`,
   `first frame ok` and no `failed`.
7. **Do not break standalone.** Anything server-driven must degrade to nothing when
   `STANDALONE` is true.
8. **Keep timing constants named and in one block** (`T_BORED`, `RELOAD_MS`, ...), commented
   with the unit.
9. **Server logic must be testable:** inject the clock and any network fetch (as
   `MorningWeather` does) and add tests next to it.
10. **Say what you did not verify** in the change note.

## 8. Recipes (current process)

**Add a command (a button on /commands that makes Bit do something):**
1. `server.py` `COMMAND_NAMES` (add the name)
2. `face.html` `runCommand` (or `CMDS` table for a plain toast)
3. `commands.html` button list
4. if it needs a sound: `make_sounds.py`, regenerate `sounds/`
5. test: send it with `GET /api/command?name=..`, watch the panel path (rule 6)

**Add a routine with a drawing (like read/love/heart):**
1. create its divs once, hidden, near the other props; use `className` classes, not inline
2. add its duration to `startAct`'s table
3. add its gaze/eye behaviour in the `act` branch of `frameWork`
4. add `drawX(t)` and register it in the `safe(...)` list
5. keep position/size writes behind a key comparison
6. confirm it ends cleanly (hidden, eyes restored) when interrupted by a notice, a touch,
   a mode change or the timed reload

**Add a server-driven display (like weather):** compute and validate on the server, send
*remaining seconds*, return a status (`ok`/`cached`/`unavailable`/`loading`) and expiry,
show source attribution if the data licence requires it, add tests with a fake clock and
fake fetch.

**Add a reminder field:** `clean_reminder` (validate), `reminders.html` (form + list),
`localTick` for standalone, `make_standalone.py` already copies the json.

## 9. Review findings (2026-10-31, Claude)

Ranked. IDs are stable; mark each as `open`, `confirmed`, `fixed (date)` or `rejected (why)`.

| ID | Sev | Finding | Status |
|---|---|---|---|
| D1 | high | **Stage meaning drifted.** `stage` is now an idle-mood cycle (1 thinking, 2 happy, 3 reading, 4 wink, 5 sleepy, 6 asleep) but `updateTear` still shows a tear for `stage 2/3` (the old lonely/sulking stages) and `touchStart` sets `welcomeBack = (stage >= 2)`. Reading the code, a tear falls while Bit is happy or "reading", and a touch during stages 2 to 6 (anything after the first idle mood) plays the "you're back!" song instead of the poke reaction, which can interrupt the tap-to-angry ladder. Unclear whether the loneliness behaviour was removed on purpose | fixed 2026-11-01 (P3): stages redefined, tear and welcome-back only apply to the wistful state |
| D2 | high | Names duplicated: commands in 3 places (server list, `runCommand`/`CMDS`, `commands.html`); moods in 4 (server `MOODS`, face `MOODS`, `MOOD_COLORS`, `reminders.html` select) plus `WEATHER_MOODS` | open |
| D3 | high | `weather.js` and `face.html` read and write each other's globals (`notice`, `act`, `toast`, `napUntil`, `connLost`, `dragging`, `HALLOWEEN`, `FLIP`, `screenEl`, `ease`, `esc`, `flipText` one way; `weatherShowing`, `morningShowing`, `weatherRoutine`, `weatherEyeInset`, `morningEyeShift`, `WEATHER_MOODS` the other). It works only because of load order and shared names | open |
| D4 | high | "Who wins" is decided in several places: `wanted()`, `prepareWeather` (`busy`), overrides after `wanted()` in `frameWork`, the `applyColor` colour rule, and `eyesHidden` set from `drawHearts`. A new feature must edit all of them | open |
| D5 | med | Commands use a single slot visible for 8 s: two commands inside one 3 s poll lose the first, and a reload inside 8 s can replay one | open |
| D6 | med | The "re-roll idle timers" block (`lastTouch`, `sleepAfter`, `idleMood`, `nextIdleChange`) is copy-pasted in 4 places | fixed 2026-11-01 (`resetIdle()`) |
| D7 | med | Theme is a global boolean: `HALLOWEEN` appears in 10 places in `face.html` and 5 in `weather.js`, with special cases in `wanted`, `updateStage`, `applyColor`, `poke`, `prepareWeather`, `drawHorns`, `drawWeather` | open |
| D8 | med | Flip support spreads through 19 spots in `face.html` and 9 in `weather.js`, is off, and cannot work on the panel font. Hearts and the newspaper already ignore it, so it is inconsistent anyway | open: remove, or centralise |
| D9 | med | DOM is created eagerly (13 creation sites, about 90 nodes at boot, weather pool unbounded) and no node budget exists | open |
| D10 | med | `index.html` is a hand-copied duplicate of `face.html`. Dead code: `__BUILD__` replace and `build` in state; header comment says 2 s polling (it is 3 s); `server.py` docstring misses `/api/command` and `/commands` | open |
| D11 | med | `server.py`: one long `do_GET` if-chain; JSONP reply code repeated 3 times; mutating endpoints are GET; `float(q["seconds"])` in `/api/notify` is not validated (bad input raises); `face-mode.json` is re-read on every poll; `fired` grows forever | open |
| D12 | low | `make_standalone.py` hardcodes the file list, so a new `.js` file works on the server and silently breaks the microSD build | open |
| D13 | low | No tests for face logic. Weather has 20 Python tests plus an optional Playwright script. Neither was run for this review | open |
| D14 | low | Anyone on the LAN can notify or command the panel (no auth, listens on all interfaces); acceptable at home, but do not expose the port | note |

**What the other AI did that Claude had not, and should be kept:**
- remaining-seconds protocol (clock independent), see section 4
- pure parsing function plus injected clock/fetch, with real unit tests
- fail closed: validate upstream data, label stale data "Cached", expire it
- DST rules without tzdata, attribution and licence note, `WEATHER.md` behaviour spec
- pooled rectangles with change keys and run-merging of scanlines (`weatherShape`)
- persisted `faceMode` that survives restarts (Claude's nap only survives a reload)
- applied the NaN lesson (`weatherPhase` is a small modulo)

**What Claude did that added to the debt (own it):** the `startAct` duration table and the
`runCommand` if-chain, the per-prop `eyesHidden` toggle, the three copies of the idle
reset, and a second hand-copied page. The recipes in section 8 are a symptom of that.

## 10. Target structure (proposal P1, for the other AI to accept, amend or reject)

Keep the single-page, ES3, no-framework constraint. Change how it is organised, in steps
that each ship and can be checked on the panel:

1. **Fix D1** and extract `resetIdle()` (D6). Remove dead `build` code and stale comments (D10).
2. **Command registry.** One manifest (`commands.json`: name, label, icon, group, params).
   The server validates against it and serves it at `/api/commands`; `commands.html`
   builds its buttons from it; the face has `Bit.commands[name] = function (c) {...}`; a
   contract test fails if a manifest name has no handler.
3. **One scene resolver.** Each frame build a `scene = {mood, text, gaze, eye:{dx,scale,hidden}, color}`
   from layers with numeric priority (notice 100, offline 90, act 80, toast 70, server
   display 40, theme/idle 10). Routines change the scene; only the core draws eyes. This
   replaces D4 and the `eyesHidden`/`weatherEyeInset` globals.
4. **Routine contract + namespace.** `Bit.routine({id, priority, dur, start, update, draw, stop})`
   with lazy DOM creation and a guaranteed `stop()` on interruption. Move hearts, newspaper,
   horns, z's, tear and weather into it, one file each. Replaces D3 and D9.
5. **Theme object** (`normal`, `halloween`: eye colour per mood, horns, idle behaviour,
   weather window) instead of the `HALLOWEEN` boolean (D7).
6. **Command queue.** The panel sends `since=<last id>`, the server returns every newer
   command (kept about 60 s). Fixes D5 and removes the 8 s replay window.
7. **Build step.** Sources in `src/`, `build.py` concatenates them into `index.html` and
   `standalone/` from one file list. Removes the duplicate copy and D12.
8. **Flip:** delete it, or implement it once as coordinate helpers (`X(x,w)`, `Y(y,h)`)
   used by every draw (D8). Needs the owner's decision about mounting the panel upside down.

Cost to weigh on CE: more function calls per frame; measure `frameCost` before and after
each step (it is smoothed ms per frame, target under 25 ms, budget 50 ms).

## 11. Proposals log

Add one entry per change that touches structure. Append, do not rewrite others' entries.

```
### P<n> <title>   (author, date)   status: proposed | accepted | amended | rejected | done
Problem:    what is hard or fragile today
Proposal:   what to change
Panel cost: DOM nodes, per-frame work, protocol size
Migration:  steps, and how old and new run side by side
Risks:      what could break, how it is checked
Reply:      (the other side, dated)
```

### P1 Target structure (Claude, 2026-10-31)   status: proposed
See section 10. Waiting for the other AI's reply and the owner's decision on D1 and D8.

### P3 Idle director and pose layer (Claude, 2026-11-01)   status: done, awaiting the other AI's review
Problem:    untouched, Bit slept for most of the day (no self-wake after 30-90 min, plus night 21:00-07:00) and the
            idle faces were near-static; stage numbers had drifted from their meaning (D1); eye size/spacing was a
            weather-only global.
Proposal:   (1) `stage` is now four named states and a self-waking doze (drowsy 20-40 min after the last touch, doze
            2-6 min, then a stretch); explicit naps and night sleep unchanged; Halloween has no naps. (2) An idle
            "director": every 8-20 s (x pace) one small action from `BEATS` (18 of them: look left/right/up, glance at
            the door or clock, scan, curious, double blink, squint, sigh, stretch, wiggle, bounce, sway, peek at you,
            follow a fly, yawn, shy, nod), weighted by time of day, drowsy and wistful states, never repeating.
            (3) Pose layer: `poseScale`, `poseGap`, `lookK`, `squash` plus automatic perspective (the far eye narrows
            when looking sideways); the weather inset stays as is. (4) Night starts 22:30 (fractional hours).
            (5) `pace` setting and a `behave` command (/commands) to try any action.
Panel cost: no new DOM nodes; two small objects allocated per frame while an action shapes the eyes; one extra
            `safe()` step. Persisted across the 10-minute reload through `window.name`.
Migration:  replaced the five-faces rotation in `updateStage`/`wanted`; the weather and morning code is untouched and
            keeps priority (the director stands down for notices, toasts, routines, touch, `morningRoutine`,
            `weatherRoutine`, sleep).
Risks:      not run on the real panel yet; the optional Playwright script (`test_weather_browser.cjs`) was not run, it
            sets `napUntil` and `lastTouch`, which still exist. Pace values are guesses, tune on the wall.
Reply:      (other AI, dated)

### P2 (reserved for the other AI's counter-review)

## 12. Before you say it is done

- [ ] Desktop: open `index.html` and `?fast`; trigger every command; no console errors
- [ ] Server log from the panel: `boot`, `init done`, `first frame ok`; no `failed`, no `error`
- [ ] Reload path: change survives the 10-minute reload (state via `window.name`)
- [ ] Interrupt path: new routine ends cleanly when a notice, touch, mode change or nap arrives
- [ ] Standalone still opens from `file://` (`python make_standalone.py`)
- [ ] `python -m unittest -v test_weather` passes (and any tests you added)
- [ ] `face.html` and `index.html` are identical (until step 7 removes the copy)
- [ ] Deploy note: files to copy, do not overwrite `reminders.json` or `face-mode.json`
- [ ] Change note says what was NOT verified
