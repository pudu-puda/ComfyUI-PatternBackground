"""Frames drawn over the edge of a finished image (plain numpy, testable alone).

The frame is a band around a window with rounded corners. Styles:
  rounded      the band and one thin line inside the window
  double_line  the band and two thin lines
  scallop      the window edge is a row of round bumps (a cloud / biscuit edge) with a line along it
  plain        the band only
Small motifs (hearts, stars, dots) can sit on the four corners.
"""

import random

import numpy as np

try:
    from .pattern import _aa, _motif_sd, parse_color
except ImportError:  # imported alone (tests)
    from pattern import _aa, _motif_sd, parse_color

STYLES = ["rounded", "double_line", "scallop", "plain"]
CORNER_MOTIFS = ["none", "hearts", "stars", "dots"]


def _sd_round_box(x, y, hw, hh, r):
    """Signed distance to a box of half size (hw, hh) with corner radius r, centered at the origin."""
    r = min(r, hw, hh)
    qx = np.abs(x) - (hw - r)
    qy = np.abs(y) - (hh - r)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    return outside + np.minimum(np.maximum(qx, qy), 0.0) - r


def _scallop_centers(hw, hh, bump):
    """Bump centers along the straight edges of a (hw, hh) box, evenly spaced and meeting at the corners."""
    pts = []
    for half, other, horizontal in ((hw, hh, True), (hh, hw, False)):
        n = max(2, int(round(2 * half / (bump * 1.7))))
        for t in np.linspace(-half, half, n + 1):
            for s in (-other, other):
                pts.append((t, s) if horizontal else (s, t))
    return sorted(set(pts))


def window_sd(width, height, margin, corner_radius, style, bump, reach=64.0):
    """Signed distance (H, W) to the window edge: negative inside the window, positive on the frame.
    `reach`: how far inside the edge the distance must be right (for the inner lines); scallop bumps are only
    computed that close to each bump, so large images stay fast."""
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    x -= (width - 1) / 2.0
    y -= (height - 1) / 2.0
    hw, hh = width / 2.0 - margin, height / 2.0 - margin
    if hw <= 1 or hh <= 1:
        raise ValueError("margin is too large for the image")
    d = _sd_round_box(x, y, hw, hh, corner_radius)
    if style == "scallop":
        r = bump / 2.0
        dc = np.full_like(d, np.inf)
        # far inside the window the bumps barely change the line; cap the box so extreme settings stay bounded
        ext = int(np.ceil(min(r + reach, 4 * r + 64))) + 2
        for cx, cy in _scallop_centers(hw - r * 0.35, hh - r * 0.35, bump):
            # pixel box around the bump (centered coordinates -> array indices)
            px, py = int(round(cx + (width - 1) / 2.0)), int(round(cy + (height - 1) / 2.0))
            ys, xs = slice(max(py - ext, 0), min(py + ext + 1, height)), slice(max(px - ext, 0), min(px + ext + 1, width))
            if ys.start >= ys.stop or xs.start >= xs.stop:
                continue
            local = np.sqrt((x[ys, xs] - cx) ** 2 + (y[ys, xs] - cy) ** 2) - r
            dc[ys, xs] = np.minimum(dc[ys, xs], local)
        d = np.maximum(d - r * 0.35, -dc)  # the bumps eat into the window
    return d


def render_frame(image, style="rounded", margin=28, corner_radius=36, line_width=4, line_gap=10,
                 frame_color="#FFFBF2", accent_color="#E8A0AE", corner_motif="none", deco_size=44,
                 roundness=0.8):
    """image (H, W, 3) float in [0, 1] -> (framed image, frame coverage (H, W))."""
    h, w = image.shape[:2]
    bump = max(float(deco_size) * 0.6, 8.0)
    d = window_sd(w, h, margin, corner_radius, style, bump,
                  reach=line_gap + 3.5 * line_width + 4 + float(deco_size))
    band = _aa(-d)  # 1 on the frame
    lines = np.zeros_like(band)
    if style != "plain" and line_width > 0:
        offsets = [line_gap] if style != "double_line" else [line_gap, line_gap + 2.5 * line_width]
        for off in offsets:
            lines = np.maximum(lines, _aa(np.abs(d + off + line_width / 2.0) - line_width / 2.0))
    motifs = np.zeros_like(band)
    if corner_motif != "none":
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        c = max(float(margin), deco_size * 0.55)  # on the window corner, like a sticker
        for cx, cy in ((c, c), (w - 1 - c, c), (c, h - 1 - c), (w - 1 - c, h - 1 - c)):
            dx, dy = x - cx, y - cy
            if corner_motif == "dots":
                sd = np.sqrt(dx * dx + dy * dy) - deco_size * 0.35
            else:
                sd = _motif_sd(corner_motif, dx, dy, float(deco_size), roundness)
            motifs = np.maximum(motifs, _aa(sd))
    fc, ac = parse_color(frame_color), parse_color(accent_color)
    out = image.astype(np.float32) * (1 - band[..., None]) + fc * band[..., None]
    deco = np.maximum(lines, motifs)
    out = out * (1 - deco[..., None]) + ac * deco[..., None]
    return np.clip(out, 0.0, 1.0), np.maximum(band, deco)


def random_frame(seed):
    """Style and corner motif picked from `seed` (sizes stay as set on the node)."""
    rng = random.Random(seed ^ 0x5F3759DF)  # not the same draw as the background with the same seed
    return dict(style=rng.choice(["rounded", "double_line", "scallop"]),
                corner_motif=rng.choice(["none", "hearts", "stars", "dots"]))


def colors_from_palette(palette):
    """Frame and accent colors that match a background picked by Pattern Background: a light base that is not
    the background itself, and the pattern color pulled a little toward the palette's deep color."""
    bg = palette.get("background")
    bases = [b for b in palette.get("base", []) if b != bg] or ["#FFFBF2"]
    fc = bases[0]
    a = parse_color(palette["color"]) * 0.65 + parse_color(palette["accent"]) * 0.35
    return fc, "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in a)

