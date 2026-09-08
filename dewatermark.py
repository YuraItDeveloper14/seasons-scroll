# -*- coding: utf-8 -*-
"""Removes the sparkle watermark from the source frames.

The mark is a fixed-position, semi-transparent white overlay:

    out = (1 - a) * bg + a * 255

so it can be solved away instead of painted over. Alpha is measured on the
summer frames, where the lawn under the mark is dark and smooth: a quadratic
surface is fitted to the ring around the mark to predict the background
underneath, and a = (out - bg) / (255 - bg). Dark background means a large
(255 - bg), which is what makes the estimate stable. The map is averaged over
many frames, then every frame is solved back to bg.
"""
import sys, io, os, glob
import numpy as np, cv2
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SP = (r"C:/Users/home/AppData/Local/Temp/claude/"
      r"C--Users-home-Desktop-Seasonsmoving/51973e2f-8af4-48c3-b9c1-3b665b7b982f/scratchpad")
SRC = os.path.join(SP, 'frames_png')
OUT = os.path.join(SP, 'frames_clean')
ROI = (1108, 552, 1212, 652)
CALIB = list(range(0, 70)) + list(range(70, 130))   # lawn, then lawn under leaves

x0, y0, x1, y1 = ROI
files = sorted(glob.glob(os.path.join(SRC, '*.png')))


def build_mask(S):
    """Where the overlay sits, from its average lift over a local median."""
    med = np.stack([cv2.medianBlur(S[i].astype(np.uint8), 31).astype(np.float32)
                    for i in range(len(S))])
    lift = (S - med).max(axis=3).mean(axis=0)
    core = (lift > max(2.5, lift.max() * 0.16)).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    if n > 1:                                    # keep the biggest blob only
        core = (lab == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    return core


def poly_background(patch, known):
    """Quadratic surface fitted to `known` pixels, evaluated everywhere."""
    H, W, _ = patch.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xs = (xx / W - .5).ravel(); ys = (yy / H - .5).ravel()
    A = np.stack([np.ones_like(xs), xs, ys, xs * xs, xs * ys, ys * ys], 1)
    k = known.ravel() > 0
    out = np.empty_like(patch)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A[k], patch[..., c].ravel()[k], rcond=None)
        out[..., c] = (A @ coef).reshape(H, W)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    S = np.stack([cv2.imread(f)[y0:y1, x0:x1].astype(np.float32) for f in files])
    core = build_mask(S)
    solve = cv2.dilate(core, np.ones((5, 5), np.uint8))          # include the soft rim
    known = 1 - cv2.dilate(core, np.ones((13, 13), np.uint8))    # clean ring for the fit
    ys, xs = np.nonzero(core)
    print("mark: %d px, frame box x %d-%d y %d-%d"
          % (core.sum(), x0 + xs.min(), x0 + xs.max(), y0 + ys.min(), y0 + ys.max()))

    acc = np.zeros(core.shape, np.float32); wsum = np.zeros(core.shape, np.float32)
    for i in CALIB:
        patch = S[i]
        bg = poly_background(patch, known)
        gap = 255.0 - bg
        a = ((patch - bg) / np.maximum(gap, 1.0)).mean(axis=2)
        w = np.clip(gap.mean(axis=2) / 255.0, 0, 1) ** 2          # trust dark backgrounds
        acc += np.clip(a, 0, .9) * w; wsum += w
    alpha = acc / np.maximum(wsum, 1e-6)
    alpha *= solve
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0) * solve
    alpha[alpha < 0.015] = 0.0
    print("alpha: %d px touched, mean %.3f, max %.3f"
          % (int((alpha > 0).sum()), alpha[alpha > 0].mean(), alpha.max()))
    np.save(os.path.join(SP, 'wm_alpha.npy'), alpha)

    a3 = np.dstack([alpha] * 3)
    # the algebra clears the body of the mark, but its anti-aliased rim is a
    # sub-pixel blend that no single alpha can undo — it leaves a hairline.
    # That ring, and only that ring, gets filled from its neighbours.
    rim = cv2.subtract(cv2.dilate(core, np.ones((9, 9), np.uint8)),
                       cv2.erode(core, np.ones((7, 7), np.uint8)))
    for i, f in enumerate(files):
        img = cv2.imread(f).astype(np.float32)
        p = img[y0:y1, x0:x1]
        soln = np.clip((p - a3 * 255.0) / np.maximum(1.0 - a3, 1e-3), 0, 255).astype(np.uint8)
        soln = cv2.inpaint(soln, rim, 4, cv2.INPAINT_TELEA)
        img[y0:y1, x0:x1] = soln.astype(np.float32)
        cv2.imwrite(os.path.join(OUT, os.path.basename(f)),
                    img.astype(np.uint8), [cv2.IMWRITE_PNG_COMPRESSION, 1])

    print("wrote %d cleaned frames" % len(files))
    for i in (10, 60, 90, 150, 220):
        b = cv2.imread(files[i])[y0:y1, x0:x1].astype(np.float32)
        a = cv2.imread(os.path.join(OUT, os.path.basename(files[i]))).astype(np.float32)[y0:y1, x0:x1]
        kb = poly_background(b, known); ka = poly_background(a, known)
        print("frame %3d  deviation from a clean surface: %5.2f -> %5.2f"
              % (i, np.abs(b - kb)[core > 0].mean(), np.abs(a - ka)[core > 0].mean()))


if __name__ == '__main__':
    main()
