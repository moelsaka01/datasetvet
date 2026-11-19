import pyarrow as pa

from datasetvet.checks.health.empty import EmptyCounter, is_empty_value
from datasetvet.checks.health.labels import (
    LabelCounter,
    labels_from_hf_features,
    pick_label_columns,
)


def test_empty_rule():
    assert is_empty_value(None) and is_empty_value("") and is_empty_value([])
    assert is_empty_value({"bytes": None, "path": None})
    assert not is_empty_value(" ") and not is_empty_value(0) and not is_empty_value([None])


def test_empty_counter():
    e = EmptyCounter()
    e.add_columns({"a": ["", None, "x", ""], "b": [[], None, [], [1]]}, file_no=0, first_row=10)
    assert e.count == 2 and e.examples == [[0, 10], [0, 11]]


def test_label_columns_classlabel_then_name_fallback():
    feats = {"text": {"_type": "Value"}, "y": {"_type": "ClassLabel", "names": ["a", "b"]},
             "tags": {"_type": "Sequence", "feature": {"_type": "ClassLabel", "names": ["t"]}}}
    cl = labels_from_hf_features(feats)
    assert cl == {"y": ["a", "b"], "tags": ["t"]}
    assert pick_label_columns(["text", "y", "tags"], cl) == (["y", "tags"], "ClassLabel feature")
    assert pick_label_columns(["text", "label"], {}) == (["label"], "column named label/labels")
    assert pick_label_columns(["text"], {}) == ([], "none")


def test_label_counter_table_ratio_and_names():
    lc = LabelCounter(names=["neg", "pos"])
    lc.add(pa.array([0, 0, 0, 1, -1]))
    table = lc.table()
    assert table[0] == {"label": "neg", "value": 0, "count": 3, "share": 0.6}
    assert lc.display(-1) == "-1 (no label)"
    assert lc.ratio() == 3.0  # -1 (no label) is left out of the ratio


def test_label_counter_lists_and_cardinality_cap():
    lc = LabelCounter()
    lc.add(pa.array([[1, 2], [2], []]))
    assert lc.counts == {1: 1, 2: 2}
    big = LabelCounter()
    big.add(pa.array([float(i) for i in range(1500)]))
    assert big.too_many and not big.counts
