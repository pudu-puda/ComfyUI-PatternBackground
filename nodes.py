import numpy as np
import torch

from .birefnet_loader import LoadBiRefNetCheckpoint
from .pattern import PATTERNS, render

MAX_SIZE = 16384


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
                                    "tooltip": "Repeat interval in px (dots, stripes, grid, gingham, checkerboard)."}),
                "thickness": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01,
                                        "tooltip": "Size relative to spacing: dot diameter, stripe/line width. "
                                                   "For focus_lines, line width."}),
                "angle": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 1.0,
                                    "tooltip": "Rotation in degrees (e.g. 45 for diagonal stripes)."}),
                "stagger": ("BOOLEAN", {"default": True, "tooltip": "dots: offset every other row."}),
                "lines": ("INT", {"default": 120, "min": 4, "max": 2000, "tooltip": "focus_lines: number of lines."}),
                "inner_radius": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01,
                                           "tooltip": "focus_lines: size of the empty center."}),
                "center_x": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "center_y": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF, "tooltip": "focus_lines: randomness."}),
            },
            "optional": {
                "size_from": ("IMAGE", {"tooltip": "If connected, width and height are taken from this image."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "pattern_mask")
    FUNCTION = "generate"
    CATEGORY = "image/pattern"
    DESCRIPTION = "Flat pattern background: solid, dots, stripes, grid, gingham, checkerboard, focus lines."

    def generate(self, pattern, width, height, color, background, spacing, thickness, angle, stagger,
                 lines, inner_radius, center_x, center_y, seed, size_from=None):
        if size_from is not None:
            height, width = int(size_from.shape[1]), int(size_from.shape[2])
        img, cov = render(pattern, width, height, color, background, spacing=spacing, thickness=thickness,
                          angle=angle, stagger=stagger, lines=lines, inner_radius=inner_radius,
                          center_x=center_x, center_y=center_y, seed=seed)
        image = torch.from_numpy(np.ascontiguousarray(img, dtype=np.float32))[None]
        mask = torch.from_numpy(np.ascontiguousarray(cov, dtype=np.float32))[None]
        return (image, mask)


NODE_CLASS_MAPPINGS = {"PatternBackground": PatternBackground, "LoadBiRefNetCheckpoint": LoadBiRefNetCheckpoint}
NODE_DISPLAY_NAME_MAPPINGS = {"PatternBackground": "Pattern Background",
                              "LoadBiRefNetCheckpoint": "Load BiRefNet Checkpoint (ToonOut etc.)"}
