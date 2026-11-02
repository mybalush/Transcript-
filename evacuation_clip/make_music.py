"""Generates a calm, simple background track (royalty-free, synthesised here)
and mixes it into the clip.

Usage: python3 make_music.py [video.mp4]
"""
import os, subprocess, sys, wave
import numpy as np

SR = 44100
BPM = 84
BEAT = 60 / BPM
HERE = os.path.dirname(os.path.abspath(__file__))


def note(n):  # MIDI note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a, r, length):
    t = np.arange(length) / SR
    e = np.minimum(1, t / a) if a > 0 else np.ones(length)
    rel = int(r * SR)
    if rel and rel < length:
        e[-rel:] *= np.linspace(1, 0, rel) ** 2
    return e


def pad(freqs, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.12):  # slight detune = warm chorus
            ff = f * 2 ** (det / 12)
            out += np.sin(2 * np.pi * ff * t) + 0.25 * np.sin(2 * np.pi * 2 * ff * t)
    out *= env(n, 0.6, 1.4, n) / (len(freqs) * 3)
    return out


def pluck(f, dur=1.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.1 * np.sin(2 * np.pi * 3 * f * t)
    return tone * np.exp(-t * 3.2) * np.minimum(1, t / 0.005)


def bass(f, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env(n, 0.05, 0.6, n) * np.exp(-t * 0.4)


def reverb(x, mix=0.3):
    y = x.copy()
    for d, g in ((0.113, 0.45), (0.171, 0.38), (0.237, 0.32), (0.311, 0.25)):
        k = int(d * SR)
        buf = np.zeros_like(x)
        for i in range(1, 6):  # a few feedback repeats
            s = k * i
            if s >= len(x):
                break
            buf[s:] += x[:-s] * g ** i
        y += buf * mix
    return y


def render(total):
    n = int((total + 3) * SR)
    mix = np.zeros(n)
    # Am - F - C - G, one chord per bar (4 beats); final bar resolves on C
    prog = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]
    bar = 4 * BEAT
    nbars = int(np.ceil(total / bar))
    arp_pat = [0, 1, 2, 1, 2, 1, 0, 2]  # eighth notes across the chord, an octave up
    for b in range(nbars):
        root, ch = prog[b % 4] if b < nbars - 1 else (48, [55, 60, 64])
        start = int(b * bar * SR)
        last = b == nbars - 1
        p = pad([note(m) for m in ch], bar * (2.2 if last else 1.6))
        mix[start:start + len(p)] += 0.32 * p[: n - start]
        bs = bass(note(root - 12), bar * (2 if last else 1))
        mix[start:start + len(bs)] += 0.30 * bs[: n - start]
        if 1 <= b and not last:  # arpeggio enters after the first bar
            for i, idx in enumerate(arp_pat):
                s = start + int(i * BEAT / 2 * SR)
                pl = pluck(note(ch[idx] + 12))
                vel = 0.16 if i % 2 == 0 else 0.11
                mix[s:s + len(pl)] += vel * pl[: n - s]
        if last:
            pl = pluck(note(72), 3.0)
            mix[start:start + len(pl)] += 0.18 * pl[: n - start]
    mix = reverb(mix)[: int(total * SR)]
    # gentle fade in/out to match the video
    fi, fo = int(1.0 * SR), int(2.5 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo) ** 1.5
    mix /= np.max(np.abs(mix)) + 1e-9
    return (mix * 0.5 * 32767).astype(np.int16)  # about -6 dB peak: background level


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "evacuation_clip.mp4")
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", video]).decode().strip())
    wav = os.path.join(HERE, "assets", "music.wav")
    pcm = render(dur)
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    tmp = video + ".tmp.mp4"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a",
                           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest",
                           "-movflags", "+faststart", tmp])
    os.replace(tmp, video)
    print("music added:", video, f"{dur:.1f}s")
