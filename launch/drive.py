"""Original high-energy track for the 30 s film: 128 BPM, F minor.

Everything is synthesized here (no samples), so the track is ours outright.
16 bars of 1.875 s = 30.0 s. Writes launch/out/drive.wav and
launch/out/drive.json (bar times the Blender film syncs to).

  1-2   intro: filtered supersaw chords opening up, arp, rising noise
  3-4   build: four-on-the-floor kick, snare roll speeding up, riser;
        the last beat of bar 4 drops out
  5-12  drop: kick, claps, offbeat hats, pumping bass, sidechained chords, arp
  13-14 lift: kick out, chords + arp + riser, roll into
  15    final drop
  16    last hit and tail

Saws are additive (band-limited) and every filter runs continuously, so
nothing aliases or clicks. Mastered through an LA-2A-style leveler and a
lookahead limiter to a -1.5 dBTP ceiling.
"""
import json
import os

import numpy as np
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

SR = 44100
BPM = 128
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
N = int(SR * BARS * BAR)
rng = np.random.default_rng(128)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)


def t_of(bar, beat=0.0):
    return (bar - 1) * BAR + beat * BEAT


def idx(t):
    return int(round(t * SR))


def place(track, sig, t, gain=1.0):
    i = idx(t)
    if i >= len(track):
        return
    n = min(len(sig), len(track) - i)
    track[i:i + n] += sig[:n] * gain


def lp(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x)


def hp(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def svf_lowpass(x, cutoff, q=0.8):
    """State-variable lowpass with a per-sample cutoff (Hz array)."""
    y = np.empty_like(x)
    low = band = 0.0
    damp = 1 / q
    f = 2 * np.sin(np.pi * np.clip(cutoff, 20, SR / 6) / SR)
    for i in range(len(x)):
        low += f[i] * band
        high = x[i] - low - damp * band
        band += f[i] * high
        y[i] = low
    return y


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def saw(f, dur, harmonics_to=16000):
    """Band-limited saw by adding harmonics up to `harmonics_to` Hz."""
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    ph = rng.uniform(0, 2 * np.pi)
    for k in range(1, int(harmonics_to / f) + 1):
        out += np.sin(2 * np.pi * k * f * t + k * ph) / k
    return out * (2 / np.pi)


def supersaw(notes, dur, voices=5, detune_cents=14):
    out = np.zeros(int(dur * SR))
    for n in notes:
        for v in range(voices):
            c = detune_cents * (v - (voices - 1) / 2) / ((voices - 1) / 2)
            out += saw(midi(n) * 2 ** (c / 1200), dur, 9000)
    return out / (len(notes) * voices) * 2.2


def env_ad(n, attack, decay):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def reverb_ir(seconds=1.8, decay=0.45, seed=3):
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = r.standard_normal((n, 2)) * np.exp(-t / decay)[:, None]
    ir = np.stack([lp(ir[:, 0], 7000), lp(ir[:, 1], 7000)], axis=1)
    ir[: int(0.012 * SR)] = 0  # pre-delay
    return ir / np.sqrt(np.sum(ir ** 2))


IR = reverb_ir()


def verb(x, wet):
    return np.stack([fftconvolve(x, IR[:, c])[: len(x)] for c in range(2)], axis=1) * wet


# ---- sounds ----

def kick():
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.035)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.2)
    click = hp(rng.standard_normal(n), 3000) * np.exp(-t / 0.004) * 0.35
    k = np.tanh(1.6 * (body + click))
    return k / np.max(np.abs(k))


def clap():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    noise = bp(rng.standard_normal(n), 900, 5200)
    e = np.zeros(n)
    for off in (0, 0.009, 0.018):  # three hands
        e += np.where(t >= off, np.exp(-(t - off) / 0.012), 0)
    e += np.where(t >= 0.025, 0.5 * np.exp(-(t - 0.025) / 0.11), 0)
    c = noise * e
    return c / np.max(np.abs(c))


def hat(open_=False):
    n = int((0.22 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    h = hp(rng.standard_normal(n), 7500, 4) * np.exp(-t / (0.07 if open_ else 0.012))
    return h / np.max(np.abs(h))


def snare():
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.03)
    noise = bp(rng.standard_normal(n), 1500, 8000) * np.exp(-t / 0.06)
    s = 0.6 * tone + noise
    return s / np.max(np.abs(s))


def pluck(n_, dur=0.22):
    """Arp voice: a soft square (odd harmonics) with a fast filter decay."""
    f = midi(n_)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for k in range(1, int(8000 / f) + 1, 2):
        x += np.sin(2 * np.pi * k * f * t) / k * np.exp(-t * k * 9)
    return x * env_ad(n, 0.002, 0.11)


def bass(n_, dur):
    f = midi(n_)
    n = int(dur * SR)
    t = np.arange(n) / SR
    sub = np.sin(2 * np.pi * f * t)
    grit = lp(saw(f, dur, 2500), 700)
    e = env_ad(n, 0.004, dur * 0.6) * np.clip((dur - t) / 0.015, 0, 1)
    return (sub + 0.35 * grit) * e


def boom():
    n = int(2.4 * SR)
    t = np.arange(n) / SR
    f = 30 + 70 * np.exp(-t / 0.12)
    b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.8)
    crash = hp(rng.standard_normal(n), 4000) * np.exp(-t / 0.9) * 0.25
    return b + crash


