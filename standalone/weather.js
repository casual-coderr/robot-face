// Weather props use ES3 and plain rectangles for Windows CE's old IE.
var weatherData = null, weatherAt = 0, weatherChangedAt = 0;
var weatherShowing = false, weatherRoutine = false, weatherPhase = 0;
var morningShowing = false, morningRoutine = false;
var weatherStrip, weatherReading, weatherAdvice, weatherCredit;
var weatherPixels = [], weatherUsed = 0, weatherDrawKey = '', weatherTextKey = '';
var weatherEyeInset = 0, morningEyeShift = 0;
var WEATHER_MOODS = {
  rain: { name: 'weatherRain', L: { w:46, h:78, tilt:0, arch:0 },
          R: { w:46, h:78, tilt:0, arch:0 }, lx:0, ly:9 },
  snow: { name: 'weatherSnow', L: { w:46, h:78, tilt:0, arch:0 },
          R: { w:46, h:78, tilt:0, arch:0 }, lx:0, ly:-26 }
};
WEATHER_MOODS.cold = WEATHER_MOODS.snow;  // Same coat pose, with no snowflakes.

function receiveWeather(data) {
  if (!weatherData || !data || weatherData.kind !== data.kind || weatherData.enabled !== data.enabled || weatherData.greeting !== data.greeting) {
    weatherChangedAt = now();
  }
  weatherData = data;
  weatherAt = now();
}

function initWeather() {
  weatherStrip = document.createElement('div');
  weatherStrip.style.position = 'absolute';
  weatherStrip.style.width = '480px'; weatherStrip.style.height = '54px';
  weatherStrip.style.background = '#061525'; weatherStrip.style.display = 'none';
  weatherStrip.style.zIndex = '10';
  screenEl.appendChild(weatherStrip);
  weatherReading = weatherTextBox(8, 3, 'bold 22px Arial, sans-serif', '#f0f6ff');
  weatherAdvice = weatherTextBox(8, 29, '16px Arial, sans-serif', '#aacbed');
  weatherCredit = weatherTextBox(340, 34, '9px Arial, sans-serif', '#7895b3');
  weatherCredit.style.width = '132px'; weatherCredit.style.textAlign = 'right';
  // Plain text attribution is readable on the panel without opening a browser link.
  setText(weatherCredit, 'Copenhagen / Open-Meteo');
}

function weatherTextBox(x, y, font, color) {
  var el = document.createElement('div');
  el.style.position = 'absolute'; el.style.left = x + 'px'; el.style.top = y + 'px';
  el.style.width = '464px'; el.style.height = '25px'; el.style.font = font;
  el.style.color = color; el.style.whiteSpace = 'nowrap';
  weatherStrip.appendChild(el);
  return el;
}

function prepareWeather(t) {
  var d = weatherData;
  var elapsed = t - weatherAt;
  var busy = notice || connLost || act || dragging || (toast && t < toast.until) || (napUntil && t < napUntil);
  morningShowing = !STANDALONE && !!d && d.greeting && elapsed < d.greeting_remaining * 1000 && !busy;
  weatherShowing = !STANDALONE && !!d && d.enabled && elapsed < d.window_remaining * 1000 && !busy;
  var usable = weatherShowing && (d.status === 'ok' || d.status === 'cached') && elapsed < d.valid_for * 1000;
  weatherPhase = (t - weatherChangedAt) % 60000;
  morningRoutine = morningShowing && weatherPhase < 8000;
  // Raise the prop for 12 seconds each minute; readings remain during idle time.
  weatherRoutine = usable && (d.kind === 'rain' || d.kind === 'snow' || d.kind === 'cold') && weatherPhase < 12000;
  weatherEyeInset = ease(weatherEyeInset, weatherRoutine ? 50 : morningRoutine ? 20 : 0, 0.3);
  morningEyeShift = ease(morningEyeShift, morningRoutine ? -25 : 0, 0.3);
}

