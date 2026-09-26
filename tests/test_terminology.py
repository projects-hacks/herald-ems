"""Drug and allergen coding (spec S6, MODEL_PLAN §0j): the normalizer never guesses, the coder keeps
what was said, anything not matched exactly waits for the medic's tap, and only drugs in a configured class set
that class's key."""
import time

import pytest

from fakes import FakeModel, make_client, tiny_coder, tiny_normalizer
from herald.api.capture import CaptureService
from herald.config import get_settings, load_yaml
from herald.core.schema import CapturedBy, FactIn, Role
from herald.core.vocabulary import Vocabulary, default_vocabulary
from herald.models import VisionReader
from herald.terminology import AllergyClasses, DrugClass, MedicationCoder, RxNormNormalizer

N = tiny_normalizer()
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"


def rx(code):
    return {"system": RXNORM, "code": code}


def codes(f):
    """A fact's code(s) as plain dicts (None where not coded)."""
    c = f.model_dump(mode="json")["code"]
    return c


# ---------- the normalizer ----------
@pytest.mark.parametrize("said, value, method", [
    ("Lipitor", "atorvastatin", "exact"),
    ("lipiter", "atorvastatin", "phonetic"),
    ("eloquis", "apixaban", "phonetic"),
    ("cumadin", "warfarin", "fuzzy"),
    ("Plavix", "clopidogrel", "exact"),
    ("Warfarin 5 mg", "warfarin", "exact"),
    ("aspirin 81 milligrams", "aspirin", "exact"),
    ("warfarin sodium 5 mg oral tablet", "warfarin", "exact"),
    ("Zofran", "ondansetron", "exact"),                       # retired brand, from the RxNav supplement
    ("Vicodin", "acetaminophen / hydrocodone", "exact"),
])
def test_names_resolve(said, value, method):
    r = N.normalize("meds.list", said)
    assert (r.value, r.method) == (value, method) and r.code


def test_a_number_in_a_product_name_is_not_a_dose():
    """"Tylenol 3" is acetaminophen with codeine, never plain acetaminophen; an unknown numbered product is never
    approximated to the plain brand."""
    r = N.normalize("allergies", "Tylenol 3")
    assert (r.value, r.code, r.method) == ("acetaminophen / codeine", "817579", "exact")
    for said in ["Humalog 75/25", "NovoLog 70/30", "Eliquis 5"]:
        assert N.normalize("meds.list", said).method == "unresolved", said


@pytest.mark.parametrize("said", ["something for her thyroid", "penicillin", "insulin", "sulfa", "shellfish", "D50",
                                  "peanuts", "nitro spray"])
def test_allergens_are_never_guessed(said):
    """Unmatched, less specific ("penicillin" is not "penicillin g"), a real RxNorm word ("insulin" is not a
    misspelling of "inulin"), or product words, which allergies never resolve through: kept as said."""
    r = N.normalize("allergies", said)
    assert (r.value, r.code, r.method) == (said, None, "unresolved")


def test_combinations_resolve_only_to_a_real_combination():
    for said in ["ipratropium-albuterol", "albuterol and ipratropium"]:
        r = N.normalize("meds.given", said)
        assert (r.value, r.code, r.method) == ("albuterol / ipratropium", "214199", "combination")
    assert N.normalize("meds.list", "Eliquis and Plavix").method == "unresolved"     # two drugs, not one product


def test_words_from_product_names_resolve_only_when_one_ingredient_fits():
    for said, value in [("nitro spray", "nitroglycerin"), ("divalproex", "valproate"), ("albuterol inhaler", "albuterol")]:
        r = N.normalize("meds.list", said)
        assert (r.value, r.method) == (value, "contained"), said
    assert N.normalize("meds.list", "insulin").method == "unresolved"               # lispro or glargine?
    assert N.normalize("meds.list", "penicillin").method == "unresolved"            # g or v?


def test_multi_ingredient_brand_uses_rxnorm_naming():
    r = N.normalize("meds.list", "Percocet")
    assert (r.value, r.code, r.ingredients) == ("acetaminophen / oxycodone", "214183", ("acetaminophen", "oxycodone"))


def test_ambiguous_name_is_not_resolved():
    n = RxNormNormalizer({"1": "a drug", "2": "b drug"}, {"samename": ["1", "2"]}, ["samename"], release="t")
    assert n.normalize("meds.list", "samename").method == "ambiguous"


