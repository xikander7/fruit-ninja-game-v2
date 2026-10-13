"""GPU post-processing: bloom, lens effects, tonemap, vignette and grain over the CPU-drawn frame.

The game still draws everything with pygame into 1280x720 surfaces: `base` (the lit scene), `emissive` (glowing
things only, black = no glow) and `ui` (HUD and overlays, premultiplied alpha). PostFX uploads them, blooms the
first two, grades the result and lays the UI over it untouched, so text never warps, fringes or dims with the camera.
"""
import array
import math

import moderngl
import pygame

from .settings import W, H

# Bloom (the soft glow around bright things) is made by shrinking the picture again and again, blurring a little each time,
# then growing it back and adding the levels together. The shaders below are tiny programs that run on the graphics card (GPU),
# written in GLSL, once for every pixel.
LEVELS = 5  # bloom mip chain: 640x360 down to 40x22

# Vertex shader: positions the one big triangle that covers the whole screen and tells the pixel shaders where on the picture (uv, 0-1) each pixel is.
# Every pass below reuses it, because we only ever draw full-screen images.
VERT = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

# Textures keep pygame's row order (row 0 = top), so every pass up to the composite works in "image uv"
# and only the composite flips V to land the picture the right way up in GL's bottom-left space.

# Dual-Kawase downsample: centre + four diagonal taps half a texel out.
DOWN_TAPS = """
vec3 down(sampler2D t, vec2 uv, vec2 texel) {
    vec3 s = tap(t, uv) * 4.0;
    s += tap(t, uv + vec2(-texel.x, -texel.y));
    s += tap(t, uv + vec2( texel.x, -texel.y));
    s += tap(t, uv + vec2(-texel.x,  texel.y));
    s += tap(t, uv + vec2( texel.x,  texel.y));
    return s / 8.0;
}
"""

# Pass 1 ("pre"): pick out what should glow (emissive layer plus the brightest parts of the scene) while shrinking to half size.
PREFILTER = """
#version 330
uniform sampler2D u_base;
uniform sampler2D u_emissive;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 f_color;
vec3 src(vec2 uv) {
    vec3 b = texture(u_base, uv).rgb;
    float luma = dot(b, vec3(0.2126, 0.7152, 0.0722));
    // soft threshold: only the brightest parts of the lit scene glow, and gently
    return texture(u_emissive, uv).rgb + b * smoothstep(0.75, 0.85, luma) * 0.25;
}
vec3 tap(sampler2D t, vec2 uv) { return src(uv); }
""" + DOWN_TAPS + """
void main() { f_color = vec4(down(u_base, v_uv, u_texel), 1.0); }
"""

# Passes 2-5 ("down"): shrink the glow image by half again, softening it each time.
DOWN = """
#version 330
uniform sampler2D u_src;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 f_color;
vec3 tap(sampler2D t, vec2 uv) { return texture(t, uv).rgb; }
""" + DOWN_TAPS + """
void main() { f_color = vec4(down(u_src, v_uv, u_texel), 1.0); }
"""

# Dual-Kawase upsample of the smaller level, added onto this level's downsample.
UP = """
#version 330
uniform sampler2D u_small;
uniform sampler2D u_same;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec2 t = u_texel;
    vec3 s = texture(u_small, v_uv + vec2(-2.0 * t.x, 0.0)).rgb;
    s += texture(u_small, v_uv + vec2(2.0 * t.x, 0.0)).rgb;
    s += texture(u_small, v_uv + vec2(0.0, -2.0 * t.y)).rgb;
    s += texture(u_small, v_uv + vec2(0.0, 2.0 * t.y)).rgb;
    s += texture(u_small, v_uv + vec2(-t.x, -t.y)).rgb * 2.0;
    s += texture(u_small, v_uv + vec2(t.x, -t.y)).rgb * 2.0;
    s += texture(u_small, v_uv + vec2(-t.x, t.y)).rgb * 2.0;
    s += texture(u_small, v_uv + vec2(t.x, t.y)).rgb * 2.0;
    f_color = vec4(s / 12.0 + texture(u_same, v_uv).rgb, 1.0);
}
"""