// Draw one rectangle, mirroring both axes for the optional upside-down mode.
function weatherRect(x, y, w, h, color) {
  var item = weatherPixels[weatherUsed];
  if (!item) {
    var el = document.createElement('div');
    el.className = 'bk'; el.style.zIndex = '5';
    screenEl.appendChild(el);
    item = { el:el, key:'', visible:false }; weatherPixels.push(item);
  }
  weatherUsed++;
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  var key = x + ',' + y + ',' + w + ',' + h + ',' + color + ',' + FLIP;
  if (!item.visible) { item.el.style.display = 'block'; item.visible = true; }
  if (item.key === key) { return; }
  item.key = key;
  var s = item.el.style;
  s.left = (FLIP ? W - x - w : x) + 'px'; s.top = (FLIP ? H - y - h : y) + 'px';
  s.width = w + 'px'; s.height = h + 'px'; s.background = color;
}

// Filled stepped polygons, still drawn entirely with old-browser rectangle divs.
// Adjacent equal scanlines share a rectangle to keep the panel's DOM small.
function weatherShape(points, color) {
  var top = points[0][1], bottom = top, i, j, y;
  for (i = 1; i < points.length; i++) {
    top = Math.min(top, points[i][1]); bottom = Math.max(bottom, points[i][1]);
  }
  var runX = 0, runY = 0, runW = 0, runH = 0;
  for (y = top; y < bottom; y += 3) {
    var cuts = [], scan = Math.min(y + 1.5, bottom - 0.1);
    for (i = 0; i < points.length; i++) {
      j = (i + 1) % points.length;
      var a = points[i], b = points[j];
      if ((a[1] <= scan && b[1] > scan) || (b[1] <= scan && a[1] > scan)) {
        cuts.push(a[0] + (scan - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
      }
    }
    cuts.sort(function (a, b) { return a - b; });
    for (i = 0; i + 1 < cuts.length; i += 2) {
      var x = Math.round(cuts[i]), w = Math.max(1, Math.round(cuts[i + 1]) - x);
      var h = Math.min(3, bottom - y);
      if (runH && runX === x && runW === w && runY + runH === y) { runH += h; }
      else {
        if (runH) { weatherRect(runX, runY, runW, runH, color); }
        runX = x; runY = y; runW = w; runH = h;
      }
    }
  }
  if (runH) { weatherRect(runX, runY, runW, runH, color); }
}

function weatherLine(points, width, color) {
  for (var i = 1; i < points.length; i++) {
    var a = points[i - 1], b = points[i];
    var steps = Math.ceil(Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])) / width);
    for (var j = 0; j < steps; j++) {
      weatherRect(a[0] + (b[0] - a[0]) * j / steps, a[1] + (b[1] - a[1]) * j / steps, width, width, color);
    }
  }
}

function coatShape(points, y, color, mirror) {
  var shifted = [];
  for (var i = 0; i < points.length; i++) { shifted.push([mirror ? 480 - points[i][0] : points[i][0], y + points[i][1]]); }
  weatherShape(shifted, color);
}

function morningGloveShape(points, angle, color, scale) {
  // Rotate the glove around its cuff using rectangle geometry, including on CE.
  var rotated = [], c = Math.cos(angle), s = Math.sin(angle);
  for (var i = 0; i < points.length; i++) {
    var x = (points[i][0] - 27) * scale, y = (points[i][1] - 67) * scale;
    rotated.push([399 + x * c - y * s, 159 + x * s + y * c]);
  }
  weatherShape(rotated, color);
}