# ---------- drug-class allergies (NEMSIS eHistory.06) ----------
@pytest.mark.parametrize("said, code, method", [
    ("penicillin", "Z88.0", "class"), ("sulfa", "Z88.2", "class"), ("sulfa drugs", "Z88.2", "class"),
    ("sulfonamides", "Z88.2", "class"), ("narcotics", "Z88.5", "class_fuzzy"), ("penicillins", "Z88.0", "class_fuzzy"),
])
def test_allergy_classes(said, code, method):
    r = AllergyClasses.from_config("terminology/allergy_classes.yaml").normalize("allergies", said)
    assert (r.code, r.method, r.system) == (code, method, "icd10cm")


@pytest.mark.parametrize("said", ["drugs", "other", "peanuts", "latex", "bee stings"])
def test_allergy_classes_never_guess(said):
    assert not AllergyClasses.from_config("terminology/allergy_classes.yaml").normalize("allergies", said).resolved


# ---------- the coder ----------
def _fact(key, value, **kw):
    return FactIn(key=key, value=value, **kw)


def test_meds_list_items_get_generic_names_codes_and_the_anticoagulant():
    out = tiny_coder().code([_fact("meds.list", ["Eliquis", "metformin", "something for her thyroid"],
                                   role=Role.family, speaker="daughter")])
    meds = next(f for f in out if f.key == "meds.list")
    assert meds.value == ["apixaban", "metformin", "something for her thyroid"]
    assert codes(meds) == [rx("1364430"), rx("6809"), None]
    assert [e["said"] for e in meds.provenance.normalized] == ["Eliquis", "metformin", "something for her thyroid"]
    assert meds.provenance.hold_reason is None                     # exact matches don't wait
    [anti] = [f for f in out if f.key == "meds.anticoagulant"]
    assert (anti.value, codes(anti), anti.role, anti.speaker) == ("apixaban", rx("1364430"), Role.family, "daughter")
    assert anti.provenance.normalized[0]["said"] == "Eliquis"


def test_brand_and_generic_of_one_drug_are_one_item():
    out = tiny_coder().code([_fact("meds.list", ["Coumadin", "warfarin"])])
    assert [(f.key, f.value) for f in out] == [("meds.list", ["warfarin"]), ("meds.anticoagulant", "warfarin")]


def test_class_drug_alone_is_also_a_medication():
    out = tiny_coder().code([_fact("meds.anticoagulant", "Lovenox", role=Role.family)])
    assert [(f.key, f.value, codes(f), f.role) for f in out] == [
        ("meds.anticoagulant", "enoxaparin", rx("67108"), Role.family),
        ("meds.list", ["enoxaparin"], [rx("67108")], Role.family)]
    both = tiny_coder().code([_fact("meds.anticoagulant", "Lovenox"), _fact("meds.list", ["enoxaparin", "metformin"])])
    assert [f.key for f in both] == ["meds.anticoagulant", "meds.list"]


def test_drug_outside_the_class_is_a_medication_not_the_class_fact():
    out = tiny_coder().code([_fact("meds.anticoagulant", "Plavix")])
    assert [(f.key, f.value, codes(f)) for f in out] == [("meds.list", ["clopidogrel"], [rx("32968")])]
    assert tiny_coder().code([_fact("meds.list", ["aspirin", "Plavix"])])[1:] == []


@pytest.mark.parametrize("said", ["none", "no", "a blood thinner"])
def test_denials_and_unresolved_class_facts_are_kept(said):
    f, = tiny_coder().code([_fact("meds.anticoagulant", said)])
    assert (f.key, f.value, f.code) == ("meds.anticoagulant", said, None)


def test_allergies_get_rxnorm_or_the_drug_class_code_and_never_become_medications():
    f, = tiny_coder().code([_fact("allergies", ["penicillin", "Codeine", "sulfa", "peanuts", "Tylenol 3"])])
    assert f.value == ["penicillin", "codeine", "sulfa", "peanuts", "acetaminophen / codeine"]
    assert codes(f) == [{"system": ICD10CM, "code": "Z88.0"}, rx("2670"), {"system": ICD10CM, "code": "Z88.2"}, None,
                        rx("817579")]
    assert f.provenance.hold_reason is None
    assert tiny_coder().code([_fact("allergies", [])])[0].value == []


