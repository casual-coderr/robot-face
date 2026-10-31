"""Robot face server: serves the page and tells the face what to react to.

  GET  /reminders                   page to add, switch off and delete reminders
  GET  /api/state                   what the face polls every 3 s
  GET  /api/notify?text=..&mood=..  make the face react (sound=, sticky=1, seconds=)
  GET  /api/ack?id=..               dismiss a notice (the face calls this when tapped)
  GET  /api/reminders               list reminders
  POST /api/reminders               add one (JSON body)
  POST /api/reminders/toggle?id=..  switch one on or off
  POST /api/reminders/delete?id=..  delete one
  POST /api/quick                   one-off reminder: {"text":..,"mode":"now"|"in"|"at","minutes":..,"time":"HH:MM"}

Reminders live in reminders.json and fire at their time (every day, chosen days, or once on a date).
Run:  python server.py        (listens on all interfaces, port 8765)
"""
import datetime
import functools
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from weather import MorningWeather

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
NIGHT = [21, 7]            # face sleeps (quiet, dim) from 21:00 to 07:00
MOODS = ["normal", "happy", "wink", "angry", "sad", "surprised", "thinking", "sleepy", "pumpkin", "devil"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SOUND_MODE = "alerts"      # panel sounds: "all" = every reaction, "alerts" = reminders and notices only, "off"
FLIP_CLIENTS = set()   # flip is off: the panel has no upside-down letters (page ignores this for now)
COMMAND_NAMES = ["happy", "wink", "angry", "furious", "sad", "lonely", "surprised", "thinking", "yawn", "sleep",
                 "hello", "giggle", "song", "love", "heart", "lookaround", "read", "nap", "wake", "say", "normal", "halloween"]
COMMANDS_PAGE_PATHS = ("/commands", "/command")
REMINDERS_PAGE_PATHS = ("/reminders", "/reminder", "/remidners")   # the last one is a typo that is easy to make

REM_PATH = os.path.join(ROOT, "reminders.json")
MODE_PATH = os.path.join(ROOT, "face-mode.json")

lock = threading.Lock()
rem_lock = threading.Lock()
mode_lock = threading.Lock()
notices = []               # oldest first; the face shows notices[0]
counter = 0
last_cmd = None             # the newest command from /commands; the face runs each one once
fired = set()              # (date, reminder id) already shown

def face_mode():
    """Read the saved mode so the choice survives server and panel restarts."""
    try:
        with open(MODE_PATH, encoding="utf-8") as f:
            return "halloween" if json.load(f).get("mode") == "halloween" else "normal"
    except (OSError, ValueError, AttributeError):
        return "normal"


def set_face_mode(mode):
    with mode_lock:
        with open(MODE_PATH + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f)
        os.replace(MODE_PATH + ".tmp", MODE_PATH)


weather = MorningWeather(mode=face_mode)


def build_id():
    """Changes whenever index.html changes; the page compares it with the one it was served with."""
    st = os.stat(os.path.join(ROOT, "index.html"))
    return "%x%x" % (int(st.st_mtime), st.st_size)


def sound_names():
    d = os.path.join(ROOT, "sounds")
    return [f[:-4] for f in os.listdir(d) if f.endswith(".wav")] if os.path.isdir(d) else []


def add_notice(text, mood="surprised", sound=None, sticky=False, seconds=30):
    global counter
    if mood not in MOODS:
        mood = "surprised"
    names = sound_names()
    if sound not in names:
        sound = mood if mood in names else "boop"
    with lock:
        counter += 1
        notices.append({
            "id": counter,
            "text": text[:80],
            "mood": mood,
            "sound": sound,
            "sticky": bool(sticky),
            "until": None if sticky else time.time() + seconds,
        })
        return counter


def current_notice():
    with lock:
        now = time.time()
        notices[:] = [n for n in notices if n["until"] is None or n["until"] > now]
        if not notices:
            return None
        n = notices[0]
        return {k: n[k] for k in ("id", "text", "mood", "sound", "sticky")}


def add_command(name, text="", mood=""):
    global counter, last_cmd
    if mood not in MOODS:
        mood = "happy"
    with lock:
        counter += 1
        last_cmd = {"id": counter, "name": name, "text": text[:40], "mood": mood, "at": time.time()}
        return counter


def current_cmd():
    """The newest command, for 8 s only: long enough for the next poll, too short to replay after a reload."""
    with lock:
        if last_cmd and time.time() - last_cmd["at"] < 8:
            return {k: last_cmd[k] for k in ("id", "name", "text", "mood")}
        return None


def ack(nid):
    with lock:
        notices[:] = [n for n in notices if nid is not None and n["id"] != nid]


# ---------------------------------------------------------------- reminders
def save_reminders(items):
    tmp = REM_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, REM_PATH)             # never leave a half-written file behind


