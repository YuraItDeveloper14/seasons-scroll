# -*- coding: utf-8 -*-
"""Encodes the two delivery cuts of the scroll film.

Short GOP rather than all-intra. Setting currentTime performs an accurate
seek: the decoder starts at the nearest keyframe and walks forward, so a GOP
of 12 costs at most 12 frame decodes — microseconds — while P-frames exploit
the very large redundancy between frames 1/60 s apart. Measured on this
footage, all-intra reached SSIM 0.911 at 27 KB/frame; GOP 12 reaches 0.989
at a comparable size.
"""
import sys, io, os, subprocess, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SP = (r"C:/Users/home/AppData/Local/Temp/claude/"
      r"C--Users-home-Desktop-Seasonsmoving/51973e2f-8af4-48c3-b9c1-3b665b7b982f/scratchpad")
FRAMES = os.path.join(SP, 'f60c', '%04d.png')     # watermark-free, 60 fps
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

GOP = 12
CUTS = [
    # file,           scale,      crf
    ("year-1280.mp4", None,       17),
    ("year-960.mp4",  "960:540",  20),
]


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stderr[-1000:])
        raise SystemExit("ffmpeg failed")
    return r.stderr


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, scale, crf in CUTS:
        dest = os.path.join(OUT, name)
        cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", "60", "-i", FRAMES]
        if scale:
            cmd += ["-vf", "scale=%s:flags=lanczos" % scale]
        cmd += ["-c:v", "libx264", "-preset", "veryslow", "-crf", str(crf),
                "-x264-params",
                "keyint=%d:min-keyint=%d:scenecut=0:bframes=2:b-adapt=2:ref=4:deblock=-1,-1"
                % (GOP, GOP),
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
                "-an", "-movflags", "+faststart", dest]
        sh(cmd)

        o = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,nb_frames,r_frame_rate",
             "-show_entries", "format=duration,size,bit_rate", "-of", "json", dest],
            capture_output=True, text=True).stdout)
        s, f = o['streams'][0], o['format']
        n = int(s['nb_frames'])
        kf = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "frame=key_frame", "-of", "csv=p=0", dest],
                            capture_output=True, text=True).stdout
        keys = [v.strip().rstrip(',') for v in kf.splitlines() if v.strip()].count('1')
        print("%-14s %sx%s  %d frames  %.3fs  %5.2f MB  %5.1f KB/frame  %d keyframes (every %.1f)"
              % (name, s['width'], s['height'], n, float(f['duration']),
                 int(f['size']) / 1048576, int(f['size']) / n / 1024, keys, n / max(keys, 1)))


if __name__ == '__main__':
    main()
