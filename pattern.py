"""Pattern rendering in plain numpy (no ComfyUI dependency, so it can be tested alone).

Every pattern is drawn as a coverage map in [0, 1] (0 = background color, 1 = pattern color)
with a 1px analytic anti-aliased edge, then mixed between the two colors.
"""

import math

import numpy as np

PATTERNS = [
    "solid",
    "dots",
    "stripes",
    "grid",
    "gingham",
    "checkerboard",
    "focus_lines",
    # added in 1.1 (appended so saved workflows keep their choice)
    "border",
    "hearts",
    "stars",
    # added in 0.3 (appended so saved workflows keep their choice)
    "gradient",
    "halftone",
]
MOTIFS = ("hearts", "stars")


def parse_color(text):
    """'#ffcc00', 'ffcc00', '#fc0' -> float32 RGB in [0, 1]."""
    s = text.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"color must be like #RRGGBB: {text!r}")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def _coords(width, height, angle):
    """Pixel-center coordinates rotated by `angle` degrees around the image center."""
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    x -= (width - 1) / 2.0
    y -= (height - 1) / 2.0
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def _aa(signed_dist):
    """Signed distance in px (negative = inside) -> coverage with a 1px soft edge."""
    return np.clip(0.5 - signed_dist, 0.0, 1.0)


def _band(u, period, width):
    """Coverage of bands `width` px wide, repeating every `period` px along u."""
    d = np.abs(np.mod(u, period) - period / 2.0) - width / 2.0
    return _aa(d)


def _dots(u, v, period, diameter, stagger):
    r = diameter / 2.0

    def lattice(ou, ov):
        du = np.mod(u - ou, period) - period / 2.0
        dv = np.mod(v - ov, period) - period / 2.0
        return _aa(np.sqrt(du * du + dv * dv) - r)

    cov = lattice(0.0, 0.0)
    if stagger:
        cov = np.maximum(cov, lattice(period / 2.0, period / 2.0))
    return cov


def _sd_heart(x, y):
    """Signed distance to a heart, tip at the origin, about 1.2 wide and 1.1 tall (y up). After Inigo Quilez."""
    x = np.abs(x)
    upper = np.sqrt((x - 0.25) ** 2 + (y - 0.75) ** 2) - math.sqrt(2.0) / 4.0
    t = 0.5 * np.maximum(x + y, 0.0)
    lower = np.sqrt(np.minimum(x * x + (y - 1.0) ** 2, (x - t) ** 2 + (y - t) ** 2)) * np.sign(x - y)
    return np.where(x + y > 1.0, upper, lower)


def _sd_star5(x, y, inner):
    """Signed distance to a five-pointed star of outer radius 1, point up (y up). `inner` = inner/outer radius.
    After Inigo Quilez."""
    k1x, k1y = 0.809016994375, -0.587785252292
    x = np.abs(x)
    for kx, ky in ((k1x, k1y), (-k1x, k1y)):
        m = np.maximum(kx * x + ky * y, 0.0)
        x, y = x - 2.0 * m * kx, y - 2.0 * m * ky
    x = np.abs(x)
    y = y - 1.0
    bax, bay = inner * -k1y - 0.0, inner * k1x - 1.0
    h = np.clip((x * bax + y * bay) / (bax * bax + bay * bay), 0.0, 1.0)
    return np.sqrt((x - bax * h) ** 2 + (y - bay * h) ** 2) * np.sign(y * bax - x * bay)


def _motif_sd(kind, dx, dy, size, roundness):
    """Signed distance in px to one motif `size` px wide centered at (0, 0); dy points down (image rows).
    Roundness 0 keeps the mathematical shape; higher values round the tips and the dips (the shape is drawn
    smaller and grown back by a radius, so the overall size stays about the same)."""
    rnd = float(np.clip(roundness, 0.0, 1.0))
    if kind == "hearts":
        r = rnd * 0.16 * size
        s = max(size - 2 * r, 1e-3) / 1.2
        return _sd_heart(dx / s, -dy / s + 0.55) * s - r
    if kind == "stars":
        r = rnd * 0.10 * size
        s = max(size / 2.0 - r, 1e-3) / 0.95
        inner = 0.40 + 0.14 * rnd  # chubbier arms as it gets rounder
        return _sd_star5(dx / s, -dy / s - 0.1, inner) * s - r
    raise ValueError(kind)


def _motifs(kind, u, v, period, size, stagger, roundness):
    def lattice(ou, ov):
        du = np.mod(u - ou, period) - period / 2.0
        dv = np.mod(v - ov, period) - period / 2.0
        return _motif_sd(kind, du, dv, size, roundness)

    d = lattice(0.0, 0.0)
    if stagger:
        d = np.minimum(d, lattice(period / 2.0, period / 2.0))
    return _aa(d)


