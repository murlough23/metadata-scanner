from scan_metadata import check_quality


def fast_info(row_count, with_pk=True):
    """A table as the scanner produces it in --fast mode."""
    return {
        "type": "BASE TABLE",
        "row_count": row_count,
        "row_count_exact": False,
        "columns": [
            {"name": "id", "data_type": "int", "nullable": False,
             "key": "PRI" if with_pk else None},
            {"name": "notes", "data_type": "varchar", "nullable": True, "key": None},
        ],
    }


def rules_for(info):
    return [issue["rule"] for issue in check_quality(info)]


def test_flags_missing_primary_key():
    info = {"type": "BASE TABLE", "row_count": 5, "row_count_exact": True,
            "columns": [{"name": "a", "key": None, "nullable": True,
                         "null_count": 0, "null_pct": 0.0, "distinct_count": 4}]}
    assert [i["rule"] for i in check_quality(info)] == ["no_primary_key"]

def test_flags_empty_table():
    info = {"type": "BASE TABLE", "row_count": 0, "row_count_exact": True,
            "columns": [{"name": "id", "key": "PRI", "nullable": False, "null_count": 0}]}
    assert [i["rule"] for i in check_quality(info)] == ["empty_table"]

def test_flags_column_with_distinct_count_equal_to_rows():
    info = {"type": "BASE TABLE", "row_count": 5, "row_count_exact": True,
            "columns": [
                {"name": "id", "key": "PRI", "nullable": False,
                 "null_count": 0, "null_pct": 0.0, "distinct_count": 5},
            ]}
    rules = [i["rule"] for i in check_quality(info)]
    assert "cols_rows_equal" in rules
    assert "no_primary_key" not in rules


def test_fast_mode_does_not_crash_without_column_stats():
    # would raise KeyError before the guard was added
    check_quality(fast_info(1000))


def test_fast_mode_estimate_of_zero_is_not_called_empty():
    assert "empty_table" not in rules_for(fast_info(0))


def test_fast_mode_still_flags_missing_primary_key():
    assert "no_primary_key" in rules_for(fast_info(1000, with_pk=False))


def test_fast_mode_skips_column_rules():
    rules = rules_for(fast_info(1000))
    assert "all_null_column" not in rules
    assert "mostly_null_column" not in rules