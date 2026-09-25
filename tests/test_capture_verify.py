import pytest

from fakes import tiny_coder
from herald.capture.config import capture_config
from herald.capture.verify import DrugCheck
from herald.core.schema import FactIn


@pytest.mark.parametrize("label,status", [("naloxone", "match"), ("Narcan", "match"), ("naloxone hydrochloride", "match"),
                                         ("ondansetron", "mismatch"), ("unknown mystery drug", "unreadable")])
def test_coded_comparison_does_not_change_spoken_dose(label, status):
    check = DrugCheck(tiny_coder(), capture_config()["verify"])
    dose = FactIn(key="meds.given", value={"drug": "Narcan", "dose": .4, "unit": "mg", "by": "crew"})
    before = dose.model_dump()
    assert check.compare(dose, [FactIn(key="meds.list", value=[label])]).status == status
    assert dose.model_dump() == before


def test_multiple_labels_or_missing_coder_are_not_a_match():
    dose = FactIn(key="meds.given", value={"drug": "Narcan"})
    labels = [FactIn(key="meds.list", value=["naloxone", "ondansetron"])]
    assert DrugCheck(tiny_coder(), capture_config()["verify"]).compare(dose, labels).status == "unreadable"
    assert DrugCheck(None, capture_config()["verify"]).compare(dose, labels).status == "unreadable"