def test_matches_by_sound_or_spelling_wait_for_a_tap_with_the_reason():
    out = tiny_coder().code([_fact("meds.list", ["zarelto", "stent"], confidence=0.93)])
    meds, anti = out
    assert meds.value == ["rivaroxaban", "sunitinib"]
    assert "matched by sound: 'zarelto' → rivaroxaban" in meds.provenance.hold_reason
    assert "matched by spelling: 'stent' → sunitinib" in meds.provenance.hold_reason
    assert anti.key == "meds.anticoagulant" and anti.provenance.hold_reason.startswith("drug name matched by sound")
    assert "stent" not in anti.provenance.hold_reason                   # only its own drug's reason


def test_given_drug_in_a_record_is_coded():
    out = tiny_coder().code([_fact("meds.given", {"drug": "Narcan", "dose": 4, "unit": "mg", "route": "IN"}),
                             _fact("meds.given", "aspirin"),
                             _fact("meds.given", {"drug": "ipratropium-albuterol"})])
    assert [f.value["drug"] for f in out] == ["naloxone", "aspirin", "albuterol / ipratropium"]
    assert out[0].value == {"drug": "naloxone", "dose": 4.0, "unit": "mg", "route": "IN"}
    assert [codes(f) for f in out] == [rx("7242"), rx("1191"), rx("214199")]
    assert out[2].provenance.hold_reason.startswith("drug names read as one combination")
    assert all(f.key == "meds.given" for f in out)                      # a dose given is never a home medication


def test_a_new_drug_key_is_configuration_only():
    """Declaring a key in config/terminology.yaml's `keys` is all it takes: nothing in the coder names a key."""
    base = default_vocabulary()
    vocab = Vocabulary({**base.keys, "meds.home_extra": {"label": "x", "type": "list", "kind": "history"}},
                       base.contradiction_keys)
    cfg = load_yaml("terminology.yaml")["keys"]
    coder = MedicationCoder(tiny_normalizer(), vocab, lists=[*cfg["lists"], "meds.home_extra"], records=cfg["records"],
                            meds_key=cfg["meds"], classes=[DrugClass.from_config(f) for f in
                                                           load_yaml("terminology.yaml")["classes"]])
    f, = coder.code([_fact("meds.home_extra", ["Lipitor"])])
    assert (f.value, codes(f)) == (["atorvastatin"], [rx("83367")])
    assert tiny_coder().keys == {*cfg["lists"], *cfg["records"], "meds.anticoagulant"}


def test_the_guard_keeps_a_drug_match_reason():
    f = tiny_coder().code([_fact("meds.list", ["zarelto"])])[0]
    CaptureService._hold([f], "mark her as")
    assert f.provenance.hold_reason.startswith('said together with a command to the system ("mark her as")')
    assert "matched by sound: 'zarelto'" in f.provenance.hold_reason and f.confidence <= 0.5


class _PillBottle:
    def available(self):
        return True

    def model_name(self):
        return "fake-vision"

    def chat_json(self, system, user, **kw):
        return {"facts": [{"key": "meds.list", "value": ["WARFARIN SODIUM 5MG"], "strength": "5 mg"}]}


def test_photo_label_is_coded_and_gives_the_anticoagulant():
    out = VisionReader(_PillBottle(), tiny_coder()).read(b"jpg", "pill_bottle")
    assert [(f.key, f.value) for f in out] == [("meds.list", ["warfarin"]), ("meds.anticoagulant", "warfarin")]
    assert all(f.role == Role.photo for f in out)


