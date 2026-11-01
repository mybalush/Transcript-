"""Builds the evacuation clip: (satellite intro) -> main hall from both
entrances -> two corridors with animated arrows to the emergency exits.

Usage: python3 make_clip.py [--satellite path/to/satellite.jpg] [-o out.mp4]
"""
import argparse, math, os, subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
A = lambda n: os.path.join(HERE, "assets", n)
W, H, FPS, XF = 1920, 1080, 30, 0.7  # XF = crossfade seconds
GREEN, WHITE, DARK = (0, 200, 83), (255, 255, 255), (12, 18, 28)
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font = lambda s, b=True: ImageFont.truetype(BOLD if b else REG, s)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rect(r0, r1, t):
    return tuple(lerp(a, b, t) for a, b in zip(r0, r1))


def view(img, rect, size):
    """Sub-pixel crop of rect=(x0,y0,x1,y1) resized to size (smooth zooms)."""
    return img.transform(size, Image.EXTENT, rect, resample=Image.BICUBIC)


def caption(frame, title, sub=None, alpha=1.0):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f1, f2 = font(54), font(34, False)
    tw = d.textlength(title, font=f1)
    sw = d.textlength(sub, font=f2) if sub else 0
    bw = int(max(tw, sw) + 80)
    bh = 150 if sub else 100
    x0, y0 = 60, H - bh - 60
    a = int(215 * alpha)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 18, fill=DARK + (a,))
    d.rectangle((x0, y0 + 14, x0 + 10, y0 + bh - 14), fill=GREEN + (int(255 * alpha),))
    d.text((x0 + 40, y0 + 18), title, font=f1, fill=WHITE + (int(255 * alpha),))
    if sub:
        d.text((x0 + 40, y0 + 90), sub, font=f2, fill=(210, 220, 230, int(255 * alpha)))
    frame.alpha_composite(ov)


def arrow_poly(cx, cy, ang, size):
    """Chunky arrow pointing along ang, tip at (cx,cy)."""
    pts = [(0, 0), (-0.55, -0.5), (-0.55, -0.2), (-1.2, -0.2),
           (-1.2, 0.2), (-0.55, 0.2), (-0.55, 0.5)]
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (x * c - y * s) * size, cy + (x * s + y * c) * size) for x, y in pts]


# ---------------------------------------------------------------- scenes
class Scene:
    dur = 4.0

    def frame(self, t):  # -> RGBA W x H
        raise NotImplementedError


class TitleCard(Scene):
    def __init__(self, title, sub, dur=3.0):
        self.title, self.sub, self.dur = title, sub, dur

    def frame(self, t):
        im = Image.new("RGBA", (W, H), DARK + (255,))
        d = ImageDraw.Draw(im)
        a = ease(t / 0.8)
        f1, f2 = font(84), font(42, False)
        tw = d.textlength(self.title, font=f1)
        sw = d.textlength(self.sub, font=f2)
        y = H // 2 - 90 + (1 - a) * 30
        d.text(((W - tw) / 2, y), self.title, font=f1, fill=WHITE + (int(255 * a),))
        d.rectangle(((W - 220) / 2, y + 120, (W + 220) / 2, y + 128), fill=GREEN + (int(255 * a),))
        d.text(((W - sw) / 2, y + 160), self.sub, font=f2, fill=(190, 205, 220, int(255 * a)))
        return im


class SatelliteZoom(Scene):
    """Zooms from a wide satellite image into the building (target in px)."""

    def __init__(self, path, target, dur=6.0, label="Site location"):
        self.img = Image.open(path).convert("RGB")
        self.target, self.dur, self.label = target, dur, label

    def frame(self, t):
        iw, ih = self.img.size
        r0 = (0, (ih - iw * 9 / 16) / 2, iw, (ih + iw * 9 / 16) / 2) if iw * 9 / 16 <= ih \
            else ((iw - ih * 16 / 9) / 2, 0, (iw + ih * 16 / 9) / 2, ih)
        tx, ty = self.target
        w1 = (r0[2] - r0[0]) / 4
        r1 = (tx - w1 / 2, ty - w1 * 9 / 32, tx + w1 / 2, ty + w1 * 9 / 32)
        k = ease(t / (self.dur - 0.8))
        r = lerp_rect(r0, r1, k)
        im = view(self.img, r, (W, H)).convert("RGBA")
        # pulsing marker on the building
        fx = (tx - r[0]) / (r[2] - r[0]) * W
        fy = (ty - r[1]) / (r[3] - r[1]) * H
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        p = (t * 1.2) % 1
        rr = 30 + 70 * p
        d.ellipse((fx - rr, fy - rr, fx + rr, fy + rr), outline=GREEN + (int(255 * (1 - p)),), width=6)
        d.ellipse((fx - 14, fy - 14, fx + 14, fy + 14), fill=GREEN + (255,), outline=WHITE + (255,), width=4)
        im.alpha_composite(ov)
        caption(im, self.label, "Satellite view", ease(t / 0.6))
        return im


