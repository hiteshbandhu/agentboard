"""7.2 s notch clip: the top of a MacBook screen, the notch doing its thing.

Static camera (no kick shake), no vignette. Three bars of the beat from the
drop (100 BPM → 18 frames per beat at 30 fps):

  beat 0   bare notch
  beat 1   ears slide out: agents working
  bar 2    drops open: "Flaky e2e on checkout · needs you"
  bar 2.2  becomes: "Migrate billing · finished after 12m"
  bar 3    springs open into the full list
  bar 3.3  folds back to the ears

  Blender -b -P launch/notch_clip.py -- --stills 10,40,80,120,160,205
  Blender -b -P launch/notch_clip.py -- --anim
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "out", "assets")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

FPS, BEAT, BAR = 30, 18, 72
LAST = 3 * BAR - 1  # 216 frames


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(f, f0, dur):
    return clamp((f - f0) / dur)


def out_expo(t):
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def in_cubic(t):
    return t ** 3


def spring(t, bounce=0.28):
    """A damped spring from 0 to 1, like SwiftUI's .spring(bounce:)."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    w = 2 * math.pi * 1.35
    return 1 - math.exp(-6.5 * t * (1 - bounce)) * math.cos(w * t)


def in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)


scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
scene.render.engine = "BLENDER_EEVEE"
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 0, LAST
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.6
scene.eevee.motion_blur_steps = 8
scene.eevee.taa_render_samples = 64
try:
    scene.view_settings.view_transform = "Standard"
except Exception:
    pass
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(HERE, "out", "notch_frames", "")
world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)

# A whisper of bloom on the brightest pixels only.
try:
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    out = ng.nodes.new("NodeGroupOutput")
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 0.85
    gl.inputs["Strength"].default_value = 0.3
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = ng
except Exception as e:
    print("compositor:", e)

col = scene.collection
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
cam.data.lens = 40
col.objects.link(cam)
scene.camera = cam


def mat(name, color=None, image=None, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    fade = nt.nodes.new("ShaderNodeValue")
    fade.outputs[0].default_value = 1
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    if image:
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = image
        tx.interpolation = "Cubic"
        nt.links.new(tx.outputs["Color"], em.inputs["Color"])
        nt.links.new(tx.outputs["Alpha"], mul.inputs[0])
    else:
        em.inputs["Color"].default_value = color
        mul.inputs[0].default_value = 1
    nt.links.new(fade.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], o.inputs["Surface"])
    return m, fade.outputs[0]


def plane(name, w, h, m):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new()
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    return o


def key(o, fade, f0, f1, fn):
    for f in range(f0, f1 + 1):
        p = fn(f)
        if "loc" in p:
            o.location = p["loc"]
            o.keyframe_insert("location", frame=f)
        if "scale" in p:
            o.scale = p["scale"]
            o.keyframe_insert("scale", frame=f)
        if "alpha" in p and fade is not None:
            fade.default_value = clamp(p["alpha"])
            fade.keyframe_insert("default_value", frame=f)


SF = bpy.data.fonts.load("/System/Library/Fonts/SFNS.ttf")
TELEGRAF = bpy.data.fonts.load(os.path.expanduser("~/Library/Fonts/PPTelegraf-Ultrabold.otf"))


def label(name, body, size, color, align="LEFT", font=SF):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    m, fade = mat(name, color)
    cu.materials.append(m)
    o = bpy.data.objects.new(name, cu)
    col.objects.link(o)
    return o, fade


# ---- geometry: the snapshots are 536 pt wide; map that to scene units.
CANVAS_W = 8.4
PT = CANVAS_W / 536          # scene units per point
NOTCH_H = 32 * PT
TOP = 2.1                     # the screen's top edge

# Camera: static, with a barely-there drift in.
key(cam, None, 0, LAST, lambda f: {"loc": (0, 0, 10.0 - 0.25 * in_out(f / LAST))})

# ---- the desktop: gradient + slow color glows, rounded top corners of a
# MacBook display implied by the black bezel above.
dm = bpy.data.materials.new("desk")
dm.use_nodes = True
nt = dm.node_tree
nt.nodes.clear()
o_ = nt.nodes.new("ShaderNodeOutputMaterial")
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
rp = nt.nodes.new("ShaderNodeValToRGB")
rp.color_ramp.interpolation = "EASE"
rp.color_ramp.elements[0].color = srgb("#0b1022")
rp.color_ramp.elements[1].color = srgb("#2f4282")
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(tc.outputs["UV"], sep.inputs[0])
nt.links.new(sep.outputs["Y"], rp.inputs["Fac"])
nt.links.new(rp.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs[0], o_.inputs["Surface"])
desk = plane("desk", 20, 8, dm)
desk.location = (0, TOP - 4, -1)


def glow(name, color, size, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.surface_render_method = "BLENDED"
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Location"].default_value = (-1, -1, 0)
    mp.inputs["Scale"].default_value = (2, 2, 2)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.color_ramp.interpolation = "EASE"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], rp.inputs["Fac"])
    nt.links.new(rp.outputs["Color"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], o.inputs["Surface"])
    return plane(name, size, size, m)


for i, (c, x, y, s, k) in enumerate([("#8b6cff", -4.4, -1.0, 9, 0.75), ("#2dd4bf", 4.8, -2.2, 10, 0.6), ("#e0845f", 0.6, -3.4, 8, 0.55)]):
    g = glow(f"glow{i}", srgb(c), s, k)
    key(g, None, 0, LAST, lambda f, x=x, y=y, i=i: {"loc": (x + 0.5 * math.sin(f * 0.02 + i * 2), y + 0.35 * math.cos(f * 0.017 + i), -0.9)})

