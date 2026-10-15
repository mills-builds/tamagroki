#!/usr/bin/env python3
"""Build + run the headless face simulator and produce PNG/GIF previews.
Usage: python3 sim/face/render.py [--bg 9B7FE0] [--out sim/face/out]"""
import argparse, csv, os, subprocess, sys, tempfile, glob
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--bg", default="9B7FE0")
ap.add_argument("--out", default=os.path.join(here, "out"))
ap.add_argument("--build", default="/tmp/grokface_simbuild")
a = ap.parse_args()

subprocess.check_call(["cmake", "-S", here, "-B", a.build, "-DCMAKE_BUILD_TYPE=Release"], stdout=subprocess.DEVNULL)
subprocess.check_call(["cmake", "--build", a.build, "-j8"], stdout=subprocess.DEVNULL)
os.makedirs(a.out, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    subprocess.check_call([os.path.join(a.build, "grokface_sim"), tmp, a.bg])
    rows = list(csv.reader(open(os.path.join(tmp, "frames.csv"))))
    by_state = {}
    for fr, st, _ in rows:
        by_state.setdefault(st, []).append(int(fr))
    img = lambda i: Image.open(os.path.join(tmp, f"f{i:05d}.ppm")).convert("RGB")
    stills = []
    for st, frames in by_state.items():
        blk = lambda i: sum(1 for p in img(i).resize((96, 96)).get_flattened_data() if p[0] < 40)
        cand = frames[len(frames) // 3:]
        pick = cand[-1] if st == "sleep" else max(cand[::3], key=blk)  # skip blink frames
        im = img(pick); im.save(os.path.join(a.out, f"{st}.png")); stills.append((st, im))
        seq = [img(i).resize((240, 240), Image.LANCZOS) for i in frames]
        seq[0].save(os.path.join(a.out, f"{st}.gif"), save_all=True, append_images=seq[1:], duration=40, loop=0)
    all_frames = [img(int(r[0])).resize((240, 240), Image.LANCZOS) for r in rows]
    all_frames[0].save(os.path.join(a.out, "timeline.gif"), save_all=True, append_images=all_frames[1:], duration=40, loop=0)
    # blink still: find the most-closed frame in idle by counting black pixels
    idle = by_state["idle"]
    blackest = min(idle, key=lambda i: sum(1 for p in img(i).resize((96, 96)).get_flattened_data() if p[0] < 40))
    img(blackest).save(os.path.join(a.out, "idle_blink.png"))
    sheet = Image.new("RGB", (240 * len(stills), 260), "white")
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for k, (st, im) in enumerate(stills):
        sheet.paste(im.resize((240, 240), Image.LANCZOS), (240 * k, 20)); d.text((240 * k + 8, 4), st, fill="black")
    sheet.save(os.path.join(a.out, "contact_sheet.png"))
print("wrote", sorted(os.path.basename(p) for p in glob.glob(os.path.join(a.out, "*"))))
