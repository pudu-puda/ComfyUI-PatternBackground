"""Background colors derived from the character's own colors (plain numpy, testable alone).

1. Take the character's pixels (mask > 0.5) and drop the ones with little color: greys (hair, outlines),
   white, black and pale skin (brighter than the clothes). What is left is the clothes and props.
2. Group them by hue (12 bins of 30 degrees, by area). The biggest group is the main color,
   a smaller but clearly different group (45+ degrees away) is the accent.
3. Make two background colors from one of the harmonies below, always light and soft so the character
   stays in front:
     same          the main color's hue, pale (unity)
     neighbor      a hue 30 degrees to either side of the main color, pale (unity with a little change)
     complement    the hue opposite the main color, pale (the character stands out)
     accent        the accent color for the pattern on a pale tint of the main color (ties props to the background)
"""

import colorsys
import random

import numpy as np

HARMONIES = ["auto", "same", "neighbor", "complement", "accent"]
# lightness / saturation (HLS) of the two background colors: pattern a little deeper, base nearly white
PATTERN_LS = (0.80, 0.50)
BASE_LS = (0.955, 0.45)


def _rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rc = np.where(nz, (mx - r) / np.maximum(d, 1e-6), 0)
    gc = np.where(nz, (mx - g) / np.maximum(d, 1e-6), 0)
    bc = np.where(nz, (mx - b) / np.maximum(d, 1e-6), 0)
    h = np.where(r == mx, bc - gc, np.where(g == mx, 2.0 + rc - bc, 4.0 + gc - rc))
    h = np.mod(h / 6.0, 1.0) * 360.0
    return np.where(nz, h, 0.0), s, mx


def character_colors(image, mask, min_share=0.03):
    """image (H, W, 3) in [0, 1], mask (H, W) -> dict(main=(hue, sat, val, share), accent=... or None,
    colored_share). Hue in degrees."""
    m = mask > 0.5
    px = image[m]
    if len(px) == 0:
        raise ValueError("the mask is empty")
    h, s, v = _rgb_to_hsv(px)
    colored = (s > 0.12) & (v > 0.3)
    # pale skin and blush: brighter than muted clothes, a little pink / orange, not very saturated
    skin = (v > 0.9) & (s < 0.3) & ((h < 40) | (h > 330))
    keep = colored & ~skin
    out = dict(colored_share=float(keep.mean()), main=None, accent=None)
    if keep.sum() < 50:
        return out
    h, s, v = h[keep], s[keep], v[keep]
    bins = (h // 30).astype(int) % 12
    weight = np.bincount(bins, minlength=12).astype(np.float64)
    total = weight.sum()

    def summary(b):
        sel = bins == b
        # circular mean of the hue inside the bin
        ang = np.deg2rad(h[sel])
        hue = float(np.rad2deg(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360)
        return dict(hue=hue, sat=float(np.median(s[sel])), val=float(np.median(v[sel])),
                    share=float(weight[b] / total))

    order = np.argsort(-weight)
    main = summary(order[0])
    out["main"] = main
    for b in order[1:]:
        if weight[b] / total < min_share:
            break
        cand = summary(b)
        dh = abs((cand["hue"] - main["hue"] + 180) % 360 - 180)
        if dh >= 45:
            out["accent"] = cand
            break
    return out


def _hls_hex(hue, light, sat):
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0, light, sat)
    return "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in (r, g, b))


def colors_for(cc, harmony="auto", seed=0):
    """-> dict(harmony, color, background, base, colors, accent) like a palette. Falls back to a soft neutral
    pair when the character has almost no color."""
    rng = random.Random(seed)
    main, acc = cc.get("main"), cc.get("accent")
    if main is None:
        return dict(name="character:none", harmony="none", color="#D9D2C5", background="#FAF7F2",
                    base=["#FAF7F2"], colors=["#D9D2C5"], accent="#6B6257")
    if harmony == "auto":
        harmony = rng.choice(["same", "neighbor", "complement", "accent"] if acc else
                             ["same", "neighbor", "complement"])
    if harmony == "accent" and acc is None:
        harmony = "complement"
    if harmony == "same":
        hue_p = hue_b = main["hue"]
    elif harmony == "neighbor":
        hue_p = hue_b = main["hue"] + rng.choice([-30, 30])
    elif harmony == "complement":
        hue_p = hue_b = main["hue"] + 180
    else:  # accent
        hue_p, hue_b = acc["hue"], main["hue"]
    # a little variation by seed, so one character does not always get the very same two colors
    jitter = rng.uniform(-10, 10)
    hue_p, hue_b = hue_p + jitter, hue_b + jitter
    light = PATTERN_LS[0] + rng.uniform(-0.05, 0.03)
    color = _hls_hex(hue_p, light, PATTERN_LS[1])
    background = _hls_hex(hue_b, *BASE_LS)
    deep = _hls_hex(hue_p, 0.35, 0.40)
    return dict(name=f"character:{harmony}", harmony=harmony, color=color, background=background,
                base=[background, _hls_hex(hue_b + 30, *BASE_LS)], colors=[color], accent=deep)
