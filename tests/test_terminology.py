"""Drug and allergen names -> RxNorm (spec S6): the normalizer never guesses, the coder keeps what was said, and
only drugs in the reviewed anticoagulant class become `meds.anticoagulant`."""
import pytest

from fakes import FakeModel, make_client, rules_extractor, tiny_coder, tiny_normalizer
from herald.config import get_settings, load_yaml
from herald.core.schema import FactIn, Role
from herald.models import VisionReader
from herald.terminology import RxNormNormalizer, anticoagulant_class

N = tiny_normalizer()


@pytest.mark.parametrize("said, value, method", [
    ("Lipitor", "atorvastatin", "exact"),
    ("lipiter", "atorvastatin", "phonetic"),
    ("eloquis", "apixaban", "phonetic"),
    ("cumadin", "warfarin", "fuzzy"),
    ("Plavix", "clopidogrel", "exact"),
    ("Warfarin 5 mg", "warfarin", "exact"),
    ("warfarin sodium 5 mg oral tablet", "warfarin", "exact"),
])
def test_spec_cases_resolve(said, value, method):
    r = N.normalize("meds.list", said)
    assert (r.value, r.method) == (value, method) and r.code


@pytest.mark.parametrize("said", ["something for her thyroid", "penicillin", "insulin", "sulfa", "shellfish", "D50"])
def test_never_guesses(said):
    """Unmatched, less specific ("penicillin" is not "penicillin g"), or a real RxNorm word ("insulin" is not a
    misspelling of "inulin"): kept as said, unresolved."""
    r = N.normalize("allergies", said)
    assert (r.value, r.code, r.method) == (said, None, "unresolved")


def test_multi_ingredient_brand_uses_rxnorm_naming():
    r = N.normalize("meds.list", "Percocet")
    assert (r.value, r.code, r.ingredients) == ("acetaminophen / oxycodone", "214183", ("acetaminophen", "oxycodone"))


def test_ambiguous_name_is_not_resolved():
    n = RxNormNormalizer({"1": "a drug", "2": "b drug"}, {"samename": ["1", "2"]}, ["samename"], release="t")
    assert n.normalize("meds.list", "samename").method == "ambiguous"


def _fact(key, value, **kw):
    return FactIn(key=key, value=value, **kw)


def test_meds_list_items_get_generic_names_codes_and_the_anticoagulant():
    out = tiny_coder().code([_fact("meds.list", ["Eliquis", "metformin", "something for her thyroid"],
                                   role=Role.family, speaker="daughter")])
    meds = next(f for f in out if f.key == "meds.list")
    assert meds.value == ["apixaban", "metformin", "something for her thyroid"]
    assert meds.code == ["1364430", "6809", None]
    assert [e["said"] for e in meds.provenance.normalized] == ["Eliquis", "metformin", "something for her thyroid"]
    [anti] = [f for f in out if f.key == "meds.anticoagulant"]
    assert (anti.value, anti.code, anti.role, anti.speaker) == ("apixaban", "1364430", Role.family, "daughter")
    assert anti.provenance.normalized[0]["said"] == "Eliquis"


def test_brand_and_generic_of_one_drug_are_one_item():
    out = tiny_coder().code([_fact("meds.list", ["Coumadin", "warfarin"])])
    assert [(f.key, f.value) for f in out] == [("meds.list", ["warfarin"]), ("meds.anticoagulant", "warfarin")]


def test_anticoagulant_alone_is_also_a_medication():
    out = tiny_coder().code([_fact("meds.anticoagulant", "Lovenox", role=Role.family)])
    assert [(f.key, f.value, f.code, f.role) for f in out] == [
        ("meds.anticoagulant", "enoxaparin", "67108", Role.family),
        ("meds.list", ["enoxaparin"], ["67108"], Role.family)]
    both = tiny_coder().code([_fact("meds.anticoagulant", "Lovenox"), _fact("meds.list", ["enoxaparin", "metformin"])])
    assert [f.key for f in both] == ["meds.anticoagulant", "meds.list"]


def test_antiplatelet_is_a_medication_not_an_anticoagulant():
    out = tiny_coder().code([_fact("meds.anticoagulant", "Plavix")])
    assert [(f.key, f.value, f.code) for f in out] == [("meds.list", ["clopidogrel"], ["32968"])]
    assert tiny_coder().code([_fact("meds.list", ["aspirin", "Plavix"])])[1:] == []


