import datetime as dt

from datasetvet.checks.health.rowhash import encode_value, hash_columns, hash_row


def test_column_order_does_not_matter():
    assert hash_row({"a": 1, "b": "x"}) == hash_row({"b": "x", "a": 1})


def test_types_are_distinguished():
    values = [1, 1.0, "1", True, b"1", [1], {"v": 1}, None, "", 0, False, 0.0, -0.0]
    encodings = {encode_value(v) for v in values}
    assert len(encodings) == len(values)


def test_column_names_matter():
    assert hash_row({"a": 1}) != hash_row({"b": 1})


def test_nested_and_binary_values():
    img1 = {"bytes": b"\x89PNG\x00\x01", "path": None}
    img2 = {"bytes": b"\x89PNG\x00\x02", "path": None}
    assert hash_row({"image": img1}) != hash_row({"image": img2})
    assert hash_row({"x": [[1, 2], [3]]}) != hash_row({"x": [[1], [2, 3]]})
    assert hash_row({"x": {"a": 1, "b": [None]}}) == hash_row({"x": {"b": [None], "a": 1}})
    assert hash_row({"d": dt.date(2024, 1, 2)}) != hash_row({"d": "2024-01-02"})


def test_string_boundaries_cannot_shift():
    assert hash_row({"a": "xy", "b": "z"}) != hash_row({"a": "x", "b": "yz"})


def test_batch_hashes_match_row_hashes_and_input_excludes_labels():
    cols = {"text": ["a", "a", "b"], "label": [0, 1, 0]}
    rows, inputs = hash_columns(cols, ["label"])
    assert rows[0] == hash_row({"text": "a", "label": 0})
    assert rows[0] != rows[1] and inputs[0] == inputs[1]
    assert inputs[0] == hash_row({"text": "a"})
    rows2, inputs2 = hash_columns(cols)
    assert rows2 == inputs2 == rows
    assert all(len(h) == 16 for h in rows)


def test_timezone_aware_timestamps_hash():
    # needs tzdata on Windows (pyproject); found on ksolovev/fine-news in the launch scan
    import datetime

    import pyarrow as pa

    t = pa.array([datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)],
                 type=pa.timestamp("us", tz="Europe/Paris"))
    rows, _ = hash_columns(pa.table({"t": t}).to_pydict(), [])
    assert len(rows) == 1