def riser(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    cut = 300 + 9000 * (t / dur) ** 2
    sweep = svf_lowpass(noise, cut, 1.6) * (t / dur) ** 1.5
    tone = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2.5 * t / dur)) / SR) * (t / dur) ** 2 * 0.25
    return sweep * 0.5 + tone


# ---- arrangement ----
# i - VI - III - VII in F minor: Fm, Db, Ab, Eb.
CHORDS = [[53, 56, 60, 65], [49, 53, 56, 61], [48, 51, 56, 60], [51, 55, 58, 63]]
ROOTS = [29, 25, 32, 27]  # bass roots (F1, Db1, Ab1, Eb1)

kicks, claps, hats, bassl, chords, arp, fx, sn = (np.zeros(N) for _ in range(8))
beatmap = {"bpm": BPM, "beat": BEAT, "bar": BAR, "bars": BARS, "kicks": []}

K, C, HC, HO, SN = kick(), clap(), hat(), hat(True), snare()
DROP = set(range(5, 13)) | {15}

for bar in range(1, BARS + 1):
    ch = CHORDS[(bar - 1) % 4]
    root = ROOTS[(bar - 1) % 4]
    full = bar in DROP
    # kick: build + drops; beat 4 of bar 4 and bar 14 is silence before the drop
    if bar in (3, 4) or full or bar == 16:
        beats = [0] if bar == 16 else range(4)
        for b in beats:
            if bar == 4 and b == 3:
                continue
            place(kicks, K, t_of(bar, b))
            beatmap["kicks"].append(t_of(bar, b))
    if full:
        for b in (1, 3):
            place(claps, C, t_of(bar, b))
        for b in range(4):
            place(hats, HO, t_of(bar, b + 0.5), 0.55)
            if bar >= 9 or bar == 15:
                for s in (0.25, 0.75):
                    place(hats, HC, t_of(bar, b + s), 0.3)
        for b in range(4):  # pumping offbeat bass
            place(bassl, bass(root, BEAT * 0.45), t_of(bar, b + 0.5))
        place(bassl, bass(root, BEAT * 0.3), t_of(bar, 0), 0.8)
    if bar == 2 or bar in (3, 4, 13, 14):
        for b in range(4):
            place(hats, HC, t_of(bar, b + 0.5), 0.25)
    # chords: every bar but the last, one long stab per bar
    if bar <= 15:
        place(chords, supersaw(ch, BAR * 0.98), t_of(bar))
    # arp: 16ths over chord tones, from bar 1
    if bar <= 15:
        tones = ch + [ch[1] + 12, ch[2] + 12]
        for s in range(16):
            if bar <= 2 and s % 2:
                continue
            place(arp, pluck(tones[(s * 3) % len(tones)] + 12), t_of(bar, s / 4), 0.5)

# snare rolls into the drops: 8ths, then 16ths, then 32nds
for bar0 in (4, 14):
    for k in range(0, 8):
        place(sn, SN, t_of(bar0, k * 0.25), 0.15 + 0.03 * k)
    for k in range(0, 12):
        if bar0 == 4 and t_of(bar0, 2 + k / 8) >= t_of(4, 3):
            break
        place(sn, SN, t_of(bar0, 2 + k / 8), 0.4 + 0.04 * k)
place(fx, riser(2 * BAR - BEAT), t_of(3), 0.7)
place(fx, riser(2 * BAR - BEAT), t_of(13), 0.7)
place(fx, riser(BAR), t_of(1), 0.25)
for bar in (5, 15):
    place(fx, boom(), t_of(bar), 0.9)
place(fx, boom(), t_of(16), 1.0)

