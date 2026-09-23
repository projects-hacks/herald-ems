import pytest

from herald.core.snapshot import default_counties


def _switch(county_id):
    reg = default_counties()
    before = reg.active["id"]
    reg.activate(county_id)
    return reg, before


@pytest.fixture
def generic_county():
    reg, before = _switch("generic")
    yield
    reg.activate(before)


@pytest.fixture
def santa_clara_county():
    reg, before = _switch("santa_clara")
    yield
    reg.activate(before)