def test_denial_and_unresolved_anticoagulant_kept():
    none, = tiny_coder().code([_fact("meds.anticoagulant", "none")])
    assert (none.value, none.code) == ("none", None)
    vague, = tiny_coder().code([_fact("meds.anticoagulant", "a blood thinner")])
    assert (vague.key, vague.value, vague.code) == ("meds.anticoagulant", "a blood thinner", None)


def test_allergies_are_coded_but_never_become_medications():
    out = tiny_coder().code([_fact("allergies", ["penicillin", "Codeine", "warfarin"])])
    assert [(f.key, f.value, f.code) for f in out] == [
        ("allergies", ["penicillin", "codeine", "warfarin"], [None, "2670", "11289"])]
    assert tiny_coder().code([_fact("allergies", [])])[0].value == []


def test_rules_take_anticoagulant_names_from_rxnorm():
    rules = rules_extractor()
    facts = {f.key: f for f in rules.extract("She's on Xarelto.")}
    assert facts["meds.anticoagulant"].value == "rivaroxaban" and facts["meds.list"].value == ["rivaroxaban"]
    assert facts["meds.list"].code == ["1114195"]
    assert not any(f.key == "meds.anticoagulant" for f in rules.extract("She takes Plavix."))


class _PillBottle:
    def available(self):
        return True

    def model_name(self):
        return "fake-vision"

    def chat_json(self, system, user, **kw):
        return {"facts": [{"key": "meds.list", "value": ["WARFARIN SODIUM 5MG"], "strength": "5 mg"}]}


def test_photo_label_is_normalized_and_gives_the_anticoagulant():
    out = VisionReader(_PillBottle(), tiny_coder()).read(b"jpg", "pill_bottle")
    assert [(f.key, f.value) for f in out] == [("meds.list", ["warfarin"]), ("meds.anticoagulant", "warfarin")]
    assert all(f.role == Role.photo for f in out)


def test_codes_reach_the_snapshot_trace_and_health():
    c, _ = make_client(FakeModel(rows=[["meds.list", ["Lipitor"], "m"]]))
    with c:
        c.post("/api/incident", json={"dispatch": "possible stroke"})
        tr = c.post("/api/transcript", json={"text": "She takes Eliquis.", "use_llm": False}).json()
        rules = {f["key"]: f for f in tr["transcript"]["trace"]["rules"]["facts"]}
        assert rules["meds.list"]["value"] == ["apixaban"] and rules["meds.list"]["code"] == ["1364430"]
        assert rules["meds.anticoagulant"]["code"] == "1364430"
        anti = c.get("/api/state").json()["facts"]["meds.anticoagulant"]       # latest fact per key
        assert (anti["value"], anti["code"]) == ("apixaban", "1364430")
        assert anti["provenance"]["normalized"][0]["said"] == "Eliquis"
        assert c.get("/api/health").json()["terminology"] == {"rxnorm_release": "test"}


def test_anticoagulant_class_is_atc_b01a_and_excludes_antiplatelets():
    classes = load_yaml("terminology/anticoagulants.yaml")["classes"]
    assert set(classes) <= {"B01AA", "B01AB", "B01AE", "B01AF", "B01AX"}
    for group, c in classes.items():
        assert all(code.startswith(group) for code in c["ingredients"].values())
    cls = anticoagulant_class()
    assert {"warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "enoxaparin", "heparin"} <= cls
    assert not cls & {"aspirin", "clopidogrel", "prasugrel", "ticagrelor", "dipyridamole", "cilostazol"}


INDEX = get_settings().terminology_index


@pytest.mark.skipif(not INDEX.exists(), reason="RxNorm index not built (scripts/build_rxnorm_index.py)")
def test_real_index():
    n = RxNormNormalizer.load(INDEX)
    assert n.release == load_yaml("terminology.yaml")["source"]["release"]
    for said, want in [("Lipitor", "atorvastatin"), ("lipiter", "atorvastatin"), ("eloquis", "apixaban"),
                       ("cumadin", "warfarin"), ("Plavix", "clopidogrel"), ("xeralto", "rivaroxaban"),
                       ("Humalog", "insulin lispro"), ("ProAir", "albuterol"), ("Lovenox", "enoxaparin")]:
        assert n.normalize("meds.list", said).value == want, said
    for said in ["something for her thyroid", "insulin", "penicillin", "sulfa", "peanuts", "shellfish", "latex",
                 "bees", "nitro", "blood thinner"]:
        assert not n.normalize("allergies", said).resolved, said
    names = n.names_for(anticoagulant_class())
    assert {"coumadin", "jantoven", "eliquis", "xarelto", "pradaxa", "savaysa", "lovenox"} <= set(names)
    assert "plavix" not in names
