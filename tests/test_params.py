import pytest

from textacad.params import ParamsError, apply_values, extract_params

CODE = '''import cadquery as cq

PARAMS = {
    "length": {"value": 60, "unit": "mm", "min": 10, "max": 100, "label": "L"},
    "count": {"value": 4, "unit": "count", "min": 1, "max": 10, "label": "N"},
}

L = PARAMS["length"]["value"]  # comment kept
result = cq.Workplane("XY").box(L, 10, 10)
'''


def test_extract():
    p = extract_params(CODE)
    assert p["length"]["value"] == 60 and p["count"]["unit"] == "count"


def test_apply_changes_only_params():
    new = apply_values(CODE, {"length": 75.5, "count": 6.0})
    p = extract_params(new)
    assert p["length"]["value"] == 75.5
    assert p["count"]["value"] == 6 and isinstance(p["count"]["value"], int)
    assert new.endswith(CODE.split("\n}\n", 1)[1])   # rest of the script identical


def test_value_out_of_range():
    with pytest.raises(ParamsError):
        extract_params(CODE.replace('"value": 60', '"value": 600'))


def test_missing_keys():
    with pytest.raises(ParamsError):
        extract_params('PARAMS = {"a": {"value": 1}}')


def test_no_params():
    with pytest.raises(ParamsError):
        extract_params("x = 1")
