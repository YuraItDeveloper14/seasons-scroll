# -*- coding: utf-8 -*-
"""Measures text contrast on the real rendered page, not on a model of it.

Chrome renders each chapter, the script asks the page where the text boxes
are, then separates glyph pixels from the background inside those boxes with
Otsu's threshold and reports the WCAG ratio between the two. This includes
every layer that actually ships: the film, both scrims, the wash behind the
column, and the text shadow.
"""
import sys, io, os
import numpy as np, cv2
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright

CHROME = os.path.join("C:\\", "Program Files", "Google", "Chrome",
                      "Application", "chrome.exe")
URL = "http://localhost:4173/"
CHAPTERS = [("hero", 0.0), ("summer", 0.25), ("autumn", 0.5),
            ("winter", 0.75), ("spring", 1.0)]

SETTLE = """async (f) => {
  const t = document.getElementById('track'), film = document.getElementById('film');
  window.scrollTo(0, (t.offsetHeight - innerHeight) * f);
  let prev = -1, still = 0;
  for (let i = 0; i < 240 && still < 8; i++){
    await new Promise(r => setTimeout(r, 16));
    if (Math.abs(film.currentTime - prev) < 0.001) still++; else still = 0;
    prev = film.currentTime;
  }
  await new Promise(r => setTimeout(r, 900));
}"""

RECTS = """() => {
  const H = innerHeight;
  const ps = [...document.querySelectorAll('.panel')];
  const p = ps.find(el => { const r = el.getBoundingClientRect();
                            return r.top < H*0.5 && r.bottom > H*0.5; }) || ps[0];
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };
  return { heading: box(p.querySelector('h1,h2')),
           lede:    box(p.querySelector('.lede')),
           eyebrow: box(p.querySelector('.eyebrow')) };
}"""


def rel(c):
    c = c / 255.0
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def luminance(bgr):
    b, g, r = bgr[..., 0], bgr[..., 1], bgr[..., 2]
    return .2126 * rel(r) + .7152 * rel(g) + .0722 * rel(b)


def ratio(img, box):
    if not box:
        return None
    x, y, w, h = box
    x, y = max(0, x), max(0, y)
    patch = img[y:y + h, x:x + w]
    if patch.size == 0 or patch.shape[0] < 4:
        return None
    grey = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    t, _ = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = grey >= t
    if ink.sum() < 40 or (~ink).sum() < 40:
        return None
    L = luminance(patch.astype(np.float32))
    # thin, letter-spaced type is mostly anti-aliased edge: taking the median
    # of the light class measures the edges, not the strokes a reader sees.
    # Compare the stroke cores against the background they sit on.
    lt = float(np.percentile(L[ink], 85))
    lb = float(np.median(L[~ink]))
    hi, lo = max(lt, lb) + .05, min(lt, lb) + .05
    return hi / lo


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME,
                               args=["--headless=new", "--disable-background-timer-throttling"])
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(URL, wait_until="load")
        pg.wait_for_function("document.body.classList.contains('is-ready')", timeout=30000)
        pg.wait_for_function("document.getElementById('film').readyState >= 4", timeout=90000)

        print("%-9s %10s %10s %10s" % ("chapter", "heading", "body", "label"))
        print("-" * 43)
        worst = 99.0
        for name, frac in CHAPTERS:
            pg.evaluate(SETTLE, frac)
            rects = pg.evaluate(RECTS)
            shot = os.path.join("shots", "_contrast.png")
            pg.screenshot(path=shot)
            img = cv2.imread(shot)
            vals = [ratio(img, rects[k]) for k in ("heading", "lede", "eyebrow")]
            worst = min([worst] + [v for v in vals if v])
            print("%-9s %10s %10s %10s" % (
                name, *["%.1f" % v if v else "-" for v in vals]))
        print("-" * 43)
        print("lowest measured contrast anywhere: %.1f : 1   (WCAG AA body 4.5, large text 3.0)"
              % worst)
        os.path.exists(os.path.join("shots", "_contrast.png")) and os.remove(
            os.path.join("shots", "_contrast.png"))
        b.close()


if __name__ == '__main__':
    main()