# ---------- through the app ----------
def _wait_model(c, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        tr = c.get("/api/state").json()["transcripts"][-1]["trace"]
        if tr["model"]["status"] != "running":
            return tr
        time.sleep(0.05)
    raise AssertionError("model phase did not finish")


def test_codes_reach_the_snapshot_trace_and_health():
    c, _ = make_client(FakeModel(rows=[["meds.list", ["Eliquis"], "m"]], conf=0.99), normalizer=tiny_normalizer())
    with c:
        c.post("/api/incident", json={"dispatch": "possible stroke", "disposition": "transported"})
        c.post("/api/transcript", json={"text": "She takes Eliquis."})
        facts = {f["key"]: f for f in _wait_model(c)["model"]["facts"]}
        assert facts["meds.list"]["value"] == ["apixaban"] and facts["meds.list"]["code"] == [rx("1364430")]
        assert facts["meds.anticoagulant"]["code"] == rx("1364430")
        assert facts["meds.anticoagulant"]["status"] == "confirmed"          # exact, from the medic, confident
        anti = c.get("/api/state").json()["facts"]["meds.anticoagulant"]       # latest fact per key
        assert (anti["value"], anti["code"]) == ("apixaban", rx("1364430"))
        assert anti["provenance"]["normalized"][0]["said"] == "Eliquis"
        assert c.get("/api/health").json()["terminology"] == {"rxnorm_release": "test"}


def test_a_sound_alike_drug_never_confirms_itself():
    c, _ = make_client(FakeModel(rows=[["meds.list", ["zarelto"], "m"]], conf=0.99), normalizer=tiny_normalizer())
    with c:
        c.post("/api/transcript", json={"text": "She's on zarelto."})
        facts = {f["key"]: f for f in _wait_model(c)["model"]["facts"]}
        for key in ("meds.list", "meds.anticoagulant"):
            assert facts[key]["status"] == "unconfirmed" and "matched by sound" in facts[key]["hold_reason"]
            assert facts[key]["relay"].startswith("held")


def test_structured_facts_are_coded_too():
    c, _ = make_client(normalizer=tiny_normalizer())
    with c:
        r = c.post("/api/facts", json=[{"key": "meds.given", "value": {"drug": "Narcan", "dose": 4}}])
        assert r.status_code == 200, r.text
        given = c.get("/api/state").json()["facts"]["meds.given"]
        assert given["value"]["drug"] == "naloxone" and given["code"] == rx("7242")


def test_without_an_index_nothing_is_coded():
    c, ctx = make_client(FakeModel(rows=[["meds.list", ["Eliquis"], "m"]], conf=0.99))
    with c:
        assert ctx.coder is None and c.get("/api/health").json()["terminology"] is None


# ---------- content ----------
def test_classes_are_atc_b01a_anticoagulants_without_antiplatelets():
    cfg = load_yaml("terminology/anticoagulants.yaml")
    assert cfg["key"] == "meds.anticoagulant"
    assert set(cfg["groups"]) <= {"B01AA", "B01AB", "B01AE", "B01AF", "B01AX"}
    for group, g in cfg["groups"].items():
        assert all(code.startswith(group) for code in g["ingredients"].values())
    cls = DrugClass.from_config("terminology/anticoagulants.yaml").ingredients
    assert {"warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "enoxaparin", "heparin"} <= cls
    assert not cls & {"aspirin", "clopidogrel", "prasugrel", "ticagrelor", "dipyridamole", "cilostazol"}


def test_allergy_class_list_is_the_nemsis_ten():
    classes = load_yaml("terminology/allergy_classes.yaml")["classes"]
    assert [c["code"] for c in classes] == [f"Z88.{i}" for i in range(10)]


INDEX = get_settings().terminology_index


@pytest.mark.skipif(not INDEX.exists(), reason="RxNorm index not built (scripts/build_rxnorm_index.py)")
def test_real_index():
    n = RxNormNormalizer.load(INDEX)
    assert n.release == load_yaml("terminology.yaml")["source"]["release"]
    for said, want in [("Lipitor", "atorvastatin"), ("lipiter", "atorvastatin"), ("eloquis", "apixaban"),
                       ("cumadin", "warfarin"), ("Plavix", "clopidogrel"), ("xeralto", "rivaroxaban"),
                       ("Humalog", "insulin lispro"), ("ProAir", "albuterol"), ("Lovenox", "enoxaparin"),
                       ("Coumadin", "warfarin"), ("Zofran", "ondansetron"), ("Vicodin", "acetaminophen / hydrocodone"),
                       ("Tylenol 3", "acetaminophen / codeine"), ("ipratropium-albuterol", "albuterol / ipratropium"),
                       ("nitro spray", "nitroglycerin"), ("divalproex", "valproate")]:
        assert n.normalize("meds.list", said).value == want, said
    for said in ["Humalog 75/25", "NovoLog 70/30"]:
        r = n.normalize("meds.list", said)
        assert not r.resolved or len(r.ingredients) > 1, said                 # never one insulin of a mix
    for said in ["something for her thyroid", "insulin", "penicillin", "sulfa", "peanuts", "shellfish", "latex",
                 "bees", "nitro", "blood thinner", "dextrose"]:
        assert not n.normalize("allergies", said).resolved, said
    for said in ["insulin", "dextrose", "penicillin"]:
        assert not n.normalize("meds.list", said).resolved, said
