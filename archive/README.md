# Archive

Things that are not part of the running project any more. Nothing here is used by
`server.py`, `face.html` or the control pages. Move something back if you need it.

| Item | What it was | Why archived |
|---|---|---|
| `output/` | preview images (weather, Halloween) with the prompt that made them, plus old server logs from testing | design previews and logs, not needed to run |
| `sound-test.html` | page for trying each sound by hand on the panel (Oct 28) | one-off test page |
| `standalone/` | generated microSD build (an old copy of the face, weather.js and reminders) | out of date; `python make_standalone.py` creates a fresh `standalone/` in the project folder |

`__pycache__/` is left in place. Python recreates it, so it can be deleted at any time.
