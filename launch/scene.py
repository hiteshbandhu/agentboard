"""hallmonitor launch film: procedural motion design in Blender, synced to
launch/out/beat.wav (100 BPM → 18 frames per beat at 30 fps).

  Blender -b -P launch/scene.py -- --stills 300,420   # a few frames to check
  Blender -b -P launch/scene.py -- --anim             # the whole film
  Blender -b -P launch/scene.py -- --anim --preview   # half res, fast

Frames land in launch/out/frames/; mux.sh adds the audio.
"""
import json
import math
import os
import random
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "out", "assets")
FONTS = os.path.expanduser("~/Library/Fonts")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW = "--preview" in argv

FPS = 30
BEAT = 18
BAR = 72
beatmap = json.load(open(os.path.join(HERE, "out", "beatmap.json")))
KICKS = [round(t * FPS) for t in beatmap["kicks"]]
SNARES = [round(t * FPS) for t in beatmap["snares"]]
END = round(beatmap["sections"]["end"] * FPS)  # final hit
LAST = END + 60


def bar(n, beat=0.0):
    return round((n - 1) * BAR + beat * BEAT)


# ---------------------------------------------------------------- easing

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(f, f0, dur):
    return clamp((f - f0) / dur) if dur > 0 else (1.0 if f >= f0 else 0.0)


def out_expo(t):
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def in_expo(t):
    return 0 if t <= 0 else 2 ** (10 * t - 10)


def out_back(t, s=1.9):
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def out_cubic(t):
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def lerp3(a, b, t):
    return tuple(lerp(x, y, t) for x, y in zip(a, b))


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)


WHITE = srgb("#f4f4f6")
MUTED = srgb("#8d8d96")
GREEN = srgb("#4ade80")
TEAL = srgb("#2dd4bf")
LIME = srgb("#a3e635")
YELLOW = srgb("#facc15")
CLAY = srgb("#d97757")
BLUE = srgb("#7dd3fc")
AMBER = srgb("#fbbf24")
BG = srgb("#07070a")

# ---------------------------------------------------------------- scene

scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

scene.render.engine = "BLENDER_EEVEE"
scene.render.fps = FPS
scene.frame_start = 0
scene.frame_end = LAST
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 50 if PREVIEW else 100
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.6
scene.eevee.motion_blur_steps = 2 if PREVIEW else 6
scene.eevee.taa_render_samples = 16 if PREVIEW else 48
scene.render.film_transparent = False
try:
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
except Exception:
    pass
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.filepath = os.path.join(HERE, "out", "frames_preview" if PREVIEW else "frames", "")

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = BG
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

# Compositor: soft bloom on the bright bits.
try:
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    glare = ng.nodes.new("CompositorNodeGlare")
    out = ng.nodes.new("NodeGroupOutput")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Threshold"].default_value = 0.75
    glare.inputs["Strength"].default_value = 0.55
    glare.inputs["Quality"].default_value = "High"
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = ng
except Exception as e:
    print("compositor setup failed:", e)

col = scene.collection

# Camera.
cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 40
cam_data.clip_end = 200
cam = bpy.data.objects.new("Cam", cam_data)
col.objects.link(cam)
scene.camera = cam

# ---------------------------------------------------------------- builders

fonts = {}


def font(name):
    if name not in fonts:
        fonts[name] = bpy.data.fonts.load(os.path.join(FONTS, name))
    return fonts[name]


HEAD = "PPTelegraf-Ultrabold.otf"
BODY = "PPTelegraf-Regular.otf"
MONO = "JetBrainsMono-Bold.ttf"


