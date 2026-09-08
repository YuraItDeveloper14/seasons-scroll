# -*- coding: utf-8 -*-
"""Drives real scrolling in a real Chrome (headless=new, so there is a real
compositor and rAF runs at display rate) and records how closely the film
follows the scroll: lag while moving, how many distinct frames actually get
shown, and whether it ever stalls. Also captures the six chapters."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright

CHROME = os.path.join("C:\\", "Program Files", "Google", "Chrome",
                      "Application", "chrome.exe")
URL = "http://localhost:4173/"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")

MEASURE = """
async ([pxPerTick, ticks, msPerTick]) => {
  const clamp01 = v => v < 0 ? 0 : v > 1 ? 1 : v;
  /* same scroll->film cue mapping the page uses, so the target we compare
     against is the one the page is actually aiming for */
  const CUE = [[0,0],[.25,.12],[.5,.40],[.75,.67],[1,.93]];
  const filmAt = s => { for (let i=1;i<CUE.length;i++){ if (s<=CUE[i][0]){
      const [a,av]=CUE[i-1],[b,bv]=CUE[i]; return av+(bv-av)*((s-a)/(b-a)); } }
    return CUE[CUE.length-1][1]; };
  const film  = document.getElementById('film');
  const track = document.getElementById('track');
  const span  = track.offsetHeight - innerHeight;
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 600));

  const samples = [], seen = new Set();
  let rafCount = 0, stop = false;
  const tick = () => { rafCount++; if (!stop) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);

  const t0 = performance.now();
  for (let i = 0; i < ticks; i++){
    window.scrollBy(0, pxPerTick);
    await new Promise(r => setTimeout(r, msPerTick));
    const p = filmAt(clamp01(scrollY / span));
    samples.push({ want: p*(film.duration - 1/60), have: film.currentTime });
    seen.add(Math.round(film.currentTime * 60));
  }
  const target = samples[samples.length-1].want;
  let settleMs = 0;
  const s0 = performance.now();
  for (let i = 0; i < 200; i++){
    await new Promise(r => setTimeout(r, 16));
    seen.add(Math.round(film.currentTime * 60));
    if (Math.abs(film.currentTime - target) < 0.02){ settleMs = performance.now()-s0; break; }
    settleMs = performance.now()-s0;
  }
  stop = true;
  const elapsed = performance.now() - t0;
  return { samples, distinct: seen.size, rafFps: rafCount/(elapsed/1000),
           settleMs, finalLag: Math.abs(film.currentTime - target),
           duration: film.duration, span };
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=[
        "--headless=new",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--autoplay-policy=no-user-gesture-required",
    ])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console." + m.type + ": " + m.text)
          if m.type == "error" else None)

    pg.goto(URL, wait_until="load")
    pg.wait_for_function("document.body.classList.contains('is-ready')", timeout=30000)
    pg.wait_for_function("document.getElementById('film').readyState >= 4", timeout=90000)

    print("scroll gesture                 rAF     distinct   lag avg / max     settle")
    print("-" * 76)
    last = None
    for label, px, ticks, ms in [
        ("slow drag    40px / 60ms", 40, 60, 60),
        ("wheel       120px / 50ms", 120, 34, 50),
        ("fast flick  400px / 30ms", 400, 12, 30),
    ]:
        r = pg.evaluate(MEASURE, [px, ticks, ms])
        lags = [abs(s["have"] - s["want"]) for s in r["samples"]]
        print("%-26s %5.1ffps  %4d      %.3fs / %.3fs   %4.0fms" % (
            label, r["rafFps"], r["distinct"],
            sum(lags)/len(lags), max(lags), r["settleMs"]))
        last = r

    print("-" * 76)
    print("film %.3fs at 60fps = %d frames over a %dpx scroll span -> %.2f px per frame"
          % (last["duration"], round(last["duration"]*60), last["span"],
             last["span"]/(last["duration"]*60)))
    print("page errors: %s" % (errors if errors else "none"))

    os.makedirs(SHOTS, exist_ok=True)
    # chapters sit at every fifth of the scroll; that is where each one is
    # centred, and now also where its own season is on screen
    for name, frac in [("1-hero",0.0), ("2-summer",0.25), ("3-autumn",0.5),
                       ("4-winter",0.75), ("5-spring",1.0)]:
        pg.evaluate("""async (f) => {
            const t=document.getElementById('track');
            window.scrollTo(0,(t.offsetHeight-innerHeight)*f);
            const film=document.getElementById('film');
            let prev=-1, still=0;
            for (let i=0;i<240 && still<8;i++){
              await new Promise(r=>setTimeout(r,16));
              if (Math.abs(film.currentTime-prev)<0.001) still++; else still=0;
              prev=film.currentTime;
            }
            await new Promise(r=>setTimeout(r,900));
        }""", frac)
        pg.screenshot(path=os.path.join(SHOTS, name + ".png"))
    print("screenshots written to %s" % SHOTS)
    b.close()
