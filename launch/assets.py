"""Renders the product shots the launch video uses, from demo data only.

  launch/out/assets/board_XX.png   the card wall, several live frames
  launch/out/assets/usage.png      the usage screen (fake ledger)
  launch/out/assets/*_win.png      the same, framed as macOS windows
"""
import json
import os
import random
import subprocess
import time
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", "assets")
BIN = os.path.join(ROOT, "bin", "agentboard")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
os.makedirs(OUT, exist_ok=True)


def fake_ledger(xdg):
    """30 days of plausible usage for a demo fleet."""
    rnd = random.Random(42)
    d = os.path.join(xdg, "agentboard", "usage")
    os.makedirs(os.path.join(d, "days"), exist_ok=True)
    projects = {"pay-api": 1.0, "storefront": 0.7, "evals": 0.55, "trainer": 0.4, "docs": 0.25, "monorepo": 0.2}
    models = [("claude", "claude-opus-5-5", 0.55), ("claude", "claude-sonnet-5", 0.2), ("codex", "gpt-6-astra", 0.25)]
    tools = {"claude|Bash": 9000, "claude|Read": 4200, "claude|Edit": 3100, "codex|exec": 2600, "claude|Grep": 1900, "codex|apply_patch": 1400, "claude|Write": 700, "claude|WebFetch": 400}
    today = date.today()
    for i in range(30):
        day = today - timedelta(days=i)
        weekend = day.weekday() >= 5
        scale = (0.35 if weekend else 1.0) * rnd.uniform(0.6, 1.25) * (1.25 if i < 7 else 1.0)
        buckets = {}
        for hour in range(24):
            # Work hours, a late-night bump.
            w = 1.0 if 10 <= hour <= 19 else (0.55 if 21 <= hour <= 23 else (0.15 if 8 <= hour <= 9 else 0.03))
            for proj, pw in projects.items():
                for prov, model, mw in models:
                    if rnd.random() > 0.55:
                        continue
                    active = 3600 * 0.9 * w * pw * mw * scale * rnd.uniform(0.3, 1.4)
                    if active < 30:
                        continue
                    toks = int(active * rnd.uniform(9000, 16000))
                    buckets[f"{hour:02d}|{prov}|{proj}|{model}"] = {
                        "tokens": {"in": toks // 200, "cache_read": int(toks * 0.93), "cache_write": toks // 30, "out": toks // 60},
                        "replies": int(active / 9), "prompts": max(1, int(active / 420)), "tools": int(active / 7), "active_s": active,
                    }
        sessions = {f"s{i}-{k}": "claude|pay-api" for k in range(int(12 * scale) + 3)}
        day_tools = {k: int(v / 30 * scale * rnd.uniform(0.7, 1.3)) for k, v in tools.items()}
        with open(os.path.join(d, "days", day.isoformat() + ".json"), "w") as f:
            json.dump({"date": day.isoformat(), "buckets": buckets, "tools": day_tools, "sessions": sessions}, f)
    now = date.today()
    with open(os.path.join(d, "state.json"), "w") as f:
        json.dump({"version": 1, "files": {}, "last": {}, "rate_limits": {
            "codex": {"provider": "codex", "used_percent": 18, "window_minutes": 43200,
                      "resets_at": f"{now + timedelta(days=12)}T16:35:00Z", "observed_at": f"{now}T12:00:00Z"}}}, f)
    with open(os.path.join(d, "claude-limits.json"), "w") as f:
        json.dump({
            "claude:5h": {"provider": "claude", "window": "5h", "used_percent": 42, "window_minutes": 300,
                          "resets_at": f"{now + timedelta(days=1)}T02:10:00Z", "observed_at": f"{now}T12:00:00Z"},
            "claude:7d": {"provider": "claude", "window": "7d", "used_percent": 61, "window_minutes": 10080,
                          "resets_at": f"{now + timedelta(days=4)}T08:50:00Z", "observed_at": f"{now}T12:00:00Z"},
        }, f)


def render(args, size, name, env_extra=None):
    cols, rows = size
    env = dict(os.environ, **(env_extra or {}))
    ansi = subprocess.run([BIN, "--render", f"{cols}x{rows}", "--images", "off", *args],
                          capture_output=True, env=env, check=True).stdout
    html = subprocess.run(["python3", os.path.join(HERE, "ansi2html.py")], input=ansi, capture_output=True, check=True).stdout
    hp = os.path.join(OUT, name + ".html")
    with open(hp, "wb") as f:
        f.write(html)
    w, h = cols * 8 + 24, rows * 17 + 24
    png = os.path.join(OUT, name + ".png")
    # Headless Chrome sometimes writes the screenshot and then lingers, so
    # wait for the file to settle and stop it ourselves.
    if os.path.exists(png):
        os.remove(png)
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                             f"--window-size={w},{h}", f"--screenshot={png}", "file://" + hp],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last, stable = -1, 0
    for _ in range(600):
        if proc.poll() is not None and os.path.exists(png):
            break
        size = os.path.getsize(png) if os.path.exists(png) else -1
        stable = stable + 1 if size > 0 and size == last else 0
        last = size
        if stable >= 5:
            break
        time.sleep(0.2)
    proc.kill()
    if not os.path.exists(png):
        raise RuntimeError("chrome produced no screenshot for " + name)
    os.remove(hp)
    return png


def window(src, name, title="agentboard"):
    """Frame a screenshot as a macOS window: rounded corners, title bar,
    traffic lights, soft shadow."""
    img = Image.open(src).convert("RGBA")
    s = 2  # device scale
    bar = 28 * s
    radius = 12 * s
    pad = 60 * s
    w, h = img.size[0], img.size[1] + bar
    win = Image.new("RGBA", (w, h), (12, 12, 16, 255))
    d = ImageDraw.Draw(win)
    d.rectangle([0, 0, w, bar], fill=(28, 28, 34, 255))
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        cx = 20 * s + i * 20 * s
        d.ellipse([cx - 6 * s, bar / 2 - 6 * s, cx + 6 * s, bar / 2 + 6 * s], fill=c + (255,))
    win.paste(img, (0, bar))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    win.putalpha(mask)
    # Hairline border.
    ImageDraw.Draw(win).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(255, 255, 255, 38), width=s)

    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + 14 * s, pad + w, pad + h + 14 * s], radius=radius, fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26 * s))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(win, (pad, pad))
    out = os.path.join(OUT, name + "_win.png")
    canvas.save(out)
    return out


if __name__ == "__main__":
    xdg = os.path.join(HERE, "out", "xdg")
    fake_ledger(xdg)
    # An empty HOME: the ledger must never see real agent logs, so nothing
    # from this machine can end up in the video.
    fake_home = os.path.join(HERE, "out", "home")
    os.makedirs(fake_home, exist_ok=True)
    board_env = {"XDG_DATA_HOME": xdg, "HOME": fake_home, "AGENTBOARD_HOSTNAME": "macbook-pro"}
    for i in range(6):
        env = dict(board_env, AGENTBOARD_DEMO_TICKS=str(400 + i * 2), AGENTBOARD_FRAME=str(i * 3))
        p = render(["--demo"], (172, 50), f"board_{i:02d}", env)
        window(p, f"board_{i:02d}")
    p = render(["--demo", "--view", "usage"], (172, 50), "usage", board_env)
    window(p, "usage")
    print("assets:", sorted(os.listdir(OUT)))
