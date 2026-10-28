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
]


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
             lines=120, inner_radius=0.45, center_x=0.5, center_y=0.5, seed=0):
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
