"""Draws the Hall Monitor menu (as it looks in the macOS menu bar) with demo
data, at 2x, for the launch video. Layout, sizes and colors follow the real
NSMenu: dark material, section headers, icon + title + gray subtitle rows,
capsule badges, submenu chevrons, right-aligned shortcuts."""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "assets")
ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "icons")  # app icons, png

S = 2
W = 350 * S
SF = "/System/Library/Fonts/SFNS.ttf"


def font(size, weight=400):
    f = ImageFont.truetype(SF, size * S)
    # Axes: Width, Optical Size, GRAD, Weight.
    f.set_variation_by_axes([100, min(96, max(17, size)), 400, weight])
    return f


def icon(path, size):
    im = Image.open(path).convert("RGBA")
    # Trim the macOS icon margin.
    bbox = im.getchannel("A").point(lambda a: 255 if a > 240 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    return im.resize((size, size), Image.LANCZOS)


claude = os.path.join(OUT, "icon_claude.png")
codex = os.path.join(OUT, "icon_codex.png")
for src, dst in [(os.path.join(ICONS, "claude-app.png"), claude), (os.path.join(ICONS, "codex-app.png"), codex)]:
    Image.open(src).save(dst)

rows = [
    ("header", "Needs You"),
    ("agent", codex, "Flaky e2e on checkout", "approve: exec · pnpm playwright test", "needs you"),
    ("sep",),
    ("header", "Working"),
    ("agent", claude, "Migrate billing to Stripe v3", "Bash · run integration tests", "4m"),
    ("agent", claude, "Fine-tune eval harness", "Read · results.jsonl", "1m"),
    ("agent", codex, "Bump Go to 1.26", "exec · go test ./...", "59s"),
    ("sep",),
    ("header", "Today"),
    ("stat", "clock", "21.6h of agent time", "934.6M tokens · 212 prompts · 12k tool calls"),
    ("limit", claude, "Claude 5-hour limit", "Resets Wed 07:40", 42),
    ("limit", claude, "Claude weekly limit", "Resets Sat 14:20", 61),
    ("sep",),
    ("action", "Open Board", "⌘O"),
    ("action", "Usage Dashboard", "⌘U"),
    ("sep",),
    ("action", "Settings…", "⌘,"),
    ("action", "Quit Hall Monitor", "⌘Q"),
]

H_ROW = {"header": 22, "agent": 40, "sep": 11, "stat": 40, "limit": 40, "action": 24}
H = (sum(H_ROW[r[0]] for r in rows) + 12) * S

pad = 50 * S
canvas = Image.new("RGBA", (W + 2 * pad, H + 2 * pad), (0, 0, 0, 0))
# Shadow.
sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle([pad, pad + 10 * S, pad + W, pad + H + 10 * S], 12 * S, fill=(0, 0, 0, 150))
canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(24 * S)))

menu = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(menu)
d.rounded_rectangle([0, 0, W - 1, H - 1], 11 * S, fill=(40, 42, 50, 236), outline=(255, 255, 255, 40), width=S)

title_f, sub_f, head_f, badge_f = font(13, 500), font(11, 400), font(11, 600), font(10.5, 500)
fg, sec, ter = (238, 238, 240, 255), (165, 168, 178, 255), (120, 124, 134, 255)
y = 6 * S
for r in rows:
    kind = r[0]
    h = H_ROW[kind] * S
    if kind == "header":
        d.text((14 * S, y + 5 * S), r[1], font=head_f, fill=ter)
    elif kind == "sep":
        d.line([14 * S, y + h // 2, W - 14 * S, y + h // 2], fill=(255, 255, 255, 30), width=S)
    elif kind in ("agent", "limit", "stat"):
        x = 14 * S
        if kind == "stat":
            cx, cy, r0 = x + 11 * S, y + h // 2, 7 * S
            d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], outline=sec, width=int(1.6 * S))
            d.line([cx, cy, cx, cy - 4 * S], fill=sec, width=int(1.6 * S))
            d.line([cx, cy, cx + 3 * S, cy], fill=sec, width=int(1.6 * S))
        elif kind == "limit":
            pct = r[4]
            cx, cy, r0 = x + 11 * S, y + h // 2, 7 * S
            d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], outline=(90, 94, 104, 255), width=int(2.4 * S))
            col = (239, 68, 68) if pct >= 80 else (249, 158, 11) if pct >= 50 else (52, 199, 89)
            d.arc([cx - r0, cy - r0, cx + r0, cy + r0], -90, -90 + 360 * pct / 100, fill=col + (255,), width=int(2.4 * S))
        else:
            ic = icon(r[1], 22 * S)
            menu.alpha_composite(ic, (x, y + (h - 22 * S) // 2))
        tx = x + 32 * S
        title, sub = (r[2], r[3])
        d.text((tx, y + 4 * S), title, font=title_f, fill=fg)
        limit = W - tx - (110 * S if kind == "agent" and r[4] == "needs you" else 70 * S if kind != "stat" else 14 * S)
        while d.textlength(sub, font=sub_f) > limit and len(sub) > 4:
            sub = sub[:-2].rstrip() + "…"
            sub = sub.replace("……", "…")
        d.text((tx, y + 21 * S), sub, font=sub_f, fill=sec)
        badge = r[4] if kind == "agent" else (f"{r[4]}%" if kind == "limit" else None)
        right = W - 14 * S
        if kind == "agent":
            # Submenu chevron.
            cx, cy = right - 3 * S, y + h // 2
            d.line([cx - 3 * S, cy - 4 * S, cx + 1 * S, cy, cx - 3 * S, cy + 4 * S], fill=sec, width=int(1.6 * S))
            right -= 14 * S
        if badge:
            bw = d.textlength(badge, font=badge_f) + 12 * S
            bx0, by0 = right - bw, y + h // 2 - 9 * S
            color = (255, 159, 10, 70) if badge == "needs you" else (255, 255, 255, 34)
            d.rounded_rectangle([bx0, by0, right, by0 + 18 * S], 9 * S, fill=color)
            d.text((bx0 + 6 * S, by0 + 2.5 * S), badge, font=badge_f, fill=(255, 190, 90, 255) if badge == "needs you" else fg)
    elif kind == "action":
        d.text((14 * S + 24 * S, y + 4 * S), r[1], font=title_f, fill=fg)
        kw = d.textlength(r[2], font=title_f)
        d.text((W - 14 * S - kw, y + 4 * S), r[2], font=title_f, fill=ter)
    y += h

canvas.alpha_composite(menu, (pad, pad))
canvas.save(os.path.join(OUT, "menu.png"))
print("menu.png", canvas.size)
