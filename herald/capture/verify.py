"""Compare coded ingredients only. A label never changes a spoken dose."""
from ..core.schema import FactIn
from .types import CheckResult


class DrugCheck:
    def __init__(self, coder, config: dict):
        self.coder, self.config = coder, config

    def compare(self, dose_fact, frame_facts) -> CheckResult:
        c = self.config
        if self.coder is None or dose_fact.key != c["dose_key"] or not isinstance(dose_fact.value, dict):
            return CheckResult("unreadable")
        said = dose_fact.value.get(c["drug_field"])
        if not isinstance(said, str):
            return CheckResult("unreadable")
        dose = self.coder.code([FactIn(key=c["dose_key"], value=dose_fact.value)])[0]
        methods = c["trusted_methods"]
        if not dose.code or not dose.provenance.normalized or any(n["method"] not in methods for n in dose.provenance.normalized):
            return CheckResult("unreadable")
        labels = []
        for f in frame_facts:
            if f.key != c["label_key"] or not isinstance(f.value, list):
                continue
            for name in f.value:
                if not isinstance(name, str):
                    continue
                coded = self.coder.code([FactIn(key=c["label_key"], value=[name])])[0]
                if not coded.code or not coded.code[0] or not coded.provenance.normalized:
                    return CheckResult("unreadable")
                if coded.provenance.normalized[0]["method"] not in methods:
                    return CheckResult("unreadable")
                labels.append((coded.code[0], coded.value[0]))
        unique = {(code.system, code.code): name for code, name in labels}
        if len(unique) != 1:
            return CheckResult("unreadable")
        (system, code), label = next(iter(unique.items()))
        return CheckResult("match" if (dose.code.system, dose.code.code) == (system, code) else "mismatch", label)
