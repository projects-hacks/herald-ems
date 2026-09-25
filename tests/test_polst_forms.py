"""The real-POLST form renderer: each scenario's answer follows the production `form` prompt (a clearly checked
Section A box, or nothing), and the held-out font group never appears in the training variants."""
from random import Random

import pytest

from scripts.vision_train import families
from scripts.vision_train.render_polst import FONT_DIR, FONT_GROUPS, SCENARIOS, ca_polst

EXPECTED = {"cpr_full": {"full code"}, "dnr_selective": {"DNR"}, "dnr_comfort": {"DNR"}, "dnr_full": {"DNR"},
            "crossed": {"full code", "DNR"}, "faint_readable": {"full code", "DNR"}}
EMPTY = {"only_b", "both_a", "void", "blank", "faint_unreadable"}

needs_fonts = pytest.mark.skipif(not all((FONT_DIR / f).exists() for g in FONT_GROUPS for f in g),
                                 reason="handwriting fonts not installed (docs/MODEL_PLAN.md §2a)")


@needs_fonts
@pytest.mark.parametrize("scenario", [s for s, _ in SCENARIOS])
def test_scenario_answer(scenario):
    for seed in range(3):
        panel = ca_polst(Random(f"{scenario}{seed}"), seed % 3, scenario)
        readable = [r.value for r in panel.readings if r.readable]
        if scenario in EMPTY:
            assert readable == [], scenario
        else:
            assert len(readable) == 1 and readable[0] in EXPECTED[scenario], (scenario, readable)
        assert panel.mode == "form" and f"fonts{seed % 3}/" in panel.family


def test_held_out_font_group_only_in_dev():
    fam = families.BY_NAME["ca_polst"]
    assert fam.dev == frozenset({3}) and 3 not in fam.train_variants() and fam.weight == 0.0
    assert not set(FONT_GROUPS[3]) & {f for g in FONT_GROUPS[:3] for f in g}
