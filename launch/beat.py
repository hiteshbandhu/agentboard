"""Original hip-hop beat for the launch video, 100 BPM, A minor.

Everything is synthesized here (no samples), so the track is ours outright.
Writes launch/out/beat.wav and launch/out/beatmap.json (bar/beat times the
Blender scene syncs to).

Structure (bars of 2.4 s):
  1-2   intro: filtered Rhodes + vinyl, hats come in on bar 2
  3-4   build: kick + hats, no snare, filter opening, riser; last beat of
        bar 4 drops out to silence
  5-12  drop: full beat
  13-14 break: drums thin out, chords + 808
  15-16 outro: full beat, final hit and tail
"""
import json
import os

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 44100
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
TAIL = 2.5
N = int(SR * (BARS * BAR + TAIL))
rng = np.random.default_rng(7)

out_dir = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(out_dir, exist_ok=True)


def t_of(bar, beat=0.0):
    """Time of a beat within a bar (both 1-based bar, 0-based beat)."""
    return (bar - 1) * BAR + beat * BEAT


def swing(beat16):
    """16th-note position with a lazy hip-hop swing on the off-16ths."""
    base = beat16 * BEAT / 4
    if beat16 % 2 == 1:
        base += 0.10 * BEAT / 4 * 2
    return base


def env_exp(n, decay):
    t = np.arange(n) / SR
    return np.exp(-t / decay)


def lp(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)


def hp(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def place(track, sig, t, gain=1.0):
    i = int(t * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sig))
    track[i:j] += gain * sig[: j - i]


# ---- instruments ----

def kick():
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    f = 42 + 110 * np.exp(-t / 0.045)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * env_exp(n, 0.28)
    click = hp(rng.standard_normal(n), 3000) * env_exp(n, 0.004) * 0.35
    k = np.tanh(2.2 * (body + click))
    return k / np.max(np.abs(k))


def snare():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 185 * t) * env_exp(n, 0.06) * 0.6
    noise = bp(rng.standard_normal(n), 1200, 9000) * env_exp(n, 0.13)
    # Clap: a few quick bursts before the body.
    clap = np.zeros(n)
    for k, d in enumerate([0.0, 0.011, 0.022]):
        burst = bp(rng.standard_normal(int(0.02 * SR)), 900, 5000) * env_exp(int(0.02 * SR), 0.006)
        i = int(d * SR)
        clap[i:i + len(burst)] += burst * (0.8 - 0.15 * k)
    s = tone + noise * 0.8 + clap * 0.9
    return s / np.max(np.abs(s))


def hat(open_=False):
    n = int((0.28 if open_ else 0.05) * SR)
    x = hp(rng.standard_normal(n), 7500, order=4)
    x *= env_exp(n, 0.09 if open_ else 0.012)
    return x / np.max(np.abs(x))


def rhodes(freqs, dur, bright=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.12):
            ff = f * (1 + det / 100)
            tone = np.sin(2 * np.pi * ff * t + 0.9 * np.sin(2 * np.pi * ff * t) * np.exp(-t / 0.25) * bright)
            tone += 0.25 * np.sin(2 * np.pi * 2 * ff * t) * np.exp(-t / 0.4)
            out += tone
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.2 * t)
    amp = np.minimum(1, t / 0.008) * np.exp(-t / 2.2)
    rel = np.ones(n)
    r = int(0.08 * SR)
    rel[-r:] = np.linspace(1, 0, r)
    return out * trem * amp * rel / len(freqs)


def sub(f, dur, glide_from=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if glide_from:
        fr = f + (glide_from - f) * np.exp(-t / 0.06)
    else:
        fr = np.full(n, f)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR)
    s = np.tanh(1.6 * s)
    amp = np.minimum(1, t / 0.005) * np.exp(-t / 1.4)
    r = int(0.05 * SR)
    amp[-r:] *= np.linspace(1, 0, r)
    return s * amp


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


