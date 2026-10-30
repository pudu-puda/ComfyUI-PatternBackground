import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pattern as P  # noqa: E402


@pytest.mark.parametrize("name", P.PATTERNS)
def test_shape_and_range(name):
    img, cov = P.render(name, 200, 120, "#ff0000", "#0000ff")
    assert img.shape == (120, 200, 3) and cov.shape == (120, 200)
    assert img.dtype == np.float32
    assert 0.0 <= img.min() and img.max() <= 1.0


def test_solid_is_background():
    img, _ = P.render("solid", 16, 16, "#000000", "#336699")
    assert np.allclose(img, P.parse_color("#336699"))


@pytest.mark.parametrize("name", ["dots", "stripes", "grid", "gingham", "checkerboard", "focus_lines"])
def test_pattern_uses_both_colors(name):
    cov = P.coverage(name, 400, 300, spacing=40, thickness=0.4)
    assert (cov > 0.99).mean() > 0.01
    assert (cov < 0.01).mean() > 0.05


def test_stripes_coverage_matches_thickness():
    cov = P.coverage("stripes", 640, 64, spacing=64, thickness=0.25)
    assert abs(cov.mean() - 0.25) < 0.02


def test_checkerboard_is_half():
    cov = P.coverage("checkerboard", 512, 512, spacing=32)
    assert abs(cov.mean() - 0.5) < 0.02


def test_gingham_has_three_levels():
    cov = P.coverage("gingham", 512, 512, spacing=64, thickness=0.5)
    for level in (0.0, 0.5, 1.0):
        assert (np.abs(cov - level) < 0.01).mean() > 0.1


def test_focus_lines_center_is_clear_and_seeded():
    a = P.coverage("focus_lines", 400, 300, lines=80, inner_radius=0.5, seed=1)
    b = P.coverage("focus_lines", 400, 300, lines=80, inner_radius=0.5, seed=1)
    c = P.coverage("focus_lines", 400, 300, lines=80, inner_radius=0.5, seed=2)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert a[140:160, 190:210].max() == 0.0


def test_parse_color():
    assert np.allclose(P.parse_color("#fff"), [1, 1, 1])
    with pytest.raises(ValueError):
        P.parse_color("#12345")


@pytest.mark.parametrize("name", ["border", "hearts", "stars"])
def test_new_patterns_use_both_colors(name):
    cov = P.coverage(name, 400, 300, spacing=80, thickness=0.6)
    assert (cov > 0.99).mean() > 0.01
    assert (cov < 0.01).mean() > 0.05


def test_border_is_horizontal():
    cov = P.coverage("border", 64, 640, spacing=64, thickness=0.25)
    assert np.allclose(cov, cov[:, :1])  # the same along each row
    assert abs(cov.mean() - 0.25) < 0.02


@pytest.mark.parametrize("name", ["hearts", "stars"])
def test_roundness_rounds_the_tips(name):
    # rounding cuts the sharp tips, so a little less area is covered at the same size
    sharp = P.coverage(name, 256, 256, spacing=128, thickness=0.7, roundness=0.0).mean()
    round_ = P.coverage(name, 256, 256, spacing=128, thickness=0.7, roundness=1.0).mean()
    assert sharp > 0.05 and round_ > 0.05 and sharp != round_


def test_heart_points_down():
    dy, dx = np.mgrid[-64:64, -64:64].astype(np.float32)
    inside = P._motif_sd("hearts", dx, dy, 100.0, 0.6) < 0
    rows = inside.sum(1)
    filled = np.nonzero(rows)[0]
    top, bottom = rows[filled[0]:filled[0] + 30], rows[filled[-1] - 10:filled[-1] + 1]
    assert top.max() > 3 * bottom.max()  # wide lobes on top, narrow tip at the bottom
