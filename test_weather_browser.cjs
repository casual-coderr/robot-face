// Optional real-browser checks. Pass an installed playwright-core directory.
// node test_weather_browser.cjs <path-to-playwright-core> [chromium-executable]
const { chromium } = require(process.argv[2] || 'playwright-core');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const weather = (overrides = {}) => ({
  enabled: true, greeting: false, greeting_remaining: 0, window_remaining: 9000,
  status: 'ok', valid_for: 5400, temperature: 8, condition: 'Rain',
  kind: 'rain', advice: 'Take an umbrella', summary: 'Rain this afternoon', snow_later: false, ...overrides
});
let state = { ts: Date.UTC(2026, 9, 31, 6, 30) / 1000, night: [21, 7],
  notice: null, sound: 'all', weather: weather({ enabled: false, greeting: true, greeting_remaining: 5400 }) };
let autoPoll = true;
const app = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/api/state') {
    res.setHeader('Content-Type', 'application/javascript');
    if (!autoPoll) return res.end('lastOk = now();'); // Manual fixtures control expiry without polling races.
    return res.end('onState(' + JSON.stringify(state) + ');');
  }
  if (url.pathname.startsWith('/api/')) return res.end(';');
  const file = path.join(__dirname, url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
  if (!fs.existsSync(file)) { res.statusCode = 404; return res.end(); }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.wav') ? 'audio/wav' : 'text/html');
  res.end(fs.readFileSync(file));
});