# A minor: Am9 – Fmaj9 – Dm9 – E7(#9), one chord per bar.
CHORDS = [
    [57, 60, 64, 67, 71],  # Am9
    [53, 57, 60, 64, 67],  # Fmaj9
    [50, 53, 57, 60, 64],  # Dm9
    [52, 56, 59, 62, 67],  # E7#9
]
ROOTS = [33, 29, 26, 28]  # A1 F1 D1 E1

drums = np.zeros(N)
kicks = np.zeros(N)
keys = np.zeros(N)
bass = np.zeros(N)
fx = np.zeros(N)

K, S, HC, HO = kick(), snare(), hat(), hat(True)

beatmap = {"bpm": BPM, "beat": BEAT, "bar": BAR, "bars": BARS, "kicks": [], "snares": [], "sections": {}}

kick_pattern = [0, 1.75, 2.5]          # boom … bap-bap
kick_pattern_b = [0, 0.75, 2.5, 3.25]   # variation every 4th bar

for bar in range(1, BARS + 1):
    chord = CHORDS[(bar - 1) % 4]
    root = ROOTS[(bar - 1) % 4]
    stop = bar == 4  # last beat of the build drops out

    # Keys every bar, with a pickup stab on the "and" of 4.
    keys_dur = BAR - (BEAT if stop else 0.0)
    place(keys, rhodes([midi(n) for n in chord], keys_dur), t_of(bar))
    if bar not in (4, 16):
        place(keys, rhodes([midi(n + 12) for n in chord[2:]], 0.4), t_of(bar, 3.5), 0.35)

    drums_on = 3 <= bar <= 16
    full = bar >= 5 and bar not in (13, 14)

    if drums_on:
        pat = kick_pattern_b if bar % 4 == 0 else kick_pattern
        for b in pat:
            if stop and b >= 3:
                continue
            if bar in (13, 14) and b != 0:
                continue
            place(kicks, K, t_of(bar, b), 1.0)
            beatmap["kicks"].append(round(t_of(bar, b), 4))
    if full or bar in (13, 14):
        for b in (1, 3):
            place(drums, S, t_of(bar, b), 0.85 if bar not in (13, 14) else 0.5)
            beatmap["snares"].append(round(t_of(bar, b), 4))

    # Hats: from bar 2, swung 16ths with accents, rolls at phrase ends.
    if bar >= 2 and not (bar in (13,)):
        for s16 in range(16):
            if stop and s16 >= 12:
                continue
            vel = 0.55 if s16 % 4 == 0 else (0.35 if s16 % 2 == 0 else 0.22)
            if bar == 2 and s16 % 2 == 1:
                continue
            place(drums, HC, t_of(bar) + swing(s16), vel * 0.5)
        if bar in (8, 12, 15):
            for k in range(6):  # 32nd-note roll into the next bar
                place(drums, HC, t_of(bar, 3.5) + k * BEAT / 12, 0.18 + 0.05 * k)
        if full:
            place(drums, HO, t_of(bar, 3.5), 0.28)

    # 808 / sub on the drop, gliding between roots.
    if bar >= 5:
        prev = ROOTS[(bar - 2) % 4]
        place(bass, sub(midi(root), 1.6, glide_from=midi(prev) if bar % 2 == 0 else None), t_of(bar), 0.9)
        place(bass, sub(midi(root + 7), 0.5), t_of(bar, 2.5), 0.55)
        place(bass, sub(midi(root), 0.9), t_of(bar, 3.25), 0.6)

# Riser over bar 4 into the drop.
rise_n = int(BAR * SR)
tt = np.arange(rise_n) / SR
noise = rng.standard_normal(rise_n)
riser = np.zeros(rise_n)
chunk = 1024
for i in range(0, rise_n, chunk):
    frac = i / rise_n
    lo = 300 + 6000 * frac ** 2
    seg = bp(noise[i:i + chunk + 256], lo, min(lo * 2.2, 18000))[:chunk]
    riser[i:i + len(seg)] = seg[: rise_n - i]
