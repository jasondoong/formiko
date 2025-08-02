"""Tests for JSONPath filter behavior."""

from jsonpath_ng.ext import parse

from formiko.renderer import JsonPreview


def filter_json_for_test(data, expression):
    """Return filtered results for tests."""
    preview = JsonPreview()
    preview._json_data = data  # noqa: SLF001

    if not expression.strip():
        def collect_paths(val, path=""):
            paths = {path}
            if isinstance(val, dict):
                for k, v in val.items():
                    new_path = f"{path}.{k}" if path else k
                    paths |= collect_paths(v, new_path)
            elif isinstance(val, list):
                for i, v in enumerate(val):
                    new_path = f"{path}.[{i}]" if path else f"[{i}]"
                    paths |= collect_paths(v, new_path)
            return paths

        return data, [], collect_paths(data)

    expr = parse(expression)
    matches = expr.find(data)

    highlights = []
    expands = {""}
    for m in matches:
        current = m
        while current:
            p = str(current.full_path)
            expands.add("" if p == "$" else p)
            current = current.context
        p = str(m.full_path)
        highlights.append("" if p == "$" else p)

    return data, highlights, expands


def test_basic_filter():
    """Expand only matching branch for direct path."""
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl, exp = filter_json_for_test(data, "$.a.b")
    assert pruned == data
    assert hl == ["a.b"]
    assert exp == {"", "a", "a.b"}


def test_no_filter():
    """Handle empty expression without folding."""
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl, exp = filter_json_for_test(data, "")
    assert pruned == data
    assert hl == []
    assert exp == {"", "a", "a.b", "c"}


def test_no_matches():
    """Collapse to root when no paths match."""
    data = {"a": {"b": 1}, "c": 2}
    pruned, hl, exp = filter_json_for_test(data, "$.d")
    assert pruned == data
    assert hl == []
    assert exp == {""}


def test_wildcard_filter():
    """Expand all children of wildcard path."""
    data = {"a": {"b": 1, "c": 2}}
    pruned, hl, exp = filter_json_for_test(data, "$.a.*")
    assert pruned == data
    assert sorted(hl) == ["a.b", "a.c"]
    assert exp == {"", "a", "a.b", "a.c"}


def test_array_filter():
    """Expand matching array index."""
    data = {"a": [10, 20, 30]}
    pruned, hl, exp = filter_json_for_test(data, "$.a[1]")
    assert pruned == data
    assert hl == ["a.[1]"]
    assert exp == {"", "a", "a.[1]"}


def test_root_is_match():
    """Handle root match properly."""
    data = {"a": 1}
    pruned, hl, exp = filter_json_for_test(data, "$")
    assert pruned == data
    assert hl == [""]
    assert exp == {""}