(async () => {
  await new Promise(resolve => app.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.argv[3] ? { executablePath: process.argv[3] } : {}) });
    const page = await browser.newPage({ viewport: { width: 480, height: 272 } });
    await page.addInitScript(() => {
      window.playedSounds = [];
      window.Audio = function (url) {
        this.play = function () { window.playedSounds.push(url); return Promise.resolve(); };
      };
    });
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    fs.mkdirSync(path.join(__dirname, 'output', 'weather'), { recursive: true });
    const screenshot = name => page.screenshot({ path: path.join(__dirname, 'output', 'weather', name + '.png') });
    const inject = async data => {
      state.weather = data;
      await page.evaluate(s => { toast = null; act = null; lastTouch = now(); onState(s); }, state);
    };
    const positions = () => page.evaluate(() => weatherPixels.map(p => p.el.style.left + ',' + p.el.style.top).join('|'));
    await page.goto('http://127.0.0.1:' + app.address().port);
    await page.waitForFunction(() => morningRoutine && document.getElementById('note').textContent === 'Good morning!');
    autoPoll = false;
    await page.waitForTimeout(1000);
    await screenshot('morning');
    let before = await positions();
    await page.waitForTimeout(450);
    assert.notEqual(await positions(), before, 'Rounded glove must wave');
    assert.deepEqual(await page.evaluate(() => playedSounds), [], 'Morning wave must be silent even with all sounds enabled');

    state.ts = Date.UTC(2026, 9, 31, 8, 30) / 1000;
    await inject(weather());
    // The existing night-to-day greeting may briefly take priority.
    await page.waitForFunction(() => weatherRoutine && weatherShowing, { timeout: 10000 });
    await page.waitForTimeout(1000);
    await screenshot('rain');
    assert.equal(await page.evaluate(() => Math.round(cur[0].w)), 46, 'Weather eyes are smaller');
    assert.equal(await page.evaluate(() => Math.round(weatherEyeInset)), 50, 'Weather eyes move closer together');
    assert.match(await page.evaluate(() => weatherReading.textContent), /8.C \/ Rain/);
    before = await positions();
    await page.waitForTimeout(450);
    assert.notEqual(await positions(), before, 'Rain must fall');
    assert.deepEqual(await page.evaluate(() => playedSounds), [], 'Daybreak greeting and weather must be silent');

    await inject(weather({ temperature: -2, condition: 'Clear', kind: 'snow', advice: 'Put on a warm coat', summary: 'Snow this evening', snow_later: true }));
    await page.waitForFunction(() => weatherRoutine && weatherData.kind === 'snow');
    await page.waitForTimeout(1000);
    await screenshot('snow');
    assert.ok(await page.evaluate(() => weatherPixels.length > 100), 'Coat has detailed geometry');
    assert.match(await page.evaluate(() => clockEl.textContent), /08:30/);
    assert.deepEqual(await page.evaluate(() => weatherPixels.filter(p => {
      if (!p.visible) return false;
      var r = p.el.getBoundingClientRect();
      return r.left < 470 && r.right > 435 && r.top < 22 && r.bottom > 6;
    }).map(p => p.el.getAttribute('style'))), [], 'Weather props leave the clock clear');
    before = await positions();
    await page.waitForTimeout(450);
    assert.notEqual(await positions(), before, 'Snow must fall');
    assert.equal(await page.evaluate(() => weatherAdvice.textContent), 'Put on a warm coat');
    assert.match(await page.evaluate(() => weatherReading.textContent), /Snow this evening/);

    await inject(weather({ condition: 'Clear', kind: 'cold', advice: 'Put on a warm coat', summary: 'Cold tonight' }));
    await page.waitForFunction(() => weatherRoutine && weatherData.kind === 'cold');
    await page.waitForTimeout(1000);
    await screenshot('cold');
    assert.match(await page.evaluate(() => weatherReading.textContent), /Cold tonight/);
    assert.equal(await page.evaluate(() => weatherAdvice.textContent), 'Put on a warm coat');
    assert.equal(await page.evaluate(() => weatherPixels.filter(p => p.visible && p.el.style.background === 'rgb(231, 244, 255)').length), 0, 'Cold coat has no snowflakes');
    assert.equal(await page.evaluate(() => weatherPixels.filter(p => p.visible && p.el.style.background === 'rgb(255, 219, 70)').length), 0, 'Coat does not also show an umbrella');

    await page.evaluate(() => { weatherChangedAt = now() - 20000; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing && !weatherRoutine), true, 'Reading remains between routines');
    await page.evaluate(() => { notice = { mood: 'surprised', text: 'Medicine time' }; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing || weatherRoutine), false, 'Reminders take priority');
    await page.evaluate(() => { notice = null; dragging = true; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing), false, 'Touch takes priority');
    await page.evaluate(() => { dragging = false; napUntil = now() + 60000; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing), false, 'Explicit nap takes priority');
    await page.evaluate(() => { napUntil = 0; });

    await inject(weather({ status: 'cached' }));
    await page.waitForTimeout(150);
    assert.match(await page.evaluate(() => weatherAdvice.textContent), /Cached/);
    await inject(weather({ status: 'unavailable', kind: undefined }));
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherRoutine), false);
    assert.equal(await page.evaluate(() => weatherReading.textContent), 'Weather unavailable');
    await inject(weather({ valid_for: 1 }));
    await page.evaluate(() => { weatherAt = now() - 2000; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherRoutine), false, 'Expired data cannot animate');
    await inject(weather({ window_remaining: 1 }));
    await page.evaluate(() => { weatherAt = now() - 2000; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing), false, 'Display expires at 11 even without another poll');
    await inject(weather({ enabled: false }));
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing || morningShowing), false);
    await page.waitForTimeout(1000);
    assert.equal(await page.evaluate(() => Math.round(weatherEyeInset)), 0, 'Eye spacing restores after weather');

    await inject(weather({ kind: 'snow', condition: 'Snow', advice: 'Put on a warm coat' }));
    await page.evaluate(() => { FLIP = true; layoutFlip(); });
    await page.waitForTimeout(200);
    assert.equal(await page.evaluate(() => weatherStrip.style.top), '0px');
    assert.equal(await page.evaluate(() => weatherStrip.style.transform), 'rotate(180deg)');
    // Selected Halloween mode keeps friendly red eyes and small horns beside the weather.
    state.ts = Date.UTC(2026, 9, 31, 22, 30) / 1000;
    await page.evaluate(() => { FLIP = false; layoutFlip(); });
    state.mode = 'halloween';
    await inject(weather({ halloween: true, condition: 'Cloudy' }));
    await page.waitForTimeout(1200);
    assert.equal(await page.evaluate(() => HALLOWEEN && weatherShowing && !weatherRoutine), true);
    assert.equal(await page.evaluate(() => mood.name), 'devil');
    assert.equal(await page.evaluate(() => curColor), '#f44');
    assert.equal(await page.evaluate(() => Math.round(cur[0].tilt)), 0, 'Eyes are friendly, without angry slants');
    assert.equal(await page.evaluate(() => horns[0].filter(h => h.style.display === 'block').length), 5);
    assert.equal(await page.evaluate(() => horns[0][0].style.height), '5px', 'Horns stay small');
    assert.match(await page.evaluate(() => weatherReading.textContent), /8.C \/ Cloudy/);
    await screenshot('halloween');
    await page.evaluate(() => { poke(4); });
    await page.waitForTimeout(500);
    assert.equal(await page.evaluate(() => mood.name), 'wink');
    assert.equal(await page.evaluate(() => weatherShowing && !toast.shake && toast.text === ''), true, 'Pokes stay playful and keep weather');
    assert.equal(await page.evaluate(() => horns[0][0].style.display), 'block', 'Horns stay through expressions');
    await page.evaluate(() => { toast = null; napUntil = now() + 60000; lastTouch = now() - 20000; });
    await page.waitForFunction(() => mood.name === 'asleep', { timeout: 5000 });
    assert.equal(await page.evaluate(() => mood.name), 'asleep', 'Explicit naps still work tonight');
    await page.evaluate(() => { napUntil = 0; toast = null; });
    state.mode = 'normal';
    await inject(weather({ halloween: false, enabled: false }));
    await page.waitForTimeout(1200);
    assert.equal(await page.evaluate(() => HALLOWEEN || weatherShowing), false, 'Normal mode restores the usual weather schedule');
    assert.equal(await page.evaluate(() => mood.name), 'asleep');
    assert.equal(await page.evaluate(() => curColor), '#2a4a7a', 'Blue restores automatically');
    await page.waitForFunction(() => horns[0].every(h => h.style.display === 'none'), { timeout: 5000 });
    assert.equal(await page.evaluate(() => horns[0].filter(h => h.style.display === 'block').length), 0);
    await page.evaluate(() => { STANDALONE = true; });
    await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => weatherShowing || morningShowing), false, 'Standalone never displays weather');
    await page.evaluate(() => {
      HALLOWEEN = true; hallGreeted = false; applyColor();
      runCommand({name: 'wake'});
    });
    assert.deepEqual(await page.evaluate(() => playedSounds), [], 'Automatic seasonal greeting and wake greeting must be silent');
    assert.deepEqual(await page.evaluate(() => stepErr), {});
    assert.deepEqual(errors, []);
    console.log('Browser checks passed: greeting, rain/snow animation, transitions, priority, cache, expiry, flip, standalone.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => app.close(resolve));
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