def _ramp(u, thickness):
    """0 -> 1 across the whole picture along u. thickness moves the middle: 0.5 = linear, larger = more of
    the picture leans to the pattern color."""
    t = (u - u.min()) / max(float(u.max() - u.min()), 1e-6)
    mid = float(np.clip(1.0 - thickness, 0.02, 0.98))
    return t ** (math.log(0.5) / math.log(mid)), t


def _halftone(u, v, period, thickness, stagger):
    """Dots on a grid whose size grows along u: none at one end, `thickness` x 1.4 x period at the other.
    Each dot takes its size from its own cell center, so the dots stay round."""
    u0, u1 = float(u.min()), float(u.max())
    dmax = max(thickness, 0.0) * period * 1.4

    def lattice(ou, ov):
        cu = np.floor((u - ou) / period) * period + period / 2.0 + ou
        cv = np.floor((v - ov) / period) * period + period / 2.0 + ov
        t = np.clip((cu - u0) / max(u1 - u0, 1e-6), 0.0, 1.0)
        return np.sqrt((u - cu) ** 2 + (v - cv) ** 2) - dmax * t / 2.0

    d = lattice(0.0, 0.0)
    if stagger:
        d = np.minimum(d, lattice(period / 2.0, period / 2.0))
    return _aa(d)


def _focus_lines(width, height, lines, inner_radius, center_x, center_y, thickness, seed):
    """Manga-style speed lines: thin wedges pointing at a center, clear area in the middle."""
    rng = np.random.default_rng(seed)
    cx = center_x * (width - 1)
    cy = center_y * (height - 1)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = x - cx, y - cy
    rho = np.sqrt(dx * dx + dy * dy)
    theta = np.mod(np.arctan2(dy, dx), 2 * math.pi)
    # Elliptical radius (1.0 = the ellipse touching the image edges), so the empty
    # center follows the image's aspect ratio like hand-drawn focus lines.
    ell = np.sqrt((dx / (width / 2.0)) ** 2 + (dy / (height / 2.0)) ** 2)
    reach = float(ell.max())

    ang = rng.uniform(0, 2 * math.pi, lines)
    half_w = rng.uniform(0.35, 1.0, lines) * thickness * math.pi / lines
    start = inner_radius * rng.uniform(0.85, 1.2, lines)
    taper = max(reach - inner_radius, 1e-3) * 0.4
    order = np.argsort(ang)
    ang, half_w, start = ang[order], half_w[order], start[order]

    # Only the few lines nearest in angle can cover a pixel, so test those instead of all lines.
    nearest = np.searchsorted(ang, theta)
    cov = np.zeros((height, width), dtype=np.float32)
    for k in range(-3, 3):
        i = np.mod(nearest + k, lines)
        dth = np.abs(np.mod(theta - ang[i] + math.pi, 2 * math.pi) - math.pi)
        # Width grows from 0 at the start radius to full width, so each line ends in a point.
        grow = np.clip((ell - start[i]) / taper, 0.0, 1.0)
        dist = (dth - half_w[i] * grow) * rho
        cov = np.maximum(cov, _aa(dist) * (ell > start[i]))
    return cov


def coverage(pattern, width, height, spacing=64, thickness=0.5, angle=0.0, stagger=True,
             lines=120, inner_radius=0.45, center_x=0.5, center_y=0.5, seed=0, roundness=0.6):
    """Coverage map (H, W) float32 of the pattern color."""
    if pattern == "solid":
        return np.zeros((height, width), dtype=np.float32)
    if pattern == "focus_lines":
        return _focus_lines(width, height, lines, inner_radius, center_x, center_y, thickness, seed)

    u, v = _coords(width, height, angle)
    p = float(spacing)
    w = max(thickness, 0.0) * p
    if pattern == "dots":
        return _dots(u, v, p, w, stagger)
    if pattern == "stripes":
        return _band(u, p, w)
    if pattern == "border":  # horizontal stripes (stripes turned 90 degrees, kept as its own name)
        return _band(v, p, w)
    if pattern in MOTIFS:
        return _motifs(pattern, u, v, p, w, stagger, roundness)
    if pattern == "gradient":  # angle: direction of the change (0 = left to right)
        return _ramp(u, thickness)[0]
    if pattern == "halftone":
        return _halftone(u, v, p, thickness, stagger)
    if pattern == "grid":
        return np.maximum(_band(u, p, w), _band(v, p, w))
    if pattern == "gingham":
        # Overlapping half-tone bands: one band = half color, crossing = full color.
        return (_band(u, p, w) + _band(v, p, w)) * 0.5
    if pattern == "checkerboard":
        a, b = _band(u, 2 * p, p), _band(v, 2 * p, p)
        return a + b - 2 * a * b
    raise ValueError(f"unknown pattern: {pattern!r}")


def render(pattern, width, height, color, background, **kw):
    """RGB image (H, W, 3) float32 in [0, 1]."""
    cov = coverage(pattern, width, height, **kw).astype(np.float32)[..., None]
    fg, bg = parse_color(color), parse_color(background)
    return bg * (1.0 - cov) + fg * cov, cov[..., 0]