function drawWeather(t) {
  var d = weatherData;
  weatherStrip.style.display = weatherShowing ? 'block' : 'none';
  if (weatherShowing) {
    weatherStrip.style.left = '0px'; weatherStrip.style.top = FLIP ? '0px' : '218px';
    if (ROTPROP) { weatherStrip.style[ROTPROP] = FLIP ? 'rotate(180deg)' : ''; }
    var usable = (d.status === 'ok' || d.status === 'cached') && t - weatherAt < d.valid_for * 1000;
    var reading = usable ? Math.round(d.temperature) + '\u00b0C / ' + (d.summary || d.condition) :
                  d.status === 'loading' ? 'Getting Copenhagen weather...' : 'Weather unavailable';
    var advice = usable ? d.advice : 'Trying again next hour';
    if (usable && d.status === 'cached') { advice = 'Cached / ' + d.advice; }
    var key = reading + '|' + advice + '|' + FLIP;
    if (key !== weatherTextKey) {
      weatherTextKey = key;
      // Rotate the whole strip once in modern browsers; use existing glyph fallback on CE.
      weatherReading.innerHTML = esc(FLIP && !ROTPROP ? flipText(reading) : reading);
      weatherAdvice.innerHTML = esc(FLIP && !ROTPROP ? flipText(advice) : advice);
      weatherCredit.innerHTML = esc(FLIP && !ROTPROP ? flipText('Copenhagen / Open-Meteo') : 'Copenhagen / Open-Meteo');
      weatherAdvice.style.fontSize = advice.length > 32 ? '14px' : '16px';
    }
  }
  var drawKey = (morningRoutine ? 'wave,' + Math.floor(weatherPhase / 150) : weatherRoutine ? d.kind + ',' + Math.floor(weatherPhase / 150) : '') + ',' + FLIP;
  if (drawKey === weatherDrawKey) { return; }
  weatherDrawKey = drawKey; weatherUsed = 0;
  if (morningRoutine) {
    // Rounded four-digit cartoon glove, matching the approved morning preview.
    var angle = 0.2 + 0.18 * Math.sin(weatherPhase / 320);
    var cuff = [[10,65],[39,65],[44,69],[44,75],[39,79],[14,79],[8,75],[8,69]];
    var glove = [[17,66],[10,59],[5,49],[-2,34],[-4,27],[-3,23],[0,20],
                 [5,20],[9,24],[15,34],[15,10],[16,5],[19,2],[24,2],
                 [28,5],[29,10],[29,30],[33,11],[36,7],[40,7],[44,10],
                 [45,14],[43,35],[48,26],[51,22],[55,22],[59,26],
                 [60,31],[57,39],[51,53],[44,63],[37,68],[27,69]];
    morningGloveShape(cuff, angle, '#175a86', 1);
    morningGloveShape(cuff, angle, '#2ca6ed', 0.87);
    morningGloveShape(glove, angle, '#7eafd2', 1);
    morningGloveShape(glove, angle, '#cde7ff', 0.94);
    morningGloveShape([[1,37],[11,53],[19,60],[33,62],[45,56],
                       [37,66],[27,67],[18,64],[10,56]], angle, '#afd2ef', 0.94);
    morningGloveShape([[18,7],[23,6],[23,10],[19,12]], angle, '#f1faff', 0.94);
    morningGloveShape([[0,24],[4,24],[7,28],[1,29]], angle, '#f1faff', 0.94);
    morningGloveShape([[36,12],[39,11],[41,14],[38,16]], angle, '#f1faff', 0.94);
    var motionColor = Math.sin(weatherPhase / 320) > 0 ? '#3af' : '#287db5';
    weatherLine([[428,78],[438,83],[446,93]], 3, motionColor);
    weatherLine([[431,66],[444,72],[454,81],[459,94]], 3, motionColor);
  } else if (weatherRoutine) {
    var lift = Math.round(42 * (1 - Math.min(1, weatherPhase / 900)));
    var bob = Math.round(2 * Math.sin(weatherPhase / 400));
    var i, y, x;
    if (d.kind === 'rain') {
      // Dome, alternating fabric panels and curved ribs above the smaller eyes.
      y = 24 + lift + bob;
      for (i = 0; i < 16; i++) {
        var half = Math.round(132 * Math.sqrt(1 - Math.pow((62 - i * 4) / 64, 2)));
        weatherRect(240 - half, y + i * 4, half, 4, '#f0c62b');
        weatherRect(240, y + i * 4, half, 4, '#ffdb46');
      }
      weatherShape([[108,y+62],[127,y+55],[148,y+58],[169,y+50],[195,y+52],[216,y+48],
                    [240,y+50],[264,y+48],[285,y+52],[311,y+50],[332,y+58],[353,y+55],
                    [372,y+62],[372,y+67],[108,y+67]], '#000');
      weatherLine([[240,y+4],[223,y+15],[210,y+30],[201,y+43],[196,y+52]], 3, '#c4931b');
      weatherLine([[240,y+4],[257,y+15],[270,y+30],[279,y+43],[284,y+52]], 3, '#dab025');
      weatherRect(238, y - 5, 4, 10, '#ffdf59');
      weatherRect(238, y + 50, 4, 118, '#7897b2');
      weatherRect(238, y + 145, 5, 26, '#e7bb27');
      weatherRect(234, y + 170, 8, 6, '#e7bb27');
      weatherRect(220, y + 173, 17, 5, '#f5ce38');
      weatherRect(216, y + 168, 7, 7, '#f5ce38');
      weatherRect(215, y + 160, 5, 10, '#f5ce38');
      weatherShape([[229,y+138],[247,y+138],[253,y+144],[253,y+157],[247,y+164],
                    [229,y+164],[223,y+157],[223,y+144]], '#18374f');
      weatherShape([[231,y+140],[245,y+140],[251,y+146],[251,y+155],[245,y+161],
                    [231,y+161],[225,y+155],[225,y+146]], '#cfe3f7');
      weatherRect(226, y + 147, 9, 8, '#e5f3ff');
      for (i = 0; i < 8; i++) {
        x = i < 4 ? 34 + (i % 2) * 34 : 412 + (i % 2) * 26;
        weatherRect(x, 40 + ((i * 39 + Math.floor(weatherPhase / 80) * 7) % 155), 3, 12, '#3af');
      }
    } else {
      // Shaped parka sleeves, stitched pockets, a fleece collar and zipper teeth.
      y = 135 + lift + bob;
      coatShape([[157,9],[179,17],[220,26],[240,29],[260,26],[301,17],[323,9],
                 [345,34],[354,61],[345,82],[135,82],[126,61],[135,34]], y, '#0b2237', false);
      coatShape([[172,20],[220,29],[240,29],[260,29],[308,20],[326,82],[154,82]], y, '#20578c', false);
      for (var side = 0; side < 2; side++) {
        coatShape([[143,28],[167,20],[207,52],[185,77],[149,79],[131,61]], y, '#12334f', side);
        coatShape([[145,32],[164,25],[199,52],[182,72],[150,74],[136,59]], y, '#2872ad', side);
        coatShape([[148,36],[152,31],[184,56],[180,61]], y, '#347fb6', side);
        coatShape([[163,2],[169,-3],[177,1],[185,-1],[192,5],[211,8],[219,16],
                   [232,21],[228,32],[216,35],[199,25],[184,21],[166,21],[158,14],[158,7]], y, '#c5bda5', side);
        coatShape([[163,0],[170,-5],[178,-1],[185,-3],[193,3],[211,6],[217,13],
                   [231,19],[226,29],[215,31],[200,21],[183,17],[165,17],[156,10],[159,4]], y, '#f2ead4', side);
        var tug = Math.round(2 * Math.sin(weatherPhase / 260));
        coatShape([[188,30],[201,23],[220,40],[222,48],[206,65],[185,47]], y + tug, '#0b2237', side);
        coatShape([[190,33],[201,28],[216,42],[216,48],[205,59],[190,45]], y + tug, '#cfe3f7', side);
        coatShape([[192,35],[199,31],[205,38],[198,45]], y + tug, '#e8f5ff', side);
        coatShape([[172,68],[193,70],[192,73],[172,71]], y, '#12334f', side);
      }
      weatherRect(234, y + 28, 12, 54, '#0b2237');
      weatherRect(239, y + 32, 3, 50, '#b2c9da');
      for (i = 0; i < 8; i++) { weatherRect(236 + (i % 2) * 5, y + 43 + i * 5, 4, 2, '#d4e5ed'); }
      weatherRect(232, y + 28, 16, 17, '#9cb7ca');
      weatherRect(236, y + 32, 8, 8, '#0b2237');
      weatherRect(236, y + 26, 8, 4, '#d6e7f0');
      for (i = 0; d.kind === 'snow' && i < 3; i++) {
        x = i === 1 ? 401 : 55 + i * 10;
        x += Math.round(4 * Math.sin(weatherPhase / 700 + i));
        var sy = 28 + ((i * 51 + Math.floor(weatherPhase / 200) * 3) % 148);
        weatherRect(x, sy + 6, 17, 3, '#e7f4ff');
        weatherRect(x + 7, sy, 3, 17, '#e7f4ff');
        weatherRect(x + 2, sy + 2, 3, 3, '#e7f4ff');
        weatherRect(x + 12, sy + 2, 3, 3, '#e7f4ff');
        weatherRect(x + 2, sy + 12, 3, 3, '#e7f4ff');
        weatherRect(x + 12, sy + 12, 3, 3, '#e7f4ff');
      }
    }
  }
  for (var p = weatherUsed; p < weatherPixels.length; p++) {
    if (weatherPixels[p].visible) { weatherPixels[p].el.style.display = 'none'; weatherPixels[p].visible = false; }
  }
}