# ---- processing ----
t = np.arange(N) / SR
# Intro: chords and arp open from muffled to bright over bars 1-4; the lift
# (13-14) dips and reopens.
cut = np.full(N, 12000.0)
a, b_ = idx(t_of(1)), idx(t_of(5))
cut[a:b_] = 350 * (12000 / 350) ** (np.linspace(0, 1, b_ - a) ** 1.6)
a, b_ = idx(t_of(13)), idx(t_of(15))
cut[a:b_] = 1200 * (12000 / 1200) ** (np.linspace(0, 1, b_ - a) ** 2)
chords_f = svf_lowpass(chords, cut, 0.9)
arp_f = svf_lowpass(arp, np.minimum(cut * 1.3, 14000), 0.8)

# Sidechain: everything melodic ducks under each kick.
duck = np.ones(N)
for kt in beatmap["kicks"]:
    i = idx(kt)
    n = min(int(BEAT * SR), N - i)
    tt = np.arange(n) / SR
    duck[i:i + n] = np.minimum(duck[i:i + n], 1 - 0.75 * np.exp(-tt / 0.11))
duck = np.convolve(duck, np.ones(64) / 64, mode="same")

dry = (kicks * 0.95 + claps * 0.42 + hats * 0.2 + sn * 0.3 + bassl * 0.55 * duck
       + chords_f * 0.32 * duck + arp_f * 0.2 * duck + fx * 0.32)
stereo = np.stack([dry, dry], axis=1)
# Width: chords and arp a few ms apart left/right, plus reverb on the
# claps, arp and chords.
for sig, g, ms in ((chords_f * 0.32 * duck, 0.45, 11), (arp_f * 0.2 * duck, 0.5, 17)):
    d = np.roll(sig, int(ms / 1000 * SR))
    stereo[:, 0] += (sig - d) * g * 0.5
    stereo[:, 1] += (d - sig) * g * 0.5
stereo += verb(claps * 0.42 + arp_f * 0.2 + chords_f * 0.1 + sn * 0.2, 0.28)
stereo = hp(stereo.T, 28).T  # nothing below hearing

# Tail: let the last hit ring and fade out.
ti = idx(t_of(16) + 1.0)
stereo[ti:] *= (np.linspace(1, 0, N - ti) ** 2)[:, None]


def la2a(x, peak_reduction_db=-14.0, ratio=3.0, knee_db=10.0, attack=0.010,
         release_fast=0.06, release_slow=1.6, fast_share=0.55):
    """LA-2A-style optical leveler: ~10 ms attack, two-stage release, soft knee."""
    det = np.sqrt(np.mean(x ** 2, axis=1))
    a = np.exp(-1 / (attack * SR))
    rf = np.exp(-1 / (release_fast * SR))
    rs = np.exp(-1 / (release_slow * SR))
    ef = es = 0.0
    env = np.empty_like(det)
    for i in range(len(det)):
        v = det[i]
        ef = v + (ef - v) * (a if v > ef else rf)
        es = v + (es - v) * (a if v > es else rs)
        env[i] = fast_share * ef + (1 - fast_share) * es
    lvl = 20 * np.log10(np.maximum(env, 1e-6))
    over = lvl - peak_reduction_db
    gr = np.where(over <= -knee_db / 2, 0.0,
                  np.where(over >= knee_db / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + knee_db / 2) ** 2 / (2 * knee_db)))
    print(f"la-2a: max gain reduction {gr.max():.1f} dB")
    return x * (10 ** (-gr / 20))[:, None]


def limit(x, ceiling=0.9, lookahead=0.004, release=0.06):
    from scipy.ndimage import maximum_filter1d
    peak = np.max(np.abs(x), axis=1)
    la = int(lookahead * SR)
    env = maximum_filter1d(peak, size=2 * la + 1, origin=-la)
    target = np.minimum(1.0, ceiling / np.maximum(env, 1e-9))
    g = np.empty_like(target)
    rel = np.exp(-1 / (release * SR))
    cur = 1.0
    for i in range(len(target)):
        tg = target[i]
        cur = tg if tg < cur else tg + (cur - tg) * rel
        g[i] = cur
    g = np.convolve(g, np.ones(la) / la, mode="same")
    return x * np.minimum(g, target)[:, None]


stereo /= np.max(np.abs(stereo))
stereo = la2a(stereo)
stereo /= np.max(np.abs(stereo))
stereo = limit(stereo * 2.0, ceiling=0.9)
tp = max(np.max(np.abs(resample_poly(stereo[:, c], 4, 1))) for c in range(2))
stereo *= (10 ** (-1.5 / 20)) / tp

import wave

with wave.open(os.path.join(OUT, "drive.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((stereo * 32767).astype("<i2").tobytes())
beatmap["length"] = N / SR
with open(os.path.join(OUT, "drive.json"), "w") as f:
    json.dump(beatmap, f, indent=1)
print(f"drive.wav: {N / SR:.2f}s, {len(beatmap['kicks'])} kicks")
