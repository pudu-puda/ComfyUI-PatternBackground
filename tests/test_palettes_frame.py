import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import frame as F  # noqa: E402
import palettes as PL  # noqa: E402
import pattern as P  # noqa: E402


def test_palette_colors_parse():
    for name, (group, bases, colors, accent) in PL.PALETTES.items():
        assert group in PL.GROUPS
        for c in bases + colors + [accent]:
            P.parse_color(c)


@pytest.mark.parametrize("choice", [c for c in PL.PALETTE_CHOICES if c != "from_character"])
def test_randomize_is_seeded(choice):
    a = PL.randomize(7, "pattern_and_colors", choice, "dots", 1344, 704)
    b = PL.randomize(7, "pattern_and_colors", choice, "dots", 1344, 704)
    assert a == b
    assert a["pattern"] in P.PATTERNS
    P.render(a["pattern"], 64, 64, a["color"], a["background"])


def test_randomize_varies_with_seed():
    picks = {tuple(sorted(PL.randomize(s, "pattern_and_colors", "any", "dots", 1344, 704).items(), key=str)).__repr__()
             for s in range(20)}
    assert len(picks) > 10


def test_colors_mode_keeps_the_pattern():
    r = PL.randomize(3, "colors", "pastel", "stars", 800, 600)
    assert r["pattern"] == "stars" and "spacing" not in r
    assert r["name"] in PL.palette_names("pastel")


def test_random_patterns_skip_solid_and_focus_lines():
    pats = {PL.randomize(s, "pattern_and_colors", "any", "dots", 1344, 704)["pattern"] for s in range(200)}
    assert "solid" not in pats and "focus_lines" not in pats
    assert pats == set(PL.RANDOM_PATTERNS)


def test_palette_backgrounds_are_light():
    for _, (_, bases, _, _) in PL.PALETTES.items():
        for b in bases:
            assert PL._lightness(b) > 0.88


@pytest.mark.parametrize("style", F.STYLES)
@pytest.mark.parametrize("motif", F.CORNER_MOTIFS)
def test_frame_keeps_size_and_center(style, motif):
    img = np.full((200, 300, 3), 0.25, np.float32)
    out, mask = F.render_frame(img, style=style, margin=20, corner_motif=motif, deco_size=24)
    assert out.shape == img.shape and mask.shape == (200, 300)
    assert np.allclose(out[100, 150], 0.25) and mask[100, 150] == 0.0  # the middle is untouched
    assert mask[0, 0] > 0.99  # the corner is frame


def test_frame_margin_too_large():
    with pytest.raises(ValueError):
        F.render_frame(np.zeros((40, 40, 3), np.float32), margin=30)


def test_frame_colors_from_palette():
    pal = PL.randomize(1, "colors", "muted", "dots", 640, 480)
    fc, ac = F.colors_from_palette(pal)
    P.parse_color(fc), P.parse_color(ac)
    assert fc != pal["background"] or len(pal["base"]) == 1


def _figure(main_rgb, accent_rgb=None):
    """A grey-haired, pale-skinned figure on white with a colored dress (and a small colored prop)."""
    img = np.ones((200, 200, 3), np.float32)
    mask = np.zeros((200, 200), np.float32)
    img[20:70, 60:140] = [0.80, 0.79, 0.79]  # grey hair
    img[70:100, 70:130] = [1.0, 0.93, 0.92]  # pale skin
    img[100:190, 50:150] = main_rgb  # dress
    if accent_rgb is not None:
        img[120:150, 150:180] = accent_rgb  # prop
    mask[20:190, 50:180] = 1
    return img, mask


def test_character_colors_finds_dress_and_prop():
    import charcolor as C
    img, mask = _figure([0.83, 0.70, 0.71], [0.2, 0.7, 0.4])  # dusty pink dress, green prop
    cc = C.character_colors(img, mask)
    assert abs((cc["main"]["hue"] - 357 + 180) % 360 - 180) < 10
    assert 130 < cc["accent"]["hue"] < 160


def test_character_without_color_falls_back():
    import charcolor as C
    img, mask = _figure([0.5, 0.5, 0.5])
    cc = C.character_colors(img, mask)
    assert cc["main"] is None
    assert C.colors_for(cc)["harmony"] == "none"


@pytest.mark.parametrize("harmony", ["same", "neighbor", "complement", "accent", "auto"])
def test_from_character_harmonies(harmony):
    import charcolor as C
    img, mask = _figure([0.95, 0.80, 0.30], [0.85, 0.2, 0.25])  # yellow vest, red straw
    cc = C.character_colors(img, mask)
    r = PL.randomize(5, "colors", "from_character", "dots", 200, 200, cc, harmony)
    assert r == PL.randomize(5, "colors", "from_character", "dots", 200, 200, cc, harmony)
    assert PL._lightness(r["background"]) > 0.9 > PL._lightness(r["color"])
    if harmony == "complement":  # yellow -> blue-ish
        h = PL.colorsys.rgb_to_hls(*P.parse_color(r["color"]))[0] * 360
        assert 190 < h < 260


def test_from_character_needs_the_character():
    with pytest.raises(ValueError):
        PL.randomize(1, "colors", "from_character", "dots", 64, 64)


def test_scallop_local_matches_full():
    # bumps computed only near each bump give the same frame as computing them over the whole image
    d_local = F.window_sd(500, 300, 24, 36, "scallop", 24.0, reach=40)
    d_wide = F.window_sd(500, 300, 24, 36, "scallop", 24.0, reach=10_000)
    near = d_wide > -40  # where the frame and its lines are drawn
    assert np.allclose(d_local[near], d_wide[near], atol=1e-4)


def test_scallop_large_image_is_quick():
    import time
    t = time.time()
    F.window_sd(4096, 4096, 40, 36, "scallop", 30.0, reach=40)
    assert time.time() - t < 10


def test_scallop_extreme_settings_are_bounded():
    import time
    t = time.time()
    F.render_frame(np.zeros((1024, 1024, 3), np.float32), style="scallop", margin=40, line_gap=512, line_width=256,
                   deco_size=4)
    assert time.time() - t < 20


def test_scallop_corners_match_and_nothing_outside():
    # the four corners are the same shape, and the window never reaches past the straight frame edge
    d = F.window_sd(832, 1216, 28, 36, "scallop", 40.0, reach=64)
    near = np.maximum(d, -40.0)  # bumps are computed only near the edge (see test_scallop_local_matches_full)
    assert np.allclose(near, near[::-1, :], atol=1e-3) and np.allclose(near, near[:, ::-1], atol=1e-3)
    assert (d[:28, :] > 0).all() and (d[:, :28] > 0).all()


@pytest.mark.parametrize("w,h,deco", [(512, 512, 256), (1344, 704, 1024), (200, 200, 44)])
def test_scallop_huge_bumps_keep_the_window(w, h, deco):
    _, mask = F.render_frame(np.zeros((h, w, 3), np.float32), style="scallop", margin=8, deco_size=deco)
    assert (mask < 0.5).mean() > 0.4
