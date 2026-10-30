"""Color palettes and the random picker for Pattern Background (plain Python + numpy, testable alone).

A palette has light `base` colors (for the background), mid `colors` (for the pattern) and one dark `accent`.
The groups follow what cute-palette collections tend to do: one cream / off-white, two or three mid tones of
similar softness, one deep color to tie them together. Greys close to the character's hair, skin-like beiges
and pure white / black are left out of the bases so the character does not sink into the background.
"""

import colorsys
import random

try:
    from .charcolor import colors_for
    from .pattern import parse_color
except ImportError:  # imported alone (tests)
    from charcolor import colors_for
    from pattern import parse_color

PALETTES = {
    # muted (kusumi): low saturation, mid-light, like matte photo-magazine thumbnails
    "sage": ("muted", ["#F3F1EA", "#EEF0E6"], ["#9DB491", "#86A08E", "#C2AE84"], "#4E5D52"),
    "mauve": ("muted", ["#F5F0F2", "#F3EEEA"], ["#B996B0", "#CC9C96", "#A096BC"], "#5B4A5E"),
    "teal_mustard": ("muted", ["#F4F1E8", "#EEF3F2"], ["#76A39F", "#D2B46C", "#8CAFB9"], "#2F4F55"),
    "dusty_blue": ("muted", ["#EFF2F5", "#F4F1EC"], ["#8CA2BE", "#A9B9CC", "#C9AE8E"], "#34445A"),
    # pastel: light and a little sweeter
    "strawberry_milk": ("pastel", ["#FFF6F3", "#FFF9EE"], ["#F4B6C2", "#F7C9B6", "#F6DE9E"], "#B24D63"),
    "soda": ("pastel", ["#F2F9FF", "#FFFCEF"], ["#A9D4F5", "#B9E3DA", "#F8E19A"], "#3D6C9A"),
    "lavender": ("pastel", ["#F8F4FF", "#FFF5FA"], ["#CDBDF0", "#F3C4DC", "#BFD8F2"], "#5E4D8C"),
    "mint_lemon": ("pastel", ["#F5FBF4", "#FFFBEA"], ["#B5E2C8", "#F4E39A", "#C8E4EF"], "#3F7A62"),
    # retro: warmer and bolder, still on a cream base
    "retro_pop": ("retro", ["#FBF4E4"], ["#E8896B", "#F2C46D", "#8DB7C9"], "#2F4A6D"),
    "cream_cherry": ("retro", ["#FBF3E6"], ["#D4707A", "#8FA9D9", "#EBCF95"], "#3B3A5A"),
    "olive_sky": ("retro", ["#F7F0DC"], ["#A9AE6C", "#96B4D0", "#D08B66"], "#4A3B2A"),
    "blue_yellow": ("retro", ["#FFFBEF", "#F3F8FD"], ["#7FB2E5", "#F2CF5B", "#A8CFEF"], "#23477A"),
}
GROUPS = ["muted", "pastel", "retro"]
# what the `palette` input offers: any / a group / one palette / colors taken from the character /
# no palette (uniform RGB, for comparison)
PALETTE_CHOICES = ["any"] + GROUPS + list(PALETTES) + ["from_character", "random_rgb"]
RANDOMIZE = ["off", "colors", "pattern_and_colors"]
RANDOM_PATTERNS = ["dots", "stripes", "border", "grid", "gingham", "checkerboard", "hearts", "stars"]

# Ranges each pattern looks good in, for a 704 px short side (scaled to the image). Angle is picked from a list.
RANGES = {
    "dots": dict(spacing=(40, 72), thickness=(0.3, 0.5), angle=[0]),
    "stripes": dict(spacing=(32, 64), thickness=(0.3, 0.5), angle=[0, 45, -45]),
    "border": dict(spacing=(32, 64), thickness=(0.35, 0.5), angle=[0]),
    "grid": dict(spacing=(36, 64), thickness=(0.05, 0.1), angle=[0]),
    "gingham": dict(spacing=(40, 72), thickness=(0.5, 0.5), angle=[0, 45]),
    "checkerboard": dict(spacing=(36, 60), thickness=(0.5, 0.5), angle=[0, 45]),
    "hearts": dict(spacing=(64, 104), thickness=(0.45, 0.6), angle=[0]),
    "stars": dict(spacing=(64, 104), thickness=(0.5, 0.65), angle=[0]),
}


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in rgb)


def _mix(a, b, t):
    """Mix two #RRGGBB colors (t = 0 -> a, 1 -> b)."""
    return _hex(parse_color(a) * (1 - t) + parse_color(b) * t)


def _lightness(c):
    return colorsys.rgb_to_hls(*parse_color(c))[1]


def palette_names(choice):
    if choice == "any":
        return list(PALETTES)
    if choice in GROUPS:
        return [n for n, p in PALETTES.items() if p[0] == choice]
    if choice in PALETTES:
        return [choice]
    raise ValueError(f"unknown palette: {choice!r}")


def pick_colors(rng, choice, character=None, harmony="auto"):
    """-> dict(name, color, background, base, colors, accent). Same rng state -> same colors.
    `character` = charcolor.character_colors(...) result, used when choice is from_character."""
    if choice == "from_character":
        if character is None:
            raise ValueError("palette from_character needs the character image (size_from) and its mask")
        return colors_for(character, harmony, rng.randrange(1 << 30))
    if choice == "random_rgb":
        fg = _hex([rng.random() for _ in range(3)])
        bg = _hex([rng.random() for _ in range(3)])
        others = [_hex([rng.random() for _ in range(3)]) for _ in range(2)]
        return dict(name="random_rgb", color=fg, background=bg, base=[bg], colors=[fg] + others, accent=others[0])
    name = rng.choice(palette_names(choice))
    _, bases, colors, accent = PALETTES[name]
    fg = rng.choice(colors)
    if rng.random() < 0.3 and len(colors) > 1:
        # a pale tint of another palette color as the background, for some variety
        bg = _mix(rng.choice([c for c in colors if c != fg]), "#FFFFFF", 0.78)
    else:
        bg = rng.choice(bases)
    if abs(_lightness(fg) - _lightness(bg)) < 0.08:  # too close to read as a pattern
        bg = bases[0]
    return dict(name=name, color=fg, background=bg, base=list(bases), colors=list(colors), accent=accent)


def randomize(seed, mode, palette, pattern, width, height, character=None, harmony="auto"):
    """Pick colors (and the pattern and its sizes) from `seed`. Returns the chosen settings as a dict:
    pattern, color, background, and for pattern_and_colors also spacing, thickness, angle, stagger.
    The same seed, mode, palette and image size always give the same result."""
    rng = random.Random(seed)
    out = pick_colors(rng, palette, character, harmony)
    if mode == "pattern_and_colors":
        pattern = rng.choice(RANDOM_PATTERNS)
        r = RANGES[pattern]
        scale = min(width, height) / 704.0
        out.update(spacing=max(2, int(round(rng.uniform(*r["spacing"]) * scale))),
                   thickness=round(rng.uniform(*r["thickness"]), 3),
                   angle=float(rng.choice(r["angle"])), stagger=True)
    out["pattern"] = pattern
    return out