riser *= (tt / BAR) ** 2 * 0.5
riser[int((BAR - BEAT) * SR):] *= np.linspace(1, 0, rise_n - int((BAR - BEAT) * SR)) ** 3
place(fx, riser, t_of(4))

# Impact on the drop and the final hit: sub boom + noise burst.
def impact():
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(35 + 60 * np.exp(-t / 0.08)) / SR) * env_exp(n, 0.9)
    crash = hp(rng.standard_normal(n), 3000) * env_exp(n, 0.5) * 0.25
    return boom + crash

place(fx, impact(), t_of(5), 0.9)
place(fx, impact(), t_of(15), 0.6)
place(fx, impact(), t_of(17), 0.8)
place(kicks, K, t_of(17), 1.0)
beatmap["kicks"].append(round(t_of(17), 4))

# Vinyl crackle under everything.
crackle = np.zeros(N)
idx = rng.choice(N, size=int(N / SR * 60), replace=False)
crackle[idx] = rng.uniform(-1, 1, len(idx))
crackle = hp(crackle, 2000) * 0.25 + lp(rng.standard_normal(N), 800) * 0.004

# Intro filter: keys open up from muffled to full across bars 1–4.
t_all = np.arange(N) / SR
cut_end = t_of(5)
keys_f = np.zeros(N)
seg = int(0.05 * SR)
for i in range(0, N, seg):
    t0 = i / SR
    hz = 600 + (9000 - 600) * min(1, max(0, t0 / cut_end)) ** 2 if t0 < cut_end else 12000
    keys_f[i:i + seg] = lp(keys[max(0, i - 2048):i + seg], hz)[-min(seg, N - i):]

# Sidechain: duck keys and bass under each kick.
duck = np.ones(N)
for kt in beatmap["kicks"]:
    i = int(kt * SR)
    n = int(0.22 * SR)
    j = min(N, i + n)
    duck[i:j] = np.minimum(duck[i:j], 1 - 0.55 * np.exp(-np.arange(j - i) / SR / 0.07))

# Short room reverb on snares and keys.
ir_n = int(1.2 * SR)
ir = rng.standard_normal(ir_n) * env_exp(ir_n, 0.35)
ir = lp(ir, 6000)
ir /= np.sum(np.abs(ir)) / 30
verb = fftconvolve(drums * 0.12 + keys_f * 0.08, ir)[:N]

mix = (
    kicks * 0.95
    + drums * 0.55
    + keys_f * duck * 0.42
    + bass * duck * 0.55
    + fx * 0.6
    + crackle * 0.5
    + verb
)
mix = np.tanh(1.3 * mix)  # glue
mix /= np.max(np.abs(mix)) / 0.89

# Fade the tail.
tail_i = int(t_of(17) * SR) + int(1.2 * SR)
mix[tail_i:] *= np.linspace(1, 0, N - tail_i) ** 2

stereo = np.stack([mix, mix], axis=1)
# A touch of width: delay keys a few ms in the right channel.
width = np.roll(keys_f * duck * 0.42, int(0.012 * SR))
stereo[:, 1] += (width - keys_f * duck * 0.42) * 0.35
stereo /= np.max(np.abs(stereo)) / 0.89

import wave
pcm = (stereo * 32767).astype("<i2")
with wave.open(os.path.join(out_dir, "beat.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

beatmap["sections"] = {
    "intro": [t_of(1), t_of(3)],
    "build": [t_of(3), t_of(5)],
    "drop": t_of(5),
    "board": [t_of(5), t_of(9)],
    "usage": [t_of(9), t_of(11)],
    "notch": [t_of(11), t_of(15)],
    "outro": [t_of(15), t_of(17)],
    "end": t_of(17),
    "length": N / SR,
}
with open(os.path.join(out_dir, "beatmap.json"), "w") as f:
    json.dump(beatmap, f, indent=1)
print(f"beat.wav: {N / SR:.1f}s, {len(beatmap['kicks'])} kicks, {len(beatmap['snares'])} snares")
