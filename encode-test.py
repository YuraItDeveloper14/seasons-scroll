# -*- coding: utf-8 -*-
"""Compares encoder settings for the scroll film on quality-per-byte.

All-intra makes every frame seekable but costs roughly three times the bits
of a short GOP for the same picture. A short GOP is still accurate to seek
(currentTime does an exact seek: decode from the nearest keyframe forward),
so the question is only how many frames the decoder has to walk. This
measures what each setting actually buys.
"""
import sys, io, os, subprocess, json, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SP = (r"C:/Users/home/AppData/Local/Temp/claude/"
      r"C--Users-home-Desktop-Seasonsmoving/51973e2f-8af4-48c3-b9c1-3b665b7b982f/scratchpad")
ENC = os.path.join(SP, 'enc2')

CONFIGS = [
    # name,        gop, bframes, crf
    ("intra crf29",  1, 0, 29),   # what shipped, for reference
    ("gop8  crf20",  8, 0, 20),
    ("gop12 crf19", 12, 0, 19),
    ("gop12 crf17", 12, 0, 17),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stderr[-800:])
        raise SystemExit("ffmpeg failed")
    return r.stderr


def encode(src_pattern, fps, name, gop, bf, crf, out):
    xp = "keyint=%d:min-keyint=%d:scenecut=0:bframes=%d" % (gop, gop, bf)
    if gop == 1:
        xp += ":ref=1"
    run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", src_pattern,
         "-c:v", "libx264", "-preset", "slower", "-crf", str(crf),
         "-x264-params", xp, "-pix_fmt", "yuv420p", "-profile:v", "high",
         "-an", "-movflags", "+faststart", out])


def ssim_vs(ref_pattern, fps, enc_path):
    err = run(["ffmpeg", "-v", "info", "-i", enc_path, "-framerate", str(fps),
               "-i", ref_pattern, "-lavfi", "ssim", "-f", "null", "-"])
    for line in err.splitlines():
        if "SSIM" in line and "All:" in line:
            return float(line.split("All:")[1].split()[0])
    return float("nan")


def keyframes(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "frame=key_frame", "-of", "csv=p=0", path],
                       capture_output=True, text=True).stdout
    vals = [v.strip().rstrip(',') for v in o.splitlines() if v.strip()]
    return vals.count('1'), len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default=os.path.join(SP, 'frames_clean'))
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    os.makedirs(ENC, exist_ok=True)
    pattern = os.path.join(a.frames, "%04d.png")

    print("source frames: %s at %d fps" % (a.frames, a.fps))
    print("%-13s %8s %10s %8s  %s" % ("setting", "size", "KB/frame", "SSIM", "keyframes"))
    print("-" * 62)
    for name, gop, bf, crf in CONFIGS:
        out = os.path.join(ENC, name.replace(" ", "") + ".mp4")
        encode(pattern, a.fps, name, gop, bf, crf, out)
        size = os.path.getsize(out)
        kf, total = keyframes(out)
        s = ssim_vs(pattern, a.fps, out)
        print("%-13s %6.1fMB %9.1f %8.4f  %d/%d" % (
            name, size / 1048576, size / total / 1024, s, kf, total))


if __name__ == '__main__':
    main()
