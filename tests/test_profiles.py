"""Each served extractor is called exactly as it was trained (config/extraction.yaml)."""
from herald.core.schema import CapturedBy
from herald.extraction.profiles import Profiles

P = Profiles.from_config(extra_finetuned=("my-tuned",))


def test_labels_map_to_the_profile_they_were_trained_with():
    assert P.for_label("ems-d-fp8").speaker_line and not P.for_label("ems-c-fp8").speaker_line
    assert P.for_label("ems") is P.for_label("ems-c-fp8")
    assert P.for_label("my-tuned") is not None                     # listed in HERALD_FINETUNED_MODELS
    assert P.for_label("omni") is None and P.for_label(None) is None


def test_run_c_input_is_unchanged_and_run_d_input_says_whose_mic():
    assert P.model_input(P.for_label("ems-c-fp8"), "BP 120 over 80", CapturedBy.medic, None) == "BP 120 over 80"
    d = P.for_label("ems-d-fp8")
    assert P.model_input(d, "Mom is allergic", CapturedBy.other, "daughter") == "[daughter's mic]\nMom is allergic"
    assert P.model_input(d, "BP 120", CapturedBy.medic, None).startswith("[medic's mic]\n")
    assert P.model_input(d, "I feel dizzy", CapturedBy.other, None).startswith("[someone else's mic]\n")
