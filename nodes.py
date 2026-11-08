import json

import numpy as np
import torch

from .birefnet_loader import LoadBiRefNetCheckpoint
from .charcolor import HARMONIES, character_colors
from .frame import CORNER_MOTIFS, STYLES, colors_from_palette, random_frame, render_frame
from .palettes import PALETTE_CHOICES, RANDOMIZE
from .palettes import randomize as pick_random
from .pattern import PATTERNS, render
from .sticker import COLOR_MODES, FILL_HOLES, pick_color, render_sticker
from .sticker import padding as sticker_padding

MAX_SIZE = 16384
MAX_PIXELS = 4096 * 4096  # about 0.2 GB per float32 RGB image (a few are alive while drawing); larger is refused


def _check_size(width, height):
    if width * height > MAX_PIXELS:
        raise ValueError(f"{width}x{height} is too large (max {MAX_PIXELS} pixels)")


class PatternBackground:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pattern": (PATTERNS, {"default": "dots"}),
                "width": ("INT", {"default": 1344, "min": 8, "max": MAX_SIZE, "step": 8}),
                "height": ("INT", {"default": 704, "min": 8, "max": MAX_SIZE, "step": 8}),
                "color": ("STRING", {"default": "#F4A6B8", "tooltip": "Pattern color (#RRGGBB)."}),
                "background": ("STRING", {"default": "#FFF6F0", "tooltip": "Base color (#RRGGBB)."}),
                "spacing": ("INT", {"default": 64, "min": 2, "max": 4096,
                                    "tooltip": "Repeat interval in px (dots, stripes, border, grid, gingham, "
                                               "checkerboard, hearts, stars, halftone)."}),
                "thickness": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01,
                                        "tooltip": "Size relative to spacing: dot diameter, stripe/line width, "
                                                   "heart/star width. For focus_lines, line width. halftone: size of "
                                                   "the biggest dot. gradient: how much leans to the pattern "
                                                   "color (0.5 = even)."}),
                "angle": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 1.0,
                                    "tooltip": "Rotation in degrees (e.g. 45 for diagonal stripes). "
                                               "gradient, halftone: direction of the change (0 = left to "
                                               "right, 90 = top to bottom)."}),
                "stagger": ("BOOLEAN", {"default": True,
                                        "tooltip": "dots, hearts, stars: offset every other row."}),
                "lines": ("INT", {"default": 120, "min": 4, "max": 2000, "tooltip": "focus_lines: number of lines."}),
                "inner_radius": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01,
                                           "tooltip": "focus_lines: size of the empty center."}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF,
                                 "tooltip": "focus_lines: randomness. With randomize on: what gets picked."}),
            },
            "optional": {
                "size_from": ("IMAGE", {"tooltip": "If connected, width and height are taken from this image."}),
                # added in 1.1; optional with defaults, so workflows saved with 1.0 keep their result
                "roundness": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05,
                                        "tooltip": "hearts, stars: 0 = the sharp mathematical shape, "
                                                   "1 = round tips and dips."}),
                "randomize": (RANDOMIZE, {"default": "off",
                                          "tooltip": "colors: pick the two colors from the palette by seed. "
                                                     "pattern_and_colors: also the pattern, spacing, thickness "
                                                     "and angle (within ranges that look good)."}),
                "palette": (PALETTE_CHOICES, {"default": "any",
                                              "tooltip": "Where random colors come from: any palette, a group "
                                                         "(muted / pastel / retro), one palette, from_character "
                                                         "(made from the colors of the size_from image), or "
                                                         "random_rgb (no palette at all)."}),
                "harmony": (HARMONIES, {"default": "auto",
                                        "tooltip": "from_character: same = the character's main color, pale; "
                                                   "complement = the opposite hue, pale; accent = the "
                                                   "character's second color as the pattern; auto = by seed."}),
                "subject_mask": ("MASK", {"tooltip": "from_character: the character's mask (e.g. Remove "
                                                     "Background). Without it, near-white pixels are skipped."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "PATTERN_PALETTE", "STRING")
    RETURN_NAMES = ("image", "pattern_mask", "palette", "settings")
    OUTPUT_TOOLTIPS = ("The pattern.", "Where the pattern color is.",
                       "The colors used, for Pattern Frame.", "The main settings used (shows what randomize picked).")
    FUNCTION = "generate"
    CATEGORY = "image/pattern"
    DESCRIPTION = ("Flat pattern background: solid, dots, stripes, border, grid, gingham, checkerboard, focus lines, "
                   "hearts, stars, gradient, halftone. Can pick the pattern and colors from cute palettes by seed.")

    def generate(self, pattern, width, height, color, background, spacing, thickness, angle, stagger,
                 lines, inner_radius, center_x, center_y, seed, size_from=None, roundness=0.6, randomize="off",
                 palette="any", harmony="auto", subject_mask=None):
        if size_from is not None:
            height, width = int(size_from.shape[1]), int(size_from.shape[2])
        _check_size(width, height)
        pal = dict(name="manual", color=color, background=background, base=[background], colors=[color],
                   accent=color)
        if randomize != "off":
            cc = None
            if palette == "from_character":
                cc = _character(size_from, subject_mask)
            pal = pick_random(seed, randomize, palette, pattern, width, height, cc, harmony)
            pattern, color, background = pal["pattern"], pal["color"], pal["background"]
            spacing = pal.get("spacing", spacing)
            thickness = pal.get("thickness", thickness)
            angle = pal.get("angle", angle)
            stagger = pal.get("stagger", stagger)
        img, cov = render(pattern, width, height, color, background, spacing=spacing, thickness=thickness,
                          angle=angle, stagger=stagger, lines=lines, inner_radius=inner_radius,
                          center_x=center_x, center_y=center_y, seed=seed, roundness=roundness)
        image = torch.from_numpy(np.ascontiguousarray(img, dtype=np.float32))[None]
        mask = torch.from_numpy(np.ascontiguousarray(cov, dtype=np.float32))[None]
        settings = dict(pattern=pattern, color=color, background=background, spacing=spacing,
                        thickness=thickness, angle=angle, stagger=stagger, roundness=roundness,
                        palette=pal["name"], seed=seed)
        pal = dict(pal, pattern=pattern, color=color, background=background)
        return (image, mask, pal, json.dumps(settings))


def _character(size_from, subject_mask):
    if size_from is None:
        raise ValueError("palette from_character: connect the character image to size_from")
    img = size_from[0, ..., :3].cpu().numpy()
    if subject_mask is not None:
        m = subject_mask.cpu().numpy()
        m = m[0] if m.ndim == 3 else m
    else:
        m = (img.min(-1) < 0.97).astype(np.float32)
    return character_colors(img, m)


class PatternFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "style": (STYLES, {"default": "rounded"}),
                "margin": ("INT", {"default": 28, "min": 0, "max": 2048, "tooltip": "Frame width in px."}),
                "corner_radius": ("INT", {"default": 36, "min": 0, "max": 2048,
                                          "tooltip": "Roundness of the window corners in px."}),
                "line_width": ("INT", {"default": 4, "min": 0, "max": 256, "tooltip": "Thin line inside the window."}),
                "line_gap": ("INT", {"default": 10, "min": 0, "max": 512,
                                     "tooltip": "Distance from the window edge to the line."}),
                "frame_color": ("STRING", {"default": "#FFFBF2", "tooltip": "Frame color (#RRGGBB)."}),
                "accent_color": ("STRING", {"default": "#E8A0AE",
                                            "tooltip": "Line and corner motif color (#RRGGBB)."}),
                "corner_motif": (CORNER_MOTIFS, {"default": "none"}),
                "deco_size": ("INT", {"default": 44, "min": 4, "max": 1024,
                                      "tooltip": "Corner motif size; scallop bump size."}),
                "roundness": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05,
                                        "tooltip": "Corner hearts / stars: roundness."}),
                "randomize": ("BOOLEAN", {"default": False,
                                          "tooltip": "Pick the style and corner motif by seed."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            },
            "optional": {
                "palette": ("PATTERN_PALETTE", {"tooltip": "From Pattern Background: frame and accent colors "
                                                           "are taken from it (overrides the two colors)."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "frame_mask")
    FUNCTION = "apply"
    CATEGORY = "image/pattern"
    DESCRIPTION = "Frame over the edge of an image: rounded window, double line, scallop; corner hearts / stars / dots."

    def apply(self, image, style, margin, corner_radius, line_width, line_gap, frame_color, accent_color,
              corner_motif, deco_size, roundness, randomize, seed, palette=None):
        if randomize:
            r = random_frame(seed)
            style, corner_motif = r["style"], r["corner_motif"]
        if palette is not None:
            frame_color, accent_color = colors_from_palette(palette)
        _check_size(int(image.shape[2]), int(image.shape[1]))
        outs, masks = [], []
        for img in image.cpu().numpy():
            o, m = render_frame(img[..., :3], style=style, margin=margin, corner_radius=corner_radius,
                                line_width=line_width, line_gap=line_gap, frame_color=frame_color,
                                accent_color=accent_color, corner_motif=corner_motif, deco_size=deco_size,
                                roundness=roundness)
            outs.append(o)
            masks.append(m)
        return (torch.from_numpy(np.stack(outs).astype(np.float32)),
                torch.from_numpy(np.stack(masks).astype(np.float32)))


class PatternSticker:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "The character image (before or after cutting out)."}),
                "mask": ("MASK", {"tooltip": "The character's mask (e.g. Remove Background)."}),
                "width": ("INT", {"default": 24, "min": 0, "max": 512, "tooltip": "Border width in px."}),
                "color": ("STRING", {"default": "#FFFFFF", "tooltip": "Border color (#RRGGBB), color_mode manual."}),
                "outline_width": ("INT", {"default": 0, "min": 0, "max": 128,
                                          "tooltip": "Thin line around the border in px (0 = none)."}),
                "outline_color": ("STRING", {"default": "#E8A0AE",
                                             "tooltip": "Outline color (#RRGGBB), outline_color_mode manual."}),
                "color_mode": (COLOR_MODES, {"default": "manual",
                                             "tooltip": "manual: the color above. from_palette: from Pattern "
                                                        "Background's palette. from_character: the character's "
                                                        "main color, pale."}),
                "outline_color_mode": (COLOR_MODES, {"default": "manual"}),
                "fill_holes": (FILL_HOLES, {"default": "small",
                                            "tooltip": "Closed gaps (inside a ribbon loop etc.): small = fill the "
                                                       "ones the border nearly closes, none = keep all, all = fill "
                                                       "all."}),
                "smooth": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05,
                                     "tooltip": "Rounds the inside corners of the border (share of the width)."}),
            },
            "optional": {
                "palette": ("PATTERN_PALETTE", {"tooltip": "From Pattern Background, for the from_palette modes."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    OUTPUT_TOOLTIPS = ("The character on the sticker paper.", "The sticker's shape, for ImageCompositeMasked.")
    FUNCTION = "apply"
    CATEGORY = "image/pattern"
    DESCRIPTION = ("Die-cut sticker border around a cut-out character (white by default), with an optional thin "
                   "outline. Composite it last, over the background and frame.")

    def apply(self, image, mask, width, color, outline_width, outline_color, color_mode, outline_color_mode,
              fill_holes, smooth, palette=None):
        pad = 2 * sticker_padding(width, outline_width, smooth)
        _check_size(int(image.shape[2]) + pad, int(image.shape[1]) + pad)  # the work area includes the margin
        imgs = image.cpu().numpy()[..., :3]
        masks = mask.cpu().numpy()
        masks = masks[None] if masks.ndim == 2 else masks
        if masks.shape[1:] != imgs.shape[1:3]:
            raise ValueError(f"mask size {masks.shape[1:]} does not match image size {imgs.shape[1:3]}")
        outs, alphas = [], []
        for i, img in enumerate(imgs):
            m = masks[min(i, len(masks) - 1)]
            cc = None
            if "from_character" in (color_mode, outline_color_mode):
                cc = character_colors(img, m)
            pc = pick_color(color_mode, color, "paper", palette, cc)
            oc = pick_color(outline_color_mode, outline_color, "outline", palette, cc)
            o, a = render_sticker(img, m, width=width, color=pc, outline_width=outline_width, outline_color=oc,
                                  fill_holes=fill_holes, smooth=smooth)
            outs.append(o)
            alphas.append(a)
        return (torch.from_numpy(np.stack(outs).astype(np.float32)),
                torch.from_numpy(np.stack(alphas).astype(np.float32)))


NODE_CLASS_MAPPINGS = {"PatternBackground": PatternBackground, "PatternFrame": PatternFrame,
                       "PatternSticker": PatternSticker, "LoadBiRefNetCheckpoint": LoadBiRefNetCheckpoint}
NODE_DISPLAY_NAME_MAPPINGS = {"PatternBackground": "Pattern Background", "PatternFrame": "Pattern Frame",
                              "PatternSticker": "Pattern Sticker",
                              "LoadBiRefNetCheckpoint": "Load BiRefNet Checkpoint (ToonOut etc.)"}