def load_reminders():
    """Read reminders.json (caller holds rem_lock). Entries without an id get one and are saved."""
    if not os.path.exists(REM_PATH):
        return []
    with open(REM_PATH, encoding="utf-8") as f:
        items = json.load(f)
    changed = False
    for r in items:
        if "id" not in r:
            r["id"] = uuid.uuid4().hex[:8]
            changed = True
    if changed:
        save_reminders(items)
    return items


def clean_reminder(d):
    """Validate a reminder from the web page; raises ValueError with a message the page can show."""
    t = str(d.get("time", ""))
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
        raise ValueError("Time must look like 08:30")
    text = str(d.get("text", "")).strip()
    if not text:
        raise ValueError("Write what the reminder should say")
    r = {"id": uuid.uuid4().hex[:8], "time": t, "text": text[:80]}
    days = d.get("days", "daily")
    if days == "daily" or not days:
        r["days"] = "daily"
    else:
        picked = [x for x in DAYS if x in days]
        r["days"] = picked if picked else "daily"
    date = d.get("date")
    if date:
        try:
            time.strptime(str(date), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must look like 2026-11-05")
        r["date"] = str(date)
    mood = d.get("mood", "surprised")
    r["mood"] = mood if mood in MOODS else "surprised"
    sound = d.get("sound", "alert")
    r["sound"] = sound if sound in sound_names() else "alert"
    r["sticky"] = bool(d.get("sticky", True))
    try:
        r["seconds"] = max(5, min(3600, int(d.get("seconds", 60))))
    except (TypeError, ValueError):
        r["seconds"] = 60
    r["enabled"] = True
    return r


def fire(r):
    add_notice(r.get("text", "Reminder"), r.get("mood", "surprised"),
               r.get("sound", "alert"), r.get("sticky", True), r.get("seconds", 60))


def reminder_loop():
    while True:
        try:
            with rem_lock:
                items = load_reminders()
            now = time.time()
            lt = time.localtime(now)
            hhmm = "%02d:%02d" % (lt.tm_hour, lt.tm_min)
            today = time.strftime("%Y-%m-%d", lt)
            dow = DAYS[lt.tm_wday]
            done = []                                           # one-offs that fired: removed afterwards
            for r in items:
                if not r.get("enabled", True):
                    continue
                if "at" in r:                                   # quick one-off: fires once its moment has passed
                    if now >= r["at"] and ("once", r["id"]) not in fired:
                        fired.add(("once", r["id"]))
                        fire(r)
                        done.append(r["id"])
                    continue
                if r.get("time") != hhmm:
                    continue
                if r.get("date") and r["date"] != today:       # one-off reminder for another day
                    continue
                days = r.get("days", "daily")
                if days != "daily" and dow not in days:
                    continue
                key = (today, r["id"])
                if key in fired:
                    continue
                fired.add(key)
                fire(r)
                if r.get("date"):
                    done.append(r["id"])
            if done:
                with rem_lock:
                    save_reminders([x for x in load_reminders() if x["id"] not in done])
        except (OSError, ValueError):
            pass
        time.sleep(5)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # the panel's old IE caches aggressively; never let it reuse a stale copy
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_index(self):
        """Serve index.html with its build id filled in, so the page knows which build it is."""
        with open(os.path.join(ROOT, "index.html"), "rb") as f:
            body = f.read().replace(b"__BUILD__", build_id().encode("ascii"), 1)   # only the one placeholder
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.send_index()
        if u.path.rstrip("/") in COMMANDS_PAGE_PATHS:
            self.path = "/commands.html"
            return super().do_GET()
        if u.path.rstrip("/") in REMINDERS_PAGE_PATHS:
            self.path = "/reminders.html"
            return super().do_GET()
        if not u.path.startswith("/api/"):
            return super().do_GET()
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/api/state":
            # ts = local wall-clock time as epoch seconds, so the face can read it with getUTC*()
            off = -(time.altzone if time.localtime().tm_isdst > 0 else time.timezone)
            ts = int(time.time() + off)
            state = {"ts": ts, "night": NIGHT, "notice": current_notice(),
                     "flip": self.client_address[0] in FLIP_CLIENTS, "sound": SOUND_MODE,
                     "build": build_id(), "cmd": current_cmd(), "mode": face_mode(), "weather": weather.state()}
            cb = q.get("cb", "")
            if cb:
                # script-tag reply for the panel's old browser: onState({...});
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cb):
                    return self.send_error(400)
                body = ("%s(%s);" % (cb, json.dumps(state))).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self.send_json(state)
        if u.path == "/api/log":                                # the panel reports errors/progress here
            print("[panel %s] %s" % (self.client_address[0], q.get("m", "")), flush=True)
            body = b";"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/command":                            # make Bit do something, then go back to normal
            name = q.get("name", "")
            if name not in COMMAND_NAMES:
                return self.send_json({"ok": False, "error": "unknown command"}, 400)
            if name in ("normal", "halloween"):
                try:
                    set_face_mode(name)
                except OSError:
                    return self.send_json({"ok": False, "error": "Mode could not be saved"}, 500)
                return self.send_json({"ok": True, "mode": name})
            cid = add_command(name, q.get("text", ""), q.get("mood", ""))
            return self.send_json({"ok": True, "id": cid})
        if u.path == "/api/notify":
            nid = add_notice(q.get("text", ""), q.get("mood", "surprised"), q.get("sound"),
                             q.get("sticky") == "1", float(q.get("seconds", 30)))
            return self.send_json({"ok": True, "id": nid})
        if u.path == "/api/ack":
            try:
                nid = int(q.get("id", ""))
            except ValueError:
                nid = None
            ack(nid)
            cb = q.get("cb", "")
            if cb:                                              # script-tag reply for the panel's old browser
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cb):
                    return self.send_error(400)
                body = ("%s();" % cb).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self.send_json({"ok": True})
        if u.path == "/api/reminders":
            try:
                with rem_lock:
                    items = load_reminders()
            except (OSError, ValueError):
                return self.send_json({"ok": False, "error": "reminders.json could not be read"}, 500)
            return self.send_json({"ok": True, "reminders": items, "sounds": sorted(sound_names()), "now": time.time()})
        self.send_error(404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, 8192)) if length else b""
        try:
            with rem_lock:
                if u.path == "/api/reminders":
                    try:
                        data = json.loads(raw.decode("utf-8"))
                        r = clean_reminder(data)
                    except (ValueError, AttributeError) as err:
                        return self.send_json({"ok": False, "error": str(err) or "Bad request"}, 400)
                    items = load_reminders()
                    items.append(r)
                    save_reminders(items)
                    return self.send_json({"ok": True, "reminder": r})
                if u.path == "/api/quick":
                    try:
                        data = json.loads(raw.decode("utf-8"))
                        text = str(data.get("text", "")).strip()[:80]
                        if not text:
                            raise ValueError("Write what the reminder should say")
                        mode = data.get("mode")
                        if mode == "now":                       # straight onto the panel, nothing stored
                            add_notice(text, "thinking", "alert", True, 60)
                            return self.send_json({"ok": True, "now": True})
                        now_dt = datetime.datetime.now()
                        if mode == "in":
                            minutes = int(data.get("minutes"))
                            if not 1 <= minutes <= 1440:
                                raise ValueError("Pick between 1 minute and 24 hours")
                            due = now_dt + datetime.timedelta(minutes=minutes)
                        elif mode == "at":
                            t = str(data.get("time", ""))
                            if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
                                raise ValueError("Time must look like 18:30")
                            due = now_dt.replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)
                            if due <= now_dt:                    # that time already passed today: tomorrow
                                due += datetime.timedelta(days=1)
                        else:
                            raise ValueError("Pick when to remind you")
                    except (ValueError, TypeError, AttributeError) as err:
                        return self.send_json({"ok": False, "error": str(err) or "Bad request"}, 400)
                    r = {"id": uuid.uuid4().hex[:8], "text": text, "at": due.timestamp(),
                         "time": due.strftime("%H:%M"), "date": due.strftime("%Y-%m-%d"),
                         "mood": "thinking", "sound": "alert", "sticky": True, "seconds": 60, "enabled": True}
                    items = load_reminders()
                    items.append(r)
                    save_reminders(items)
                    return self.send_json({"ok": True, "now": False, "time": r["time"], "date": r["date"]})
                if u.path in ("/api/reminders/toggle", "/api/reminders/delete"):
                    items = load_reminders()
                    rid = q.get("id", "")
                    hit = [r for r in items if r["id"] == rid]
                    if not hit:
                        return self.send_json({"ok": False, "error": "No such reminder"}, 404)
                    if u.path.endswith("toggle"):
                        hit[0]["enabled"] = not hit[0].get("enabled", True)
                    else:
                        items = [r for r in items if r["id"] != rid]
                    save_reminders(items)
                    return self.send_json({"ok": True})
        except (OSError, ValueError):
            return self.send_json({"ok": False, "error": "reminders.json could not be read or written"}, 500)
        self.send_error(404)


if __name__ == "__main__":
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=weather.run, daemon=True).start()
    handler = functools.partial(Handler, directory=ROOT)
    print("Robot face on http://0.0.0.0:%d/   reminders: /reminders" % PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), handler).serve_forever()
