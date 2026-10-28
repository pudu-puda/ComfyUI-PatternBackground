import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from birefnet_loader import strip_prefixes  # noqa: E402


def test_strip_toonout_prefixes():
    sd = {"module._orig_mod.bb.layers.1.blocks.0.attn.relative_position_index": 1, "bb.x": 2,
          "_orig_mod.module.decoder.y": 3}
    assert strip_prefixes(sd) == {"bb.layers.1.blocks.0.attn.relative_position_index": 1, "bb.x": 2,
                                  "decoder.y": 3}