class HallPan(Scene):
    def __init__(self, path, title, sub, drift=+1, dur=4.5):
        self.img = Image.open(path).convert("RGB")
        self.title, self.sub, self.drift, self.dur = title, sub, drift, dur

    def frame(self, t):
        iw, ih = self.img.size
        h0 = iw * 9 / 16
        r0 = (0, (ih - h0) / 2, iw, (ih + h0) / 2)
        z = 1.18
        w1, h1 = iw / z, h0 / z
        cx = iw / 2 + self.drift * (iw - w1) / 2 * 0.8
        cy = ih / 2 - 10
        r1 = (cx - w1 / 2, cy - h1 / 2, cx + w1 / 2, cy + h1 / 2)
        im = view(self.img, lerp_rect(r0, r1, ease(t / self.dur)), (W, H)).convert("RGBA")
        caption(im, self.title, self.sub, ease((t - 0.3) / 0.6))
        return im


class CorridorExit(Scene):
    """Portrait corridor photo: push in toward the end door, animated arrows
    flowing along the floor to the door, glowing door frame and label."""

    def __init__(self, path, door, path_start, label, sub, dur=7.0):
        self.img = Image.open(path).convert("RGB")
        self.door = door            # (x0,y0,x1,y1) of the exit door in image px
        self.p0 = path_start        # floor point near the camera, image px
        self.label, self.sub, self.dur = label, sub, dur
        iw, ih = self.img.size
        self.fw, self.fh = int(H * iw / ih), H
        self.fx = (W - self.fw) // 2
        self.bg = self.img.resize((W, int(W * ih / iw))).crop(
            (0, (int(W * ih / iw) - H) // 2, W, (int(W * ih / iw) + H) // 2))
        self.bg = self.bg.filter(ImageFilter.GaussianBlur(40))
        self.bg = Image.blend(self.bg, Image.new("RGB", (W, H), DARK), 0.55).convert("RGBA")

    def frame(self, t, cap=True):
        iw, ih = self.img.size
        dx = (self.door[0] + self.door[2]) / 2
        dy = (self.door[1] + self.door[3]) / 2
        z = 1.9
        w1, h1 = iw / z, ih / z
        cx = min(max(dx, w1 / 2), iw - w1 / 2)
        cy = min(max(dy + h1 * 0.08, h1 / 2), ih - h1 / 2)
        r = lerp_rect((0, 0, iw, ih), (cx - w1 / 2, cy - h1 / 2, cx + w1 / 2, cy + h1 / 2),
                      ease(t / (self.dur * 0.75)))
        im = self.bg.copy()
        im.paste(view(self.img, r, (self.fw, self.fh)), (self.fx, 0))
        sx = self.fw / (r[2] - r[0])

        def m(p):  # image px -> frame px
            return (self.fx + (p[0] - r[0]) * sx, (p[1] - r[1]) * sx)

        S = 2  # supersample overlay for smooth edges
        ov = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        show = ease((t - 0.8) / 0.6)
        if show > 0:
            a = int(255 * show)
            # flowing floor arrows
            tip = (dx, self.door[3] - (self.door[3] - self.door[1]) * 0.05)
            P0, P1 = m(self.p0), m(tip)
            ang = math.atan2(P1[1] - P0[1], P1[0] - P0[0])
            n = 5
            for i in range(n):
                s = (i / n + t * 0.35) % 1.0
                u = 1 - (1 - s) ** 1.6  # perspective-ish spacing
                x, y = lerp(P0[0], P1[0], u), lerp(P0[1], P1[1], u)
                size = lerp(150, 38, u) * (sx / (self.fw / iw)) ** 0.35
                fa = min(1, s / 0.12, (1 - s) / 0.15) * show
                poly = [(px * S, py * S) for px, py in arrow_poly(x, y, ang, size)]
                d.polygon(poly, fill=GREEN + (int(235 * fa),), outline=WHITE + (int(255 * fa),),
                          width=int(4 * S))
            # pulsing door frame
            (x0, y0), (x1, y1) = m(self.door[:2]), m(self.door[2:])
            pulse = 0.5 + 0.5 * math.sin(t * 5)
            pad = 6 + 6 * pulse
            for k, wdt in ((pad + 10, 14), (pad, 7)):
                d.rounded_rectangle(((x0 - k) * S, (y0 - k) * S, (x1 + k) * S, (y1 + k) * S),
                                    8 * S, outline=GREEN + (int(a * (0.35 if wdt > 10 else 1)),),
                                    width=wdt * S)
            # label pill above the door with a downward pointer
            f = font(44 * S)
            tw = d.textlength(self.label, font=f)
            lx = (x0 + x1) / 2 * S
            bob = math.sin(t * 4) * 8 * S
            ly = (y0 - 150) * S + bob
            bx0, bx1 = lx - tw / 2 - 30 * S, lx + tw / 2 + 30 * S
            bx0, bx1 = max(bx0, (self.fx + 10) * S) , max(bx1, (self.fx + 10) * S + (bx1 - bx0))
            d.rounded_rectangle((bx0, ly, bx1, ly + 76 * S), 38 * S, fill=GREEN + (a,),
                                outline=WHITE + (a,), width=3 * S)
            d.text(((bx0 + bx1) / 2 - tw / 2, ly + 12 * S), self.label, font=f, fill=WHITE + (a,))
            d.polygon([(lx - 22 * S, ly + 76 * S), (lx + 22 * S, ly + 76 * S),
                       (lx, ly + 110 * S)], fill=GREEN + (a,), outline=WHITE + (a,))
        im.alpha_composite(ov.resize((W, H), Image.LANCZOS))
        if cap:
            caption(im, self.label.title(), self.sub, ease((t - 0.3) / 0.6))
        return im


class Summary(Scene):
    def __init__(self, c1, c2, dur=4.5):
        self.c1, self.c2, self.dur = c1, c2, dur

    def frame(self, t):
        im = Image.new("RGBA", (W, H), DARK + (255,))
        d = ImageDraw.Draw(im)
        a = ease(t / 0.8)
        f1 = font(64)
        title = "2 Emergency Exits"
        d.text(((W - d.textlength(title, font=f1)) / 2, 70), title, font=f1, fill=WHITE + (int(255 * a),))
        sub = "Follow the green arrows to the nearest exit"
        f2 = font(36, False)
        d.text(((W - d.textlength(sub, font=f2)) / 2, 160), sub, font=f2, fill=(190, 205, 220, int(255 * a)))
        for i, sc in enumerate((self.c1, self.c2)):
            th = sc.frame(sc.dur * 0.82, cap=False).crop((sc.fx, 0, sc.fx + sc.fw, H)).resize((540, 720))
            x = W // 2 - 600 + i * 660
            y = 260 + int((1 - ease((t - 0.2 * i) / 0.8)) * 60)
            th.putalpha(int(255 * ease((t - 0.2 * i) / 0.8)))
            im.alpha_composite(th, (x, y))
        return im


# ---------------------------------------------------------------- render
def render(scenes, out):
    starts, t = [], 0.0
    for i, s in enumerate(scenes):
        starts.append(t)
        t += s.dur - (XF if i < len(scenes) - 1 else 0)
    total = t
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                           "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    nf = int(round(total * FPS))
    for f in range(nf):
        T = f / FPS
        active = [(i, T - st) for i, (s, st) in enumerate(zip(scenes, starts)) if 0 <= T - st < s.dur]
        i, lt = active[-1]
        img = scenes[i].frame(lt)
        if len(active) > 1 and lt < XF:  # crossfade from previous scene
            j, pt = active[-2]
            img = Image.blend(scenes[j].frame(pt), img, ease(lt / XF))
        # fade in / out of whole clip
        k = min(1, T / 0.5, (total - T) / 0.8)
        if k < 1:
            img = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), img, max(0, k))
        ff.stdin.write(img.convert("RGB").tobytes())
        if f % 60 == 0:
            print(f"{f}/{nf}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("wrote", out, f"{total:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--satellite", help="satellite image of the site")
    ap.add_argument("--target", default=None, help="building pixel x,y in satellite image")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "evacuation_clip.mp4"))
    args = ap.parse_args()

    c1 = CorridorExit(A("corridor1.jpg"), door=(482, 614, 554, 690), path_start=(470, 1180),
                      label="EMERGENCY EXIT 1", sub="End of corridor 1 - follow the arrows")
    c2 = CorridorExit(A("corridor2.jpg"), door=(440, 600, 517, 680), path_start=(470, 1180),
                      label="EMERGENCY EXIT 2", sub="End of corridor 2 - follow the arrows")
    scenes = []
    if args.satellite:
        sat = Image.open(args.satellite)
        tgt = tuple(map(float, args.target.split(","))) if args.target else (sat.width / 2, sat.height / 2)
        scenes.append(SatelliteZoom(args.satellite, tgt))
    else:
        scenes.append(TitleCard("Emergency Evacuation Route", "Main Hall & Emergency Exits"))
    scenes += [
        HallPan(A("hall_entrance1.jpg"), "Main Hall", "View from Entrance 1", drift=-1),
        HallPan(A("hall_entrance2.jpg"), "Main Hall", "View from Entrance 2", drift=+1),
        c1, c2, Summary(c1, c2),
    ]
    render(scenes, args.out)
