import pytest
from jsonpath_ng.ext import parse

from formiko.renderer import JsonPreview


def filter_json_for_test(data, expression):
    preview = JsonPreview()
    preview._json_data = data
    if not expression.strip():
        return data, [], []
    expr = parse(expression)
    matches = expr.find(data)
    highlights, expand = preview._build_paths(matches)
    return data, highlights, expand


def test_basic_filter():
    data = {"a": {"b": 1}, "c": 2}
    returned, hl, expand = filter_json_for_test(data, "$.a.b")
    assert returned == data
    assert hl == ["a.b"]
    assert set(expand) == {"", "a", "a.b"}


def test_no_filter():
    data = {"a": {"b": 1}, "c": 2}
    returned, hl, expand = filter_json_for_test(data, "")
    assert returned == data
    assert hl == []
    assert expand == []


def test_no_matches():
    data = {"a": {"b": 1}, "c": 2}
    returned, hl, expand = filter_json_for_test(data, "$.d")
    assert returned == data
    assert hl == []
    assert expand == []


def test_wildcard_filter():
    data = {"a": {"b": 1, "c": 2}}
    returned, hl, expand = filter_json_for_test(data, "$.a.*")
    assert returned == data
    assert sorted(hl) == ["a.b", "a.c"]
    assert set(expand) == {"", "a", "a.b", "a.c"}


def test_array_filter():
    data = {"a": [10, 20, 30]}
    returned, hl, expand = filter_json_for_test(data, "$.a[1]")
    assert returned == data
    assert hl == ["a.[1]"]
    assert set(expand) == {"", "a", "a.[1]"}


def test_root_is_match():
    data = {"a": 1}
    returned, hl, expand = filter_json_for_test(data, "$")
    assert returned == data
    assert hl == [""]
    assert set(expand) == {""}