# Final pass ("comp"): add the bloom to the scene, then apply the camera zoom, shockwave ripples, colour fringing,
# saturation, film-like brightness curve, dark corners (vignette) and film grain. The HUD (`ui`) is laid on last, untouched.
COMPOSITE = """
#version 330
uniform sampler2D u_base;
uniform sampler2D u_emissive;
uniform sampler2D u_bloomtex;
uniform sampler2D u_ui;
uniform float u_zoom;
uniform vec4 u_shock[2];
uniform float u_aberration;
uniform float u_saturation;
uniform float u_flash;
uniform float u_bloom;
uniform float u_time;
in vec2 v_uv;
out vec4 f_color;

const float ASPECT = 16.0 / 9.0;

vec3 scene(vec2 uv) {
    // bloom texture holds LEVELS added levels, so normalise before applying the strength
    return texture(u_base, uv).rgb + texture(u_emissive, uv).rgb + texture(u_bloomtex, uv).rgb * (u_bloom / 5.0);
}

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);  // flip V: textures are stored top row first
    vec4 ui = texture(u_ui, uv);  // sampled before any warp: the HUD sits on the glass, not in the scene
    uv = 0.5 + (uv - 0.5) / u_zoom;
    for (int i = 0; i < 2; i++) {
        vec4 s = u_shock[i];
        if (s.w == 0.0) continue;
        vec2 d = (uv - s.xy) * vec2(ASPECT, 1.0);  // aspect-correct so the ring is round
        float dist = length(d);
        float x = (dist - s.z) / 0.06;  // ring width 0.06
        if (abs(x) < 1.0 && dist > 0.0) {
            float k = (1.0 - x * x) * x;  // push in front of the ring, pull behind it
            uv -= (d / dist) * vec2(1.0 / ASPECT, 1.0) * s.w * k;
        }
    }
    vec2 split = (uv - 0.5) * u_aberration;
    vec3 col = vec3(scene(uv + split).r, scene(uv).g, scene(uv - split).b);

    float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = max(mix(vec3(luma), col, u_saturation), 0.0);

    // mild filmic curve: identity below the knee, soft shoulder above, light S-curve that keeps 0.5 fixed
    const float knee = 0.8;
    vec3 over = max(col - knee, 0.0);
    col = mix(col, knee + (1.0 - knee) * (1.0 - exp(-over / (1.0 - knee))), step(knee, col));
    col = mix(col, col * col * (3.0 - 2.0 * col), 0.1);

    vec2 c = (uv - 0.5) * vec2(ASPECT, 1.0);
    float r = length(c) / length(vec2(ASPECT, 1.0) * 0.5);  // 0 centre, 1 corner
    col *= 1.0 - 0.35 * r * r;

    col += (hash(gl_FragCoord.xy + fract(u_time) * 97.0) - 0.5) * 0.05;  // grain, amplitude 0.025
    col += u_flash;
    // premultiplied alpha-over; the game clears its UI layer to alpha 1/255 (see UI_CLEAR), which reads as clear
    float a = max(ui.a - 1.0 / 255.0, 0.0) * (255.0 / 254.0);
    f_color = vec4(clamp(col, 0.0, 1.0) * (1.0 - a) + ui.rgb, 1.0);
}
"""


def letterbox(x, y, w, h):
    """Fit the 16:9 game picture inside any window shape, leaving black bars at the sides or top/bottom. Returns x, y, width, height."""
    """Largest 16:9 rect centred in (x, y, w, h)."""
    s = min(w / W, h / H)
    vw, vh = max(1, round(W * s)), max(1, round(H * s))
    return x + (w - vw) // 2, y + (h - vh) // 2, vw, vh


def to_logical(pos, window_size):
    """Window pixels -> 1280x720 through the letterbox."""
    x, y, w, h = letterbox(0, 0, *window_size)
    return ((pos[0] - x) * W / w, (pos[1] - y) * H / h)