# ---- the bezel: solid black above the screen's top edge.
bzm, _ = mat("bezel", (0, 0, 0, 1))
bz = plane("bezel", 20, 3, bzm)
bz.location = (0, TOP + 1.5, -0.35)

# ---- the menu bar: translucent strip, menus on the left, extras on the right.
mbm, _ = mat("menubar", srgb("#4a5680"))
mb = plane("menubar", 20, NOTCH_H, mbm)
mb.location = (0, TOP - NOTCH_H / 2, -0.5)
_ = mb.data.materials[0].node_tree.nodes  # (strip is drawn a touch translucent below)
for n in mbm.node_tree.nodes:
    if n.type == "VALUE":
        n.outputs[0].default_value = 0.45

MB_Y = TOP - NOTCH_H / 2
menus, _ = label("menus", "    Finder    File    Edit    View    Go    Window    Help", 13 * PT, srgb("#f2f2f5"), "RIGHT")
menus.location = (-(180 * PT) / 2 - 90 * PT, MB_Y, -0.45)
clock, _ = label("clock", "Tue 9:41 AM", 13 * PT, srgb("#f2f2f5"), "LEFT")
clock.location = (180 * PT / 2 + 128 * PT, MB_Y, -0.45)
# Our menu bar glyph: three bars, left of the clock.
for i, h in enumerate([7, 12, 9]):
    bm, _ = mat(f"mini{i}", srgb("#f2f2f5"))
    b = plane(f"mini{i}", 3.4 * PT, h * PT, bm)
    b.location = (180 * PT / 2 + 100 * PT + i * 5.3 * PT, MB_Y - 6 * PT + h * PT / 2, -0.45)

# ---- the notch states, each anchored to the top edge.
def image(fn):
    img = bpy.data.images.load(os.path.join(A, fn))
    img.colorspace_settings.name = "sRGB"
    return img


def state(name, fn):
    img = image(fn)
    h = CANVAS_W * img.size[1] / img.size[0]
    m, fade = mat(name, image=img)
    o = plane(name, CANVAS_W, h, m)
    return o, fade, h


hidden = state("hidden", "notch_hidden.png")
compact = state("compact", "notch_compact.png")
needs = state("needs", "notch_banner_needs.png")
done = state("done", "notch_banner_done.png")
expanded = state("expanded", "notch_expanded.png")

B1 = BEAT            # ears out
B_NEEDS = BAR        # bar 2: needs you
B_DONE = BAR + 2 * BEAT
B_EXP = 2 * BAR      # bar 3: list
B_FOLD = 2 * BAR + 3 * BEAT


def place(obj, fade, h, f0, f1, sx0, sy0, z, fade_in=4, fade_out=4, dur=0.55):
    """Show a state between f0 and f1, springing from (sx0, sy0) scale."""
    frames = dur * FPS

    def fn(f):
        k = spring(prog(f, f0, frames))
        sx = sx0 + (1 - sx0) * k
        sy = sy0 + (1 - sy0) * k
        a = clamp((f - f0 + 1) / fade_in) * (1 - clamp((f - f1) / fade_out))
        vis = f0 - 1 <= f <= f1 + fade_out
        return {"loc": (0, TOP - h * sy / 2, z), "scale": (sx, sy, 1), "alpha": a if vis else 0.0}

    key(obj, fade, 0, LAST, fn)


o, fa, h = hidden
place(o, fa, h, -10, B1 + 3, 1, 1, -0.30, fade_in=1)
o, fa, h = compact
place(o, fa, h, B1, B_NEEDS + 2, 388 / 540, 1, -0.29)
o, fa, h = needs
place(o, fa, h, B_NEEDS, B_DONE, 0.78, 0.32, -0.28, fade_in=3)
o, fa, h = done
place(o, fa, h, B_DONE, B_EXP + 2, 0.96, 0.96, -0.27, fade_in=3, dur=0.4)
o, fa, h = expanded
place(o, fa, h, B_EXP, B_FOLD, 0.8, 0.2, -0.26, fade_in=3)
# The fold: an independent compact for the ending (copies would share the
# fade animation with the first one).
o, fa, h = state("compact_end", "notch_compact.png")
place(o, fa, h, B_FOLD, LAST + 10, 1.25, 1.8, -0.25, fade_in=3, dur=0.5)

# ---- a quiet lockup, bottom right; it steps aside while the list is open.
lock_y = -2.15


def lock_vis(f):
    return 1 - clamp((f - B_EXP) / 6) * (1 - clamp((f - B_FOLD - 4) / 10))

for i, (hh, c) in enumerate(zip([0.14, 0.24, 0.18], ["#2dd4bf", "#4ade80", "#a3e635"])):
    m, fd = mat(f"lb{i}", srgb(c), strength=1.2)
    b = plane(f"lb{i}", 0.068, hh, m)
    key(b, fd, 0, LAST, lambda f, i=i, hh=hh: {"loc": (2.62 + i * 0.1, lock_y - 0.12 + hh / 2, 0),
                                               "alpha": out_expo(prog(f, 24 + i * 2, 16)) * lock_vis(f)})
word, wf = label("word", "agentboard", 0.3, srgb("#f4f4f6"), "LEFT", TELEGRAF)
key(word, wf, 0, LAST, lambda f: {"loc": (2.97, lock_y - 0.035, 0), "alpha": out_expo(prog(f, 30, 16)) * lock_vis(f)})

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "out", "notch_clip.blend"))

if "--stills" in argv:
    os.makedirs(os.path.join(HERE, "out", "notch_stills"), exist_ok=True)
    for f in [int(x) for x in argv[argv.index("--stills") + 1].split(",")]:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(HERE, "out", "notch_stills", f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
elif "--anim" in argv:
    bpy.ops.render.render(animation=True)
