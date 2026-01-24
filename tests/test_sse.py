import json

from airframe.adapters.llama_server import _parse_sse_lines


def test_parse_sse_lines_basic():
    lines = [
        "data: {\"content\":\"Hello\"}",
        "data: {\"content\":\" world\"}",
        "data: [DONE]",
    ]
    out = list(_parse_sse_lines(lines))
    assert len(out) == 2
    assert json.loads(out[0])["content"] == "Hello"
    assert json.loads(out[1])["content"] == " world"


def test_parse_sse_lines_mixed_and_done():
    lines = [
        "{\"content\":\"plain\"}",
        "data: {\"content\":\"next\"}",
        "data: [DONE]",
        "data: {\"content\":\"ignored\"}",
    ]
    out = list(_parse_sse_lines(lines))
    assert [json.loads(o)["content"] for o in out] == ["plain", "next"]
