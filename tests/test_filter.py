import pytest
from jsonpath_ng.ext import parse

from formiko.renderer import JsonPreview


def filter_json_for_test(data, expression):
    """
    A test helper function to simulate the filtering process
    and return the pruned data and highlight paths.
    """
    preview = JsonPreview()
    preview._json_data = data

    if not expression.strip():
        return data, []

    expr = parse(expression)
    matches = expr.find(data)

    if not matches:
        return {}, []

    pruned_data = preview._build_pruned_tree(matches)
    highlight_paths = [str(m.full_path) for m in matches]

    return pruned_data, highlight_paths


def test_basic_filter():
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl = filter_json_for_test(data, "$.a.b")
    assert pruned == {"a": {"b": 1}}
    assert hl == ["a.b"]


def test_no_filter():
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl = filter_json_for_test(data, "")
    assert pruned == data
    assert hl == []


def test_no_matches():
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl = filter_json_for_test(data, "$.d")
    assert pruned == {}
    assert hl == []


def test_wildcard_filter():
    data = {"a": {"b": 1, "c": 2}}
    pruned, hl = filter_json_for_test(data, "$.a.*")
    assert pruned == {"a": {"b": 1, "c": 2}}
    assert sorted(hl) == ["a.b", "a.c"]


def test_array_filter():
    data = {"a": [10, 20, 30]}
    pruned, hl = filter_json_for_test(data, "$.a[1]")
    assert pruned == {"a": [20]}
    assert hl == ["a.[1]"]


def test_root_is_match():
    data = {"a": 1}
    pruned, hl = filter_json_for_test(data, "$")
    assert pruned == data
    assert hl == ["$"]