class PostFX:
    """Owns the OpenGL objects (textures, shaders) and runs the bloom + final-look passes each frame."""
    def __init__(self, ctx=None):
        """Create (or reuse) an OpenGL context, then allocate the textures for the game's layers and each bloom level, and compile the shaders."""
        self.owns_ctx = ctx is None  # a context we made is ours to release (each F11 toggle makes a new one)
        self.ctx = ctx or moderngl.create_context()
        ctx = self.ctx
        self.vbo = ctx.buffer(array.array("f", [-1, -1, 3, -1, -1, 3]))  # one oversized triangle covers the screen
        self.base = self.texture((W, H), 3, "f1")
        self.emissive = self.texture((W, H), 3, "f1")
        self.ui = self.texture((W, H), 4, "f1")
        self.ui_blank = False  # True while the ui texture holds the all-clear upload for callers without a ui layer
        self.downs, self.ups = [], []
        w, h = W // 2, H // 2
        for i in range(LEVELS):
            self.downs.append(self.texture((w, h), 4, "f2"))
            if i < LEVELS - 1:
                self.ups.append(self.texture((w, h), 4, "f2"))
            w, h = max(1, w // 2), max(1, h // 2)
        self.fbos = {t: ctx.framebuffer([t]) for t in self.downs + self.ups}
        self.progs = {name: ctx.program(vertex_shader=VERT, fragment_shader=src)
                      for name, src in (("pre", PREFILTER), ("down", DOWN), ("up", UP), ("comp", COMPOSITE))}
        self.vaos = {name: ctx.vertex_array(p, [(self.vbo, "2f", "in_pos")]) for name, p in self.progs.items()}
        self.time = 0.0

    def texture(self, size, comps, dtype):
        """Make a GPU texture with smooth (linear) filtering. `comps` = colour channels (3 = RGB, 4 = RGBA)."""
        t = self.ctx.texture(size, comps, dtype=dtype)
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        t.repeat_x = t.repeat_y = False
        return t

    def set(self, prog, **uniforms):
        """Send values ("uniforms") to a shader program, such as zoom or saturation."""
        p = self.progs[prog]
        for k, v in uniforms.items():
            if k in p:  # the GLSL compiler drops unused uniforms
                p[k].value = v

    def blit(self, prog, out, *textures):
        """Run shader `prog` over the whole screen, reading the given textures and writing into framebuffer `out`."""
        self.fbos[out].use()
        for unit, t in enumerate(textures):
            t.use(unit)
        self.vaos[prog].render(moderngl.TRIANGLES, vertices=3)

    def render(self, base, emissive, params, viewport, target=None, ui=None):
        """Bloom + composite to the window (or `target`, an offscreen framebuffer used by tests). `ui` (SRCALPHA,
        premultiplied, optional) is laid over the graded picture with no post-processing at all.

        params (all optional, missing = neutral): zoom (1.0), aberration (0, uv offset per unit of distance from
        centre), saturation (1), flash (0..1 additive white), shocks: up to 2 (cx, cy, radius, strength) with the
        centre in screen uv (0,0 = top-left) and the radius in units of screen height.
        """
        self.base.write(pygame.image.tobytes(base, "RGB"))
        self.emissive.write(pygame.image.tobytes(emissive, "RGB"))
        if ui is not None:
            self.ui.write(pygame.image.tobytes(ui, "RGBA"))
            self.ui_blank = False
        elif not self.ui_blank:
            self.ui.write(bytes(W * H * 4))
            self.ui_blank = True
        # The grain pattern moves a little every frame, so it shimmers like film.
        self.time += 1 / 60

        # bloom: prefilter into the first half-res level, then down the chain ...
        self.set("pre", u_base=0, u_emissive=1, u_texel=(1 / W, 1 / H))
        self.blit("pre", self.downs[0], self.base, self.emissive)
        for src, dst in zip(self.downs, self.downs[1:]):
            self.set("down", u_src=0, u_texel=(1 / src.width, 1 / src.height))
            self.blit("down", dst, src)
        # ... and back up, adding each level on the way
        small = self.downs[-1]
        for i in range(LEVELS - 2, -1, -1):
            self.set("up", u_small=0, u_same=1, u_texel=(1 / small.width, 1 / small.height))
            self.blit("up", self.ups[i], small, self.downs[i])
            small = self.ups[i]

        shocks = list(params.get("shocks", ()))[:2]
        shocks += [(0.0, 0.0, 0.0, 0.0)] * (2 - len(shocks))
        p = self.progs["comp"]
        self.set("comp", u_base=0, u_emissive=1, u_bloomtex=2, u_ui=3,
                 u_zoom=float(params.get("zoom", 1.0)), u_aberration=float(params.get("aberration", 0.0)),
                 u_saturation=float(params.get("saturation", 1.0)), u_flash=float(params.get("flash", 0.0)),
                 u_bloom=1.1, u_time=math.fmod(self.time, 1.0))
        if "u_shock" in p:
            p["u_shock"].value = [tuple(float(v) for v in s) for s in shocks]

        fb = target or self.ctx.screen
        fb.use()
        fb.clear(0.0, 0.0, 0.0, 1.0)
        fb.viewport = letterbox(*viewport)
        self.base.use(0)
        self.emissive.use(1)
        self.ups[0].use(2)
        self.ui.use(3)
        self.vaos["comp"].render(moderngl.TRIANGLES, vertices=3)

    def release(self):
        """Free the GPU objects (called when the window mode changes or the game exits)."""
        for obj in [*self.vaos.values(), *self.progs.values(), *self.fbos.values(),
                    self.base, self.emissive, self.ui, *self.downs, *self.ups, self.vbo]:
            obj.release()
        if self.owns_ctx:
            self.ctx.release()
