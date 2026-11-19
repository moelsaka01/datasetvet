"""Synthetic splits with known duplicate and leakage counts."""

from datasetvet.checks.health.duplicates import HashStore
from datasetvet.checks.health.rowhash import hash_columns


def add(store, split, texts, labels, config="c", file_no=0, first=0):
    rows, inputs = hash_columns({"text": texts, "label": labels}, ["label"])
    store.add(f"{config}/{split}", config, file_no, first, rows, inputs)


def test_known_counts(tmp_path):
    store = HashStore(tmp_path)
    # train: "a" x3 (2 extra), "b" x2 (1 extra), "c" once -> 3 extra copies
    add(store, "train", ["a", "a", "a", "b", "b", "c", "d"], [0, 0, 0, 1, 1, 0, 1])
    # test: "a" with the same label, "d" with a different label, "e" only here
    add(store, "test", ["a", "d", "e"], [0, 0, 1])
    # another config never leaks into this one
    add(store, "train", ["e"], [1], config="other")
    dups = {d.split: d for d in store.duplicates()}
    assert dups["c/train"].extra_copies == 3 and dups["c/train"].rows == 7
    assert dups["c/test"].extra_copies == 0
    assert dups["c/train"].examples[0] == [[0, 0], [0, 1], [0, 2]]
    (leak,) = [x for x in store.leakage() if x.config == "c"]
    assert (leak.split_a, leak.split_b) == ("c/test", "c/train")
    assert leak.shared_inputs == 2  # "a" and "d"
    assert leak.rows_a == 2 and leak.rows_b == 4  # test: a,d ; train: a,a,a,d
    assert leak.label_differs == 1  # "d" has label 1 in train, 0 in test
    assert round(leak.pct_of_smaller, 2) == round(100 * 2 / 3, 2)
    assert leak.examples[0] == {"a": [0, 0], "b": [0, 0]}
    other = [x for x in store.leakage() if x.config == "other"]
    assert other == []  # a single split has no pairs
    store.close()


def test_pair_without_overlap_reported_as_zero(tmp_path):
    store = HashStore(tmp_path)
    add(store, "train", ["a"], [0])
    add(store, "test", ["b"], [0])
    (leak,) = store.leakage()
    assert leak.shared_inputs == 0
    store.close()


def test_works_beyond_a_tiny_memory_cap(tmp_path):
    # 1.1M rows: the hash tables for these queries need well over 64 MB, so DuckDB must spill
    # to its temp directory. (32 MB is below DuckDB's practical floor for these joins.)
    store = HashStore(tmp_path, memory_limit="64MB")
    n = 1_000_000
    batch = 100_000
    for start in range(0, n, batch):
        texts = [f"row {i % (n - 1000)}" for i in range(start, start + batch)]  # 1,000 repeats
        add(store, "train", texts, [i % 3 for i in range(start, start + batch)], first=start)
    texts = [f"row {i}" for i in range(100_000)]
    add(store, "test", texts, [0] * len(texts))
    dups = {d.split: d for d in store.duplicates()}
    assert dups["c/train"].extra_copies == 1000
    (leak,) = store.leakage()
    assert leak.shared_inputs == 100_000
    store.close()
