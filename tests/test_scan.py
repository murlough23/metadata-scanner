from scan_metadata import check_quality

def test_flags_missing_primary_key():
    info = {"type": "BASE TABLE", "row_count": 5,
            "columns": [{"name": "a", "key": None, "nullable": True,
                         "null_count": 0, "null_pct": 0.0, "distinct_count": 4}]}
    assert [i["rule"] for i in check_quality(info)] == ["no_primary_key"]

def test_flags_empty_table():
    info = {"type": "BASE TABLE", "row_count": 0,
            "columns": [{"name": "id", "key": "PRI", "nullable": False, "null_count": 0}]}
    assert [i["rule"] for i in check_quality(info)] == ["empty_table"]

def test_flags_column_with_distinct_count_equal_to_rows():
    info = {"type": "BASE TABLE", "row_count": 5,
            "columns": [
                {"name": "id", "key": "PRI", "nullable": False,
                 "null_count": 0, "null_pct": 0.0, "distinct_count": 5},
            ]}
    rules = [i["rule"] for i in check_quality(info)]
    assert "cols_rows_equal" in rules
    assert "no_primary_key" not in rules