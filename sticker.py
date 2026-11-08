"""Sticker border around a cut-out character (plain numpy, testable alone).

The character's mask is grown by `width` px into a round-cornered "paper" shape, like a die-cut sticker, and
an optional thin outline is drawn around the paper. Distances are Euclidean (round corners, no blocky steps).
  - Image edges: the mask is extended past the image edges before growing, so a body cut off by the bottom
    edge gets no border line along that edge; only the sides of the border run out of the picture.
  - Closed gaps: after growing, background left enclosed by the paper (inside a ribbon loop, between the ankles,
    between an arm and the body). `fill_holes` none = keep them as windows (with the border and outline inside),
    small = fill the narrow ones (no point farther than `width` from the paper), all = fill every one.
"""

import numpy as np

try:
    from .pattern import parse_color
except ImportError:  # imported alone (tests)
    from pattern import parse_color

FILL_HOLES = ["small", "none", "all"]


def _shift(a, d, axis, fill):
    """a shifted by d along axis, filling the gap with `fill`."""
    out = np.full_like(a, fill)
    n = a.shape[axis]
    if abs(d) >= n:
        return out
    src = [slice(None)] * a.ndim
    dst = [slice(None)] * a.ndim
    if d > 0:
        src[axis], dst[axis] = slice(0, n - d), slice(d, n)
    else:
        src[axis], dst[axis] = slice(-d, n), slice(0, n + d)
    out[tuple(dst)] = a[tuple(src)]
    return out


def distance_to(fg, reach):
    """Euclidean distance (H, W) from each pixel center to the nearest `fg` pixel center, exact up to `reach`
    px (farther pixels get a value > reach)."""
    h, w = fg.shape
    big = float(reach + 1)
    # vertical distance to the nearest fg pixel in the same column (two sweeps)
    g = np.where(fg, 0.0, big).astype(np.float32)
    for y in range(1, h):
        np.minimum(g[y], g[y - 1] + 1.0, out=g[y])
    for y in range(h - 2, -1, -1):
        np.minimum(g[y], g[y + 1] + 1.0, out=g[y])
    np.minimum(g, big, out=g)
    # then along rows: min over horizontal offsets d of d^2 + g^2 (only offsets up to reach can matter)
    g2 = g * g
    d2 = g2.copy()
    inf = np.float32(big * big)
    for d in range(1, int(np.ceil(reach)) + 1):
        dd = np.float32(d * d)
        if dd > inf:
            break
        np.minimum(d2, _shift(g2, d, 1, inf) + dd, out=d2)
        np.minimum(d2, _shift(g2, -d, 1, inf) + dd, out=d2)
    return np.sqrt(d2)


def _segments(mask):
    """Run ids along rows for True pixels (0 = not in mask)."""
    prev = np.zeros_like(mask)
    prev[:, 1:] = mask[:, :-1]
    start = mask & ~prev
    ids = np.cumsum(start.ravel()).reshape(mask.shape)
    return np.where(mask, ids, 0)


def _spread_any(region, seeds):
    """Pixels of `region` connected (4-neighbors) to `seeds`: whole row / column runs are filled at once,
    alternating directions until nothing changes."""
    reached = seeds & region
    while True:
        before = int(reached.sum())
        for t in (False, True):
            r, s = (region.T, reached.T) if t else (region, reached)
            ids = _segments(r)
            hit = np.bincount(ids[s], minlength=int(ids.max()) + 1) > 0
            hit[0] = False
            new = hit[ids]
            reached = new.T if t else new
        if int(reached.sum()) == before:
            return reached


def _label(region):
    """Connected components (4-neighbors) of `region`: (H, W) int labels, 0 outside."""
    lab = np.zeros(region.shape, np.int64)
    rest = region.copy()
    n = 0
    while rest.any():
        n += 1
        y, x = np.argwhere(rest)[0]
        seed = np.zeros_like(rest)
        seed[y, x] = True
        comp = _spread_any(rest, seed)
        lab[comp] = n
        rest &= ~comp
    return lab, n


def closed_gaps(fg):
    """Background pixels not connected to the image edge."""
    bg = ~fg
    edge = np.zeros_like(bg)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    return bg & ~_spread_any(bg, edge)


def fill_gaps(paper, mode, width):
    """paper (bool) with its closed gaps filled by `mode` (none / small / all). small: a gap is filled when no
    pixel of it is farther than `width` px from the paper (a narrow window)."""
    if mode == "none":
        return paper
    holes = closed_gaps(paper)
    if mode == "all" or not holes.any():
        return paper | holes
    lab, n = _label(holes)
    d = distance_to(paper, width + 2)
    far = np.zeros(n + 1)
    np.maximum.at(far, lab[holes], d[holes])
    small = far <= width
    small[0] = False
    return paper | small[lab]