def emit_mat(name, color, strength=1.0, image=None):
    """Unlit material with an animatable fade (returns the fade socket)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    nt.nodes.clear()
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    fade = nt.nodes.new("ShaderNodeValue")
    fade.outputs[0].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    if image:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Cubic"
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
    else:
        em.inputs["Color"].default_value = color
        mul.inputs[0].default_value = 1.0
    nt.links.new(fade.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], outn.inputs["Surface"])
    return m, fade.outputs[0], em


def plane(name, w, h, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new()
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    return o


images = {}


def image(fn):
    if fn not in images:
        img = bpy.data.images.load(os.path.join(A, fn))
        img.colorspace_settings.name = "sRGB"
        images[fn] = img
    return images[fn]


def panel(name, fn, width):
    img = image(fn)
    w, h = img.size
    m, fade, _ = emit_mat(name, None, image=img)
    o = plane(name, width, width * h / w, m)
    return o, fade


def text(name, body, size, color, fontname=HEAD, align="CENTER", strength=1.0, spacing=1.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font(fontname)
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.space_character = spacing
    m, fade, em = emit_mat(name, color, strength)
    cu.materials.append(m)
    o = bpy.data.objects.new(name, cu)
    col.objects.link(o)
    return o, fade


def rounded_bar(name, w, h, d, color, strength=1.0):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.data.name = name
    # Scale the mesh itself so the bevel stays round.
    for v in o.data.vertices:
        v.co.x *= w
        v.co.y *= h
        v.co.z *= d
    bev = o.modifiers.new("round", "BEVEL")
    bev.width = w * 0.49
    bev.segments = 10
    bev.limit_method = "NONE"
    bev.affect = "EDGES"
    m, fade, _ = emit_mat(name, color, strength)
    o.data.materials.append(m)
    return o, fade


# ---------------------------------------------------------------- animation

class Track:
    """Bakes a per-frame function into keyframes, and hides the object
    outside [f0, f1] so nothing leaks into other shots."""

    def __init__(self, obj, fade=None):
        self.obj, self.fade = obj, fade

    def bake(self, f0, f1, fn):
        o = self.obj
        o.hide_render = True
        o.keyframe_insert("hide_render", frame=0)
        if f0 > 0:
            o.keyframe_insert("hide_render", frame=f0 - 1)
        o.hide_render = False
        o.keyframe_insert("hide_render", frame=f0)
        if f1 < LAST:
            o.hide_render = True
            o.keyframe_insert("hide_render", frame=f1 + 1)
        for f in range(f0, f1 + 1):
            p = fn(f)
            if "loc" in p:
                o.location = p["loc"]
                o.keyframe_insert("location", frame=f)
            if "rot" in p:
                o.rotation_euler = [math.radians(a) for a in p["rot"]]
                o.keyframe_insert("rotation_euler", frame=f)
            if "scale" in p:
                s = p["scale"]
                o.scale = (s, s, s) if isinstance(s, (int, float)) else s
                o.keyframe_insert("scale", frame=f)
            if "alpha" in p and self.fade is not None:
                self.fade.default_value = clamp(p["alpha"])
                self.fade.keyframe_insert("default_value", frame=f)
        return self


def pop(f, f0, dur=12):
    """0→1 with overshoot, for things that land on a beat."""
    return out_back(prog(f, f0, dur)) if f >= f0 else 0.0


def appear(f, f0, dur=10):
    return out_expo(prog(f, f0, dur))


def vanish(f, f0, dur=8):
    return 1 - in_expo(prog(f, f0, dur))


# ---------------------------------------------------------------- background

# Drifting aurora: huge soft discs of color far behind everything.
def glow_mat(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    nt.nodes.clear()
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2, 2, 2)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.interpolation = "EASE"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    fade = nt.nodes.new("ShaderNodeValue")
    fade.outputs[0].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(tc.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mul.inputs[0])
    nt.links.new(fade.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], outn.inputs["Surface"])
    # Generated coords run 0..1; center them.
    mapping.inputs["Location"].default_value = (-1, -1, 0)
    return m, fade.outputs[0]


blobs = []
for i, (c, x, y, s) in enumerate([(TEAL, -9, 3, 26), (GREEN, 8, -4, 24), (CLAY, 2, 6, 22), (BLUE, -6, -6, 20)]):
    m, fade = glow_mat(f"glow{i}", c, 0.22)
    o = plane(f"glow{i}", s, s, m)
    o.location = (x, y, -30)
    blobs.append((o, fade, x, y, i))


def blob_level(f):
    """How much background color each section gets."""
    if f < bar(3):
        return 0.35 * appear(f, 0, 60)
    if f < bar(4, 3):
        return 0.5
    if f < bar(5):
        return 0.5 * vanish(f, bar(4, 3), 6)
    if f < bar(15):
        return 0.55 + 0.45 * vanish(f, bar(5), 40)
    return 0.8 * (1 - in_expo(prog(f, END + 10, 40)))


for o, fade, x, y, i in blobs:
    rnd = random.Random(i)
    ph, sp = rnd.uniform(0, 6.28), rnd.uniform(0.004, 0.008)

    def fn(f, x=x, y=y, ph=ph, sp=sp, i=i):
        lvl = blob_level(f)
        # Outro leans warm (clay), notch section leans cool.
        tint = 1.0
        if i == 2:
            tint = 1.4 if f >= bar(15) else 0.8
        return {"loc": (x + 4 * math.sin(f * sp + ph), y + 3 * math.cos(f * sp * 1.3 + ph), -30), "alpha": lvl * tint}

    Track(o, fade).bake(0, LAST, fn)

# Vignette: a soft black ring parented to the camera.
vm = bpy.data.materials.new("vignette")
vm.use_nodes = True
vm.surface_render_method = "BLENDED"
nt = vm.node_tree
nt.nodes.clear()
o_ = nt.nodes.new("ShaderNodeOutputMaterial")
tc = nt.nodes.new("ShaderNodeTexCoord")
mp = nt.nodes.new("ShaderNodeMapping")
mp.inputs["Location"].default_value = (-0.5, -0.5, 0)
mp.inputs["Scale"].default_value = (1.0, 1.78, 1)
gr = nt.nodes.new("ShaderNodeTexGradient")
gr.gradient_type = "SPHERICAL"
rp = nt.nodes.new("ShaderNodeValToRGB")
rp.color_ramp.elements[0].position = 0.25
rp.color_ramp.elements[0].color = (0, 0, 0, 0.75)
rp.color_ramp.elements[1].position = 0.75
rp.color_ramp.elements[1].color = (0, 0, 0, 0)
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0, 0, 0, 1)
mx = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
nt.links.new(gr.outputs["Fac"], rp.inputs["Fac"])
nt.links.new(rp.outputs["Alpha"], mx.inputs["Fac"])
nt.links.new(tr.outputs[0], mx.inputs[1])
nt.links.new(em.outputs[0], mx.inputs[2])
nt.links.new(mx.outputs[0], o_.inputs["Surface"])
vig = plane("vignette", 2.0, 2.0 * 9 / 16, vm)
vig.parent = cam
vig.location = (0, 0, -1.2)
vig.scale = (0.62, 0.62, 1)

# Full-screen flash for hits.
flash_m, flash_fade, _ = emit_mat("flash", WHITE, 1.0)
flash = plane("flash", 2, 2 * 9 / 16, flash_m)
flash.parent = cam
flash.location = (0, 0, -1.1)
flash.scale = (0.6, 0.6, 1)
HITS = [bar(5), bar(15), END]
Track(flash, flash_fade).bake(0, LAST, lambda f: {"alpha": max([0.0] + [(0.08 if h == HITS[0] else 0.05) * (1 - out_cubic(prog(f, h, 6))) for h in HITS if f >= h])})

# ---------------------------------------------------------------- camera

def shake(f, start, stop, amp=0.045):
    s = [0.0, 0.0]
    for k in KICKS:
        if start <= k <= f <= stop and f - k < 14:
            d = amp * math.exp(-(f - k) / 3.5)
            rnd = random.Random(k)
            s[0] += d * rnd.uniform(-1, 1)
            s[1] += d * rnd.uniform(-1, 1)
    return s


def camera(f):
    x, y, z, rx, ry = 0.0, 0.0, 10.0, 0.0, 0.0
    if f < bar(3):  # intro: slow push
        z = 10.6 - 0.8 * in_out_cubic(prog(f, 0, bar(3)))
    elif f < bar(5):  # chaos: drift through the windows
        t = prog(f, bar(3), bar(5) - bar(3))
        z = lerp(10.5, 8.2, in_out_cubic(t))
        ry = lerp(-4, 5, t)
        rx = lerp(2, -2, t)
    elif f < bar(6):  # drop: punch in
        z = lerp(8.6, 10.0, out_expo(prog(f, bar(5), 24)))
    elif f < bar(9):  # board: slow orbit
        t = prog(f, bar(6), bar(9) - bar(6))
        z = lerp(10.2, 9.3, in_out_cubic(t))
        ry = lerp(3, -3, in_out_cubic(t))
    elif f < bar(11):  # usage
        t = prog(f, bar(9), bar(11) - bar(9))
        z = lerp(10.4, 9.4, in_out_cubic(t))
        ry = lerp(-3, 2, in_out_cubic(t))
    elif f < bar(15):  # notch
        t = prog(f, bar(11), bar(15) - bar(11))
        z = lerp(10.0, 9.2, in_out_cubic(t))
        rx = lerp(-1, 1, in_out_cubic(t))
    else:  # outro
        z = lerp(9.0, 10.2, out_expo(prog(f, bar(15), 60))) - 0.4 * in_out_cubic(prog(f, END - 20, 80))
    sx, sy = shake(f, bar(5), END + 20)
    return {"loc": (x + sx, y + sy, z), "rot": (rx, ry, 0)}


Track(cam).bake(0, LAST, camera)

# ---------------------------------------------------------------- S1 intro

words1 = [("You", WHITE), ("run", WHITE), ("agents.", WHITE)]
words2 = [("Lots", GREEN), ("of", GREEN), ("them.", GREEN)]
line1_y, line2_y = 0.5, -0.75
gap = 0.28


def lay_words(words, size, y):
    objs = []
    for w, c in words:
        o, fade = text("w_" + w, w, size, c, align="LEFT")
        objs.append((o, fade))
    # Measure after creation.
    bpy.context.view_layer.update()
    widths = [o.dimensions.x for o, _ in objs]
    total = sum(widths) + gap * (len(objs) - 1)
    x = -total / 2
    xs = []
    for wdt in widths:
        xs.append(x)
        x += wdt + gap
    return objs, xs


objs1, xs1 = lay_words(words1, 1.0, line1_y)
ICON_ROOM = 0.4 + 0.5 + 0.6
xs1 = [x - ICON_ROOM / 2 for x in xs1]
objs2, xs2 = lay_words(words2, 1.0, line2_y)
OUT1 = bar(2, 3.25)

for i, ((o, fade), x) in enumerate(zip(objs1, xs1)):
    f0 = i * BEAT

    def fn(f, x=x, f0=f0, i=i):
        k = pop(f, f0, 12)
        # Line 1 lifts when line 2 arrives, then everything leaves.
        lift = 0.35 * out_expo(prog(f, bar(2), 14))
        gone = in_expo(prog(f, OUT1 + i * 1.5, 10))
        return {"loc": (x, line1_y + lift - 0.35 * (1 - k) + 0.6 * gone, 0),
                "scale": 0.7 + 0.3 * k, "alpha": appear(f, f0, 8) * (1 - gone)}

    Track(o, fade).bake(f0, bar(3), fn)

for i, ((o, fade), x) in enumerate(zip(objs2, xs2)):
    f0 = bar(2) + i * BEAT

    def fn(f, x=x, f0=f0, i=i):
        k = pop(f, f0, 12)
        gone = in_expo(prog(f, OUT1 + 3 + i * 1.5, 10))
        return {"loc": (x, line2_y + 0.35 - 0.35 * (1 - k) - 0.6 * gone, 0),
                "scale": 0.7 + 0.3 * k, "alpha": appear(f, f0, 8) * (1 - gone)}

    Track(o, fade).bake(f0, bar(3), fn)

# The two tools, landing on the last beat of bar 1.
for i, fn_ in enumerate(["icon_claude.png", "icon_codex.png"]):
    o, fade = panel("intro_icon%d" % i, fn_, 0.5)
    f0 = bar(1, 3) + i * 4
    x = xs1[-1] + objs1[-1][0].dimensions.x + 0.4 + i * 0.6

    def fn(f, f0=f0, x=x):
        k = pop(f, f0, 12)
        gone = in_expo(prog(f, OUT1, 10))
        return {"loc": (x, line1_y + 0.35 * out_expo(prog(f, bar(2), 14)) + 0.05, 0.01),
                "scale": max(0.001, k) * (1 - gone), "rot": (0, 0, lerp(-20, 0, k)), "alpha": 1 - gone}

    Track(o, fade).bake(f0, bar(3), fn)

# ---------------------------------------------------------------- S2 chaos

rnd = random.Random(3)
chaos_files = ["board_00_win.png", "usage_win.png", "board_03_win.png", "board_01_win.png", "board_04_win.png",
               "board_02_win.png", "usage_win.png", "board_05_win.png", "board_00_win.png", "board_03_win.png",
               "board_01_win.png", "usage_win.png"]
spawn = sorted([k for k in KICKS if bar(3) <= k < bar(4, 3)] + [bar(3, b) for b in (0.5, 1.25, 2.0, 3.0, 3.5)] +
               [bar(4, b) for b in (0.25, 1.5, 2.0)])[:len(chaos_files)]
slots = [(-3.6, 1.6), (3.4, 1.9), (-0.2, -1.6), (4.4, -1.5), (-4.5, -1.2), (0.6, 2.3), (-2.0, 0.3), (2.3, 0.1),
         (-5.4, 2.4), (5.6, 0.6), (1.2, -2.6), (-1.4, 2.8)]
BLACKOUT = bar(4, 3)
for i, (fn_, f0) in enumerate(zip(chaos_files, spawn)):
    o, fade = panel(f"chaos{i}", fn_, rnd.uniform(3.0, 4.2))
    x, y = slots[i]
    z = rnd.uniform(-3.5, 0.8)
    r0 = (rnd.uniform(-10, 10), rnd.uniform(-18, 18), rnd.uniform(-5, 5))
    drift = (rnd.uniform(-0.004, 0.004), rnd.uniform(-0.003, 0.003))

    def fn(f, x=x, y=y, z=z, r0=r0, f0=f0, drift=drift, i=i):
        k = pop(f, f0, 14)
        # When the question lands, the windows sink back and dim.
        q = out_expo(prog(f, bar(4), 16))
        out = in_expo(prog(f, BLACKOUT, 7))
        dt = f - f0
        return {"loc": (x + drift[0] * dt, y + drift[1] * dt, z - 1.5 * q - 3 * (1 - k)),
                "rot": (r0[0], r0[1] + 0.03 * dt, r0[2]),
                "scale": 0.4 + 0.6 * k,
                "alpha": appear(f, f0, 6) * (1 - 0.55 * q) * (1 - out)}

    Track(o, fade).bake(f0, BLACKOUT + 8, fn)

q_lines = [("Which one", WHITE, 0.55), ("needs you?", AMBER, -0.6)]
for i, (s, c, y) in enumerate(q_lines):
    o, fade = text(f"q{i}", s, 1.05, c)
    f0 = bar(4) + i * 6

    def fn(f, f0=f0, y=y):
        k = pop(f, f0, 12)
        out = in_expo(prog(f, BLACKOUT, 7))
        return {"loc": (0, y - 0.3 * (1 - k), 1.0), "scale": 0.85 + 0.15 * k, "alpha": appear(f, f0, 6) * (1 - out)}

    Track(o, fade).bake(f0, BLACKOUT + 8, fn)

# ---------------------------------------------------------------- logo

BAR_W, BAR_GAP = 0.34, 0.16
BAR_H = [0.7, 1.2, 0.9]
BAR_C = [TEAL, GREEN, LIME]
logo_bars = []
for i, (h, c) in enumerate(zip(BAR_H, BAR_C)):
    o, fade = rounded_bar(f"logo_bar{i}", BAR_W, h, 0.18, c, 1.6)
    logo_bars.append((o, fade, h))
word, word_fade = text("wordmark", "hallmonitor", 1.25, WHITE, align="LEFT")
tag, tag_fade = text("tagline", "One board for every coding agent.", 0.36, MUTED, fontname=BODY)
bpy.context.view_layer.update()
WORD_W = word.dimensions.x
LOGO_W = 3 * BAR_W + 2 * BAR_GAP
LOCKUP_W = LOGO_W + 0.4 + WORD_W


def logo_frames(f):
    """Where the lockup is and how present it is: the drop, then the outro."""
    if f < bar(6):
        return 0.0, 0.0, bar(5), vanish(f, bar(5, 3.4), 8), 1.0  # (x, y, start, alive, scale)
    return 0.0, 0.35, bar(15), 1 - in_expo(prog(f, END + 30, 20)), 1.0 + 0.08 * pop(f, END, 10) * (1 - prog(f, END + 10, 20))


def logo_bar_fn(i, h):
    def fn(f):
        x0, y0, start, alive, sc = logo_frames(f)
        k = pop(f, start + i * 2, 14)
        left = -LOCKUP_W / 2 + BAR_W / 2 + i * (BAR_W + BAR_GAP)
        base = y0 - 0.6  # bars stand on a common baseline
        hk = max(0.001, k)
        return {"loc": ((x0 + left) * sc, (base + h * hk / 2) * sc, 0.2),
                "scale": (sc, sc * hk, sc), "alpha": alive}
    return fn


for i, (o, fade, h) in enumerate(logo_bars):
    Track(o, fade).bake(bar(5), bar(6) + 2, logo_bar_fn(i, h))
    # A second pass for the outro: duplicate so tracks stay independent.
    o2 = o.copy()
    o2.data = o.data.copy()
    col.objects.link(o2)
    o2.animation_data_clear()
    m2 = o.data.materials[0].copy()
    o2.data.materials[0] = m2
    fade2 = [n for n in m2.node_tree.nodes if n.type == "VALUE"][0].outputs[0]
    Track(o2, fade2).bake(bar(15), LAST, logo_bar_fn(i, h))


def word_fn(f):
    x0, y0, start, alive, sc = logo_frames(f)
    k = appear(f, start + 5, 14)
    return {"loc": ((x0 - LOCKUP_W / 2 + LOGO_W + 0.4 + 0.8 * (1 - k)) * sc, (y0 - 0.6 + 0.47) * sc, 0.2),
            "scale": sc, "alpha": k * alive}


Track(word, word_fade).bake(bar(5), bar(6) + 2, word_fn)
word2 = word.copy()
word2.data = word.data.copy()
word2.animation_data_clear()
col.objects.link(word2)
wm2 = word.data.materials[0].copy()
word2.data.materials[0] = wm2
Track(word2, [n for n in wm2.node_tree.nodes if n.type == "VALUE"][0].outputs[0]).bake(bar(15), LAST, word_fn)


def tag_fn(f):
    k = appear(f, bar(5, 1), 14)
    return {"loc": (0, -1.05 - 0.2 * (1 - k), 0.2), "alpha": k * vanish(f, bar(5, 3.4), 8)}


Track(tag, tag_fade).bake(bar(5, 1), bar(6), tag_fn)

# ---------------------------------------------------------------- lower thirds

def headline(name, lines, f0, f1, y=-1.12, size=0.38, x=0.0, align="CENTER"):
    """Stacked words that punch in on the beat and leave before the cut."""
    for j, (s, c) in enumerate(lines):
        o, fade = text(f"{name}{j}", s, size if j == 0 else size * 0.55, c, fontname=HEAD if j == 0 else BODY, align=align)
        yy = y - j * size * 0.95
        start = f0 + j * 5

        def fn(f, start=start, yy=yy):
            k = pop(f, start, 12)
            return {"loc": (x, yy - 0.18 * (1 - k), 3.0), "scale": 0.9 + 0.1 * k,
                    "alpha": appear(f, start, 6) * vanish(f, f1 - 6, 6)}

        Track(o, fade).bake(start, f1, fn)


# Dark gradient under lower thirds so text always reads.
def shade_mat():
    m = bpy.data.materials.new("shade")
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    nt.nodes.clear()
    o_ = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.elements[0].position = 0.55
    rp.color_ramp.elements[0].color = (1, 1, 1, 1)
    rp.color_ramp.elements[1].position = 1.0
    rp.color_ramp.elements[1].color = (0, 0, 0, 1)
    rp.color_ramp.interpolation = "EASE"
    fade = nt.nodes.new("ShaderNodeValue")
    fade.outputs[0].default_value = 1
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    mul2.inputs[1].default_value = 0.96
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = BG
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], rp.inputs["Fac"])
    nt.links.new(rp.outputs["Color"], mul.inputs[0])
    nt.links.new(fade.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    nt.links.new(mul2.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], o_.inputs["Surface"])
    return m, fade.outputs[0]


sm, sfade = shade_mat()
shade = plane("shade", 2.0, 0.5, sm)
shade.parent = cam
shade.location = (0, -0.31, -1.15)
Track(shade, sfade).bake(bar(6) - 4, bar(15), lambda f: {"alpha": appear(f, bar(6) - 4, 10) * vanish(f, bar(15) - 8, 8)})

# ---------------------------------------------------------------- S4 board

boards = [panel(f"board{i}", f"board_{i:02d}_win.png", 8.6) for i in range(6)]
BOARD_IN, BOARD_OUT = bar(5, 3.2), bar(9)


def board_pose(f):
    """Tilted hero, then a push into a card, then a wide swing."""
    t_in = out_expo(prog(f, BOARD_IN, 22))
    loc = lerp3((0, -7.5, -2), (0, 0.7, 0), t_in)
    rot = lerp3((-38, 0, 0), (-9, 11, 1.5), t_in)
    sc = 1.0
    # Bar 7: into the top-left card.
    k = in_out_cubic(prog(f, bar(7) - 6, 14))
    k_out = in_out_cubic(prog(f, bar(8) - 6, 14))
    zoom = k * (1 - k_out)
    loc = lerp3(loc, (2.1, -1.05, 2.4), zoom)
    rot = lerp3(rot, (-3, 4, 0), zoom)
    # Bar 8: swing the other way.
    w = in_out_cubic(prog(f, bar(8) - 6, 20))
    rot = lerp3(rot, (-7, -12, -1.5), w)
    loc = lerp3(loc, (0.2, 0.75, -0.3), w)
    # Exit: fly left as usage arrives.
    ex = in_expo(prog(f, BOARD_OUT - 8, 12))
    loc = lerp3(loc, (-14, 0.5, -2), ex)
    rot = lerp3(rot, (-9, 50, 0), ex)
    return loc, rot, sc


for i, (o, fade) in enumerate(boards):
    def fn(f, i=i):
        loc, rot, sc = board_pose(f)
        beat_i = max(0, (f - BOARD_IN) // BEAT)
        shown = (beat_i % len(boards)) == i
        return {"loc": loc, "rot": rot, "scale": sc, "alpha": 1.0 if shown else 0.0}

    Track(o, fade).bake(BOARD_IN, BOARD_OUT + 6, fn)

headline("h_board", [("Every agent. Live.", WHITE), ("Claude Code and Codex, on one screen.", MUTED)], bar(6), bar(7) - 2)
headline("h_card", [("See what it's doing.", WHITE)], bar(7), bar(8) - 2)
headline("h_hosts", [("Every machine.", WHITE), ("Laptop, dev box, GPU server — over plain SSH.", MUTED)], bar(8), bar(9) - 2)

# ---------------------------------------------------------------- S5 usage

usage, usage_fade = panel("usage", "usage_win.png", 8.6)
U_IN, U_OUT = bar(9) - 6, bar(11)


def usage_fn(f):
    t = out_expo(prog(f, U_IN, 22))
    loc = lerp3((14, 0.7, -2), (0, 0.7, 0), t)
    rot = lerp3((-9, -55, 0), (-8, -10, -1), t)
    # Bar 10: push toward the right column (limits).
    k = in_out_cubic(prog(f, bar(10) - 6, 16))
    loc = lerp3(loc, (-1.9, 0.9, 2.2), k)
    rot = lerp3(rot, (-4, -5, 0), k)
    ex = in_expo(prog(f, U_OUT - 8, 12))
    loc = lerp3(loc, (loc[0], 9.5, loc[2]), ex)
    rot = lerp3(rot, (35, rot[1], rot[2]), ex)
    return {"loc": loc, "rot": rot, "alpha": appear(f, U_IN, 6)}


Track(usage, usage_fade).bake(U_IN, U_OUT + 4, usage_fn)
headline("h_usage", [("Know your numbers.", WHITE), ("Agent-hours, tokens, cache hits — from logs already on disk.", MUTED)], bar(9), bar(10) - 2)
headline("h_limits", [("Never hit a wall blind.", WHITE), ("Claude and Codex plan limits, live.", MUTED)], bar(10), bar(11) - 2)

# ---------------------------------------------------------------- S6 notch + menu bar

# A MacBook's top edge: a desktop, a translucent menu bar, the notch.
N_IN, N_OUT = bar(11) - 4, bar(15)
NOTCH_W = 7.2  # the canvas width the snapshots were rendered at, in scene units
TOP = 2.05     # screen top edge in the notch shot
desk_w = 16.0
def desk_pose(f):
    t = out_expo(prog(f, N_IN, 24))
    y = lerp(-8, 0, t)
    ex = in_expo(prog(f, N_OUT - 6, 10))
    return y + 9 * ex


# A Mac desktop: a lit gradient with two soft color glows, so the black
# island reads the way it does on a real screen.
dm = bpy.data.materials.new("desk")
dm.use_nodes = True
dm.surface_render_method = "BLENDED"
nt = dm.node_tree
nt.nodes.clear()
o_ = nt.nodes.new("ShaderNodeOutputMaterial")
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
rp = nt.nodes.new("ShaderNodeValToRGB")
rp.color_ramp.elements[0].color = srgb("#0a0f1f")
rp.color_ramp.elements[1].color = srgb("#2b3c73")
rp.color_ramp.interpolation = "EASE"
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(tc.outputs["UV"], sep.inputs[0])
nt.links.new(sep.outputs["Y"], rp.inputs["Fac"])
nt.links.new(rp.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs[0], o_.inputs["Surface"])
desk = plane("desk", 22.0, 12.0, dm)
Track(desk).bake(N_IN, N_OUT + 4, lambda f: {"loc": (0, desk_pose(f) + TOP - 6.0, -0.5)})
for i, (c, x, y, sz) in enumerate([(srgb("#7c5cff"), -4.5, -1.5, 9), (srgb("#2dd4bf"), 5.0, -3.0, 10), (srgb("#d97757"), 1.0, 1.0, 7)]):
    gm, gfade = glow_mat(f"deskglow{i}", c, 0.5)
    g = plane(f"deskglow{i}", sz, sz, gm)
    Track(g, gfade).bake(N_IN, N_OUT + 4, lambda f, x=x, y=y, i=i: {
        "loc": (x + 0.6 * math.sin(f * 0.01 + i), desk_pose(f) + TOP - 3.0 + y + 0.4 * math.cos(f * 0.013 + i), -0.45),
        "alpha": 0.9})

mb_m, mb_fade, _ = emit_mat("menubar", srgb("#3a4466"), 1.0)
menubar = plane("menubar", desk_w, 0.34, mb_m)
clock, clock_fade = text("clock", "Tue 9:41 AM", 0.17, WHITE, fontname=BODY, align="RIGHT")
mini = []
for i, h in enumerate([0.1, 0.17, 0.13]):
    o, fade = rounded_bar(f"mini{i}", 0.045, h, 0.02, WHITE, 1.0)
    mini.append((o, fade, h))

notch_states = [("notch_compact.png", bar(11), bar(12)), ("notch_banner_needs.png", bar(12), bar(13)),
                ("notch_expanded.png", bar(13), bar(14)), ("notch_compact.png", bar(14), N_OUT)]


Track(menubar, mb_fade).bake(N_IN, N_OUT + 4, lambda f: {"loc": (0, desk_pose(f) + TOP - 0.17, -0.25), "alpha": 0.55})
Track(clock, clock_fade).bake(N_IN, N_OUT + 4, lambda f: {"loc": (4.4, desk_pose(f) + TOP - 0.17, -0.2), "alpha": 0.92})
for i, (o, fade, h) in enumerate(mini):
    Track(o, fade).bake(N_IN, N_OUT + 4, lambda f, i=i, h=h: {
        "loc": (2.55 + i * 0.075, desk_pose(f) + TOP - 0.24 + h / 2, -0.2), "alpha": 0.92})

for i, (fn_, f0, f1) in enumerate(notch_states):
    nw = NOTCH_W * (0.82 if "expanded" in fn_ else 1.0)
    o, fade = panel(f"notch{i}", fn_, nw)
    img = image(fn_)
    h = nw * img.size[1] / img.size[0]

    def fn(f, f0=f0, f1=f1, h=h, i=i):
        # Each state springs open from the top edge; the previous one
        # snaps shut underneath it.
        k = pop(f, f0, 14) if i else 1.0
        return {"loc": (0, desk_pose(f) + TOP - h / 2 * (0.4 + 0.6 * k) - 0.001, -0.15 + i * 0.01),
                "scale": (0.6 + 0.4 * k, 0.4 + 0.6 * k, 1),
                "alpha": (appear(f, f0, 4) if i else 1.0) * vanish(f, f1, 4)}

    Track(o, fade).bake(max(N_IN, f0 - 1 if i else N_IN), min(N_OUT + 4, f1 + 5), fn)

menu, menu_fade = panel("menu", "menu.png", 3.0)
MENU_IN = bar(14)


def menu_fn(f):
    k = pop(f, MENU_IN, 14)
    mh = 3.0 * image("menu.png").size[1] / image("menu.png").size[0]
    return {"loc": (2.75, desk_pose(f) + TOP - 0.34 - mh / 2 * (0.7 + 0.3 * k) + 0.25, 0.1),
            "scale": (1, max(0.001, 0.2 + 0.8 * k), 1), "alpha": appear(f, MENU_IN, 5) * vanish(f, bar(15) - 6, 6)}


Track(menu, menu_fade).bake(MENU_IN, bar(15), menu_fn)

headline("h_notch", [("Lives in your notch.", WHITE), ("A glance tells you who's working.", MUTED)], bar(11), bar(12) - 2, y=-0.85)
headline("h_needs", [("Taps you when it's stuck.", AMBER), ("Approvals, questions, errors — right when they happen.", MUTED)], bar(12), bar(13) - 2, y=-0.85)
headline("h_list", [("Everything, one hover away.", WHITE), ("What every agent is doing, and where.", MUTED)], bar(13), bar(14) - 2, y=-0.95)
headline("h_menu", [("And in your menu bar.", WHITE), ("Native. Tiny. Always there.", MUTED)], bar(14), bar(15) - 2, x=-0.9, y=-0.85)

# ---------------------------------------------------------------- S7 outro

cmd_s = "brew install hiteshbandhu/tap/hallmonitor"
pill_m, pill_fade, _ = emit_mat("pill", srgb("#15151c"), 1.0)
bpy.ops.mesh.primitive_plane_add(size=1)
pill = bpy.context.active_object
pill.name = "pill"
for v in pill.data.vertices:
    v.co.x *= 7.3
    v.co.y *= 0.62
pb = pill.modifiers.new("round", "BEVEL")
pb.width = 0.3
pb.segments = 12
pb.affect = "VERTICES"
pill.data.materials.append(pill_m)
TYPE_AT = bar(15, 2)


def pill_fn(f):
    k = pop(f, TYPE_AT - 4, 12)
    return {"loc": (0, -1.05, 0.15), "scale": (0.85 + 0.15 * k, max(0.001, k), 1),
            "alpha": appear(f, TYPE_AT - 4, 6) * (1 - in_expo(prog(f, END + 30, 20)))}


Track(pill, pill_fade).bake(TYPE_AT - 4, LAST, pill_fn)

# Typed command: one text object per prefix, each shown for its frames.
prompt, prompt_fade = text("prompt", "$", 0.34, GREEN, fontname=MONO, align="LEFT")
typed = []
chars_per_frame = 1.1
for n in range(1, len(cmd_s) + 1):
    o, fade = text(f"cmd{n}", cmd_s[:n], 0.34, WHITE, fontname=MONO, align="LEFT")
    typed.append((o, fade, n))
bpy.context.view_layer.update()
cmd_w = typed[-1][0].dimensions.x
cx0 = -(cmd_w + 0.42) / 2


def fade_out_end(f):
    return 1 - in_expo(prog(f, END + 30, 20))


Track(prompt, prompt_fade).bake(TYPE_AT, LAST, lambda f: {"loc": (cx0, -1.05, 0.2), "alpha": appear(f, TYPE_AT, 4) * fade_out_end(f)})
for o, fade, n in typed:
    start = TYPE_AT + 4 + int((n - 1) / chars_per_frame)
    stop = TYPE_AT + 4 + int(n / chars_per_frame) - 1 if n < len(cmd_s) else LAST
    Track(o, fade).bake(start, max(start, stop), lambda f: {"loc": (cx0 + 0.42, -1.05, 0.2), "alpha": fade_out_end(f)})

# Blinking cursor after the command.
cur_m, cur_fade, _ = emit_mat("cursor", GREEN, 1.4)
cursor = plane("cursor", 0.16, 0.34, cur_m)
Track(cursor, cur_fade).bake(TYPE_AT + 4, LAST, lambda f: {
    "loc": (cx0 + 0.42 + (typed[min(len(typed) - 1, max(0, int((f - TYPE_AT - 4) * chars_per_frame)))][0].dimensions.x) + 0.1, -1.05, 0.2),
    "alpha": (1.0 if (f // 9) % 2 == 0 else 0.0) * fade_out_end(f)})

works, works_fade = text("works", "Works with Claude Code and Codex  ·  macOS & Linux  ·  open source", 0.24, MUTED, fontname=BODY)
Track(works, works_fade).bake(bar(16), LAST, lambda f: {"loc": (0, -1.85, 0.2), "alpha": appear(f, bar(16), 12) * fade_out_end(f)})

# ---------------------------------------------------------------- render

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "out", "launch.blend"))

if "--stills" in argv:
    frames = [int(x) for x in argv[argv.index("--stills") + 1].split(",")]
    os.makedirs(os.path.join(HERE, "out", "stills"), exist_ok=True)
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(HERE, "out", "stills", f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
elif "--anim" in argv:
    if "--from" in argv:
        scene.frame_start = int(argv[argv.index("--from") + 1])
    if "--to" in argv:
        scene.frame_end = int(argv[argv.index("--to") + 1])
    bpy.ops.render.render(animation=True)
