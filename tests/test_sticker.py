import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sticker as S  # noqa: E402


def disk(h, w, cy, cx, r):
    y, x = np.mgrid[0:h, 0:w]
    return ((y - cy) ** 2 + (x - cx) ** 2 <= r * r).astype(np.float32)


def test_distance_is_euclidean():
    fg = np.zeros((41, 41), bool)
    fg[20, 20] = True
    d = S.distance_to(fg, 30)
    assert d[20, 20] == 0 and abs(d[20, 35] - 15) < 1e-5 and abs(d[30, 30] - np.hypot(10, 10)) < 1e-4


def test_border_width_and_outline():
    m = disk(200, 200, 100, 100, 30)
    paper, ring = S.sticker_layers(m, 10, outline_width=4, smooth=0)
    row = paper[100]
    assert row[100 + 30 + 8] > 0.99 and row[100 + 30 + 13] < 0.01  # border ends about 10 px outside
    assert ring[100, 100 + 30 + 12] > 0.99 and ring[100, 100] == 0  # outline just outside the border
    assert ring[100, 100 + 30 + 18] < 0.01


def test_no_border_line_along_the_image_edge():
    m = np.zeros((100, 120), np.float32)
    m[60:, 40:80] = 1.0  # a body cut off by the bottom edge
    paper, _ = S.sticker_layers(m, 8, smooth=0)
    assert paper[99, 20].max() < 0.01  # beside the body at the bottom edge: no border running along the edge
    assert paper[99, 35] > 0.99  # the side border reaches the edge


@pytest.mark.parametrize("mode,filled", [("none", False), ("all", True)])
def test_fill_holes_modes(mode, filled):
    m = disk(200, 200, 100, 100, 60) - disk(200, 200, 100, 100, 30)  # a ring with a big closed gap
    paper, _ = S.sticker_layers(m, 6, fill_holes=mode, smooth=0)
    assert (paper[100, 100] > 0.99) == filled


def test_fill_holes_small_fills_only_narrow_gaps():
    m = np.ones((120, 200), np.float32)
    m[:5] = m[-5:] = 0  # background touching the edge, so the rest is not a hole
    m[50:56, 30:50] = 0  # narrow gap: 6 px tall
    m[30:90, 110:170] = 0  # wide gap
    holes = S.closed_gaps(m > 0.5)
    assert holes[52, 40] and holes[60, 140] and not holes[2, 100]
    filled = S.fill_gaps(m > 0.5, "small", 10)
    assert filled[52, 40] and not filled[60, 140]


def test_render_keeps_the_character_and_white_paper():
    img = np.zeros((100, 100, 3), np.float32)
    img[..., 0] = 1.0
    m = disk(100, 100, 50, 50, 20)
    out, a = S.render_sticker(img, m, width=8)
    assert np.allclose(out[50, 50], [1, 0, 0]) and np.allclose(out[50, 75], [1, 1, 1])
    assert a[50, 75] > 0.99 and a[50, 95] == 0


def test_empty_mask():
    paper, ring = S.sticker_layers(np.zeros((10, 10), np.float32), 5, 2)
    assert paper.max() == 0 and ring.max() == 0


def test_pick_color_modes():
    assert S.pick_color("manual", "#123456", "paper") == "#123456"
    cc = {"main": {"hue": 330.0}}
    p, o = S.pick_color("from_character", "#FFFFFF", "paper", character=cc), \
        S.pick_color("from_character", "#FFFFFF", "outline", character=cc)
    assert p != o and p.startswith("#")
    assert S.pick_color("from_character", "#FFFFFF", "paper", character={"main": None}) == "#FFFFFF"
    pal = dict(background="#FFF6F0", base=["#FFF6F0", "#FDEFF4"], color="#F4A6B8", accent="#8C3B57")
    assert S.pick_color("from_palette", "#FFFFFF", "paper", palette=pal) == "#FDEFF4"
    with pytest.raises(ValueError):
        S.pick_color("from_palette", "#FFFFFF", "paper")


def test_small_fills_a_window_the_border_closes():
    # two legs touching the bottom edge, close at the feet: not a closed gap of the mask, but the border closes
    # it into a narrow window between the legs, which small fills and none keeps
    m = np.zeros((200, 200), np.float32)
    m[40:200, 50:80] = 1.0
    m[40:200, 120:150] = 1.0
    m[40:60, 50:150] = 1.0
    m[180:200, 80:96] = 1.0
    m[180:200, 104:120] = 1.0  # feet: an 8 px opening at the bottom
    assert not S.closed_gaps(m > 0.5).any()
    keep, _ = S.sticker_layers(m, 6, fill_holes="none", smooth=0)
    fill, _ = S.sticker_layers(m, 12, fill_holes="small", smooth=0)
    keep12, _ = S.sticker_layers(m, 12, fill_holes="none", smooth=0)
    assert keep[120, 100] < 0.01 and keep12[120, 100] < 0.01  # the 40 px gap stays a window
    assert fill[120, 100] > 0.99 and fill[130, 99].min() > 0.99


def test_padding_covers_the_reach_and_keeps_usual_sizes_small():
    # the margin must reach the outline and the closing radius
    assert S.padding(24, 0, 0.5) >= 24 + 12 + 2
    assert S.padding(512, 128, 2.0) >= 512 + 128 + 1024 + 2
    # the article's sizes with the default border stay far under the 4096x4096 limit
    pad = 2 * S.padding(24, 6, 0.5)
    assert (1216 + pad) * (832 + pad) < 4096 * 4096
    # the largest settings on the same image are refused by the node (work area above the limit)
    pad = 2 * S.padding(512, 128, 2.0)
    assert (1216 + pad) * (832 + pad) > 4096 * 4096