def _aa(signed_dist):
    return np.clip(0.5 - signed_dist, 0.0, 1.0)


def padding(width, outline_width=0, smooth=0.5):
    """Margin in px added on each side while growing the mask (the work area is the image plus this)."""
    reach = width + outline_width + max(float(smooth), 0.0) * width + 2
    return int(np.ceil(reach)) + 1


def sticker_layers(mask, width, outline_width=0, fill_holes="small", smooth=0.5, extend_edges=True):
    """mask (H, W) in [0, 1] -> (paper coverage, outline coverage), each (H, W) float32.
    paper covers the character and the border; outline is the thin ring outside the paper.
    smooth: rounds the inside corners of the paper (between arm and body etc.), as a share of the width.
    extend_edges: False treats outside the image as background (only for comparison)."""
    h, w = mask.shape
    fg = mask > 0.5
    if not fg.any():
        z = np.zeros((h, w), np.float32)
        return z, z
    r = max(float(smooth), 0.0) * width  # closing radius
    outer = width + outline_width
    reach = outer + r + 2
    pad = padding(width, outline_width, smooth)
    # extend the mask past the edges, so a body cut off by the frame continues outside it
    fgp = np.pad(fg, pad, mode="edge" if extend_edges else "constant")
    d = distance_to(fgp, reach)

    def shape(t):
        """Coverage of the mask grown by t px, inside corners rounded by r (dilate by t+r, erode by r)."""
        if t <= 0:
            return np.zeros_like(d)
        if r <= 0:
            return _aa(d - 0.5 - t)
        grown = d <= t + r
        din = distance_to(~grown, r + 2)  # distance from inside the grown shape to its outside
        return _aa(r + 0.5 - din)

    paper = np.maximum(shape(width), fgp.astype(np.float32))
    solid = paper > 0.5
    added = fill_gaps(solid, fill_holes, width) & ~solid
    if added.any():
        # also cover the soft edge pixels around a filled gap, or a faint seam shows where the window was
        paper = np.where(distance_to(added, 3) <= 2.0, 1.0, paper)
    ring = np.clip(shape(outer) - paper, 0.0, 1.0) if outline_width > 0 else np.zeros_like(paper)
    crop = (slice(pad, pad + h), slice(pad, pad + w))
    return paper[crop].astype(np.float32), ring[crop].astype(np.float32)


def render_sticker(image, mask, width=24, color="#FFFFFF", outline_width=0, outline_color="#E8A0AE",
                   fill_holes="small", smooth=0.5, extend_edges=True):
    """image (H, W, 3), mask (H, W) -> (sticker image (H, W, 3), sticker mask (H, W)).
    The character is laid on the paper; outside the sticker mask the image is the paper color (unused when the
    sticker is composited with its mask)."""
    m = np.clip(mask.astype(np.float32), 0.0, 1.0)
    paper, ring = sticker_layers(m, width, outline_width, fill_holes, smooth, extend_edges)
    pc, oc = parse_color(color), parse_color(outline_color)
    base = pc * (1 - ring[..., None]) + oc * ring[..., None]
    out = image.astype(np.float32) * m[..., None] + base * (1 - m[..., None])
    alpha = np.maximum(np.maximum(paper, ring), m)
    return np.clip(out, 0.0, 1.0), alpha


COLOR_MODES = ["manual", "from_palette", "from_character"]
# HLS lightness / saturation of the colors taken from the character: paper nearly white, outline mid-tone
PAPER_LS = (0.95, 0.45)
OUTLINE_LS = (0.60, 0.45)


def pick_color(mode, manual, which, palette=None, character=None):
    """Paper (which='paper') or outline (which='outline') color for a color mode.
    from_palette: the frame colors Pattern Frame would use (a light base / the pattern color pulled deeper).
    from_character: the character's main hue (see charcolor), pale for the paper, mid-tone for the outline.
    Falls back to `manual` when there is nothing to take the color from."""
    if mode == "from_palette":
        if palette is None:
            raise ValueError("color mode from_palette: connect palette from Pattern Background")
        try:
            from .frame import colors_from_palette
        except ImportError:
            from frame import colors_from_palette
        fc, ac = colors_from_palette(palette)
        return fc if which == "paper" else ac
    if mode == "from_character":
        main = (character or {}).get("main")
        if main is None:
            return manual
        try:
            from .charcolor import _hls_hex
        except ImportError:
            from charcolor import _hls_hex
        return _hls_hex(main["hue"], *(PAPER_LS if which == "paper" else OUTLINE_LS))
    return manual
