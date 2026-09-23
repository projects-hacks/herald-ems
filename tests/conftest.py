import pytest

from herald import county


@pytest.fixture
def generic_county():
    before = county.active()["id"]
    county.activate("generic")
    yield
    county.activate(before)


@pytest.fixture
def santa_clara_county():
    before = county.active()["id"]
    county.activate("santa_clara")
    yield
    county.activate(before)
