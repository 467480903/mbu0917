import pytest
import s7


@pytest.mark.parametrize("address, expected", [("DB1.DBX2.3", (1,2,1,3)), ("DB2.DBW4", (2,4,2,None)), ("DB3.DBD8", (3,8,4,None))])
def test_parse_s7_addresses(address, expected):
    assert s7._parse_s7_addr(address) == expected


def test_parse_s7_rejects_invalid_addresses():
    with pytest.raises(ValueError):
        s7._parse_s7_addr("M0.0")
    with pytest.raises(ValueError):
        s7._parse_s7_addr("DB1.DBX0.8")


def test_extract_integer_values():
    assert s7._extract_value(b"\x00\x02", {"type":"int"}) == 2
    assert s7._extract_value(b"\x00\x00\x00\x05", {"type":"dint"}) == 5
    assert s7._extract_value(None, {"type":"int"}) is None
