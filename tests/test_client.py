"""Offline tests: a fake transport records each request; no network, no real key."""
import asyncio
import json

import pytest

from fanar_mcp.client import FanarClient, FanarError, multipart_body, rate_limit_from

KEY = "test-key-0123456789"


class FakeTransport:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status, self.body, self.headers = status, body, headers or {}
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data})
        return self.status, self.headers, self.body


def client(transport):
    return FanarClient(api_key=KEY, transport=transport)


def test_missing_key_raises_with_access_hint(monkeypatch):
    monkeypatch.delenv("FANAR_API_KEY", raising=False)
    with pytest.raises(FanarError) as err:
        FanarClient()
    assert err.value.code == "no_api_key" and "api.fanar.qa/request" in err.value.hint


def test_chat_payload_drops_none_params_and_sends_bearer():
    t = FakeTransport(body=json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())
    client(t).chat("Fanar-Sadiq", [{"role": "user", "content": "q"}], madhab=None, max_tokens=50)
    call = t.calls[0]
    assert call["url"].endswith("/v1/chat/completions") and call["method"] == "POST"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert json.loads(call["data"]) == {"model": "Fanar-Sadiq", "messages": [{"role": "user", "content": "q"}],
                                        "max_tokens": 50}


def test_chat_sends_madhab_as_a_list():
    # The API rejects madhab="hanafi" with 422 "Input should be a valid list" (measured 2026-10-20).
    t = FakeTransport(body=json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())
    c = client(t)
    c.chat("Fanar-Sadiq", [{"role": "user", "content": "q"}], madhab="hanafi")
    c.chat("Fanar-Sadiq", [{"role": "user", "content": "q"}], madhab=["maliki", "shafii"])
    assert json.loads(t.calls[0]["data"])["madhab"] == ["hanafi"]
    assert json.loads(t.calls[1]["data"])["madhab"] == ["maliki", "shafii"]


def test_translate_payload():
    t = FakeTransport(body=b'{"text": "x"}')
    client(t).translate("salam", "ar-en")
    assert json.loads(t.calls[0]["data"]) == {"model": "Fanar-3.0-Shaheen-Translate", "text": "salam",
                                              "langpair": "ar-en", "preprocessing": "default"}


def test_entitlement_error_gets_access_hint_and_never_echoes_the_key():
    body = json.dumps({"error": {"code": "invalid_authorization", "message": f"Invalid authorization {KEY}"}})
    t = FakeTransport(status=403, body=body.encode())
    with pytest.raises(FanarError) as err:
        client(t).validate_quotations("text")
    assert err.value.status == 403 and "not entitled" in err.value.hint
    assert KEY not in str(err.value) and KEY not in json.dumps(err.value.as_dict())


def test_rate_limit_error_reports_reset():
    t = FakeTransport(status=429, body=b'{"error": {"code": "rate_limited", "message": "slow down"}}',
                      headers={"x-ratelimit-limit": "20", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "3600"})
    with pytest.raises(FanarError) as err:
        client(t).translate("x", "en-ar")
    assert err.value.rate_limit == {"limit": 20, "remaining": 0, "reset_seconds": 3600}
    assert "retry in 3600 s" in err.value.hint


def test_rate_limit_parsing_is_case_insensitive():
    assert rate_limit_from({"X-RateLimit-Remaining": "19", "X-RateLimit-Limit": "20"}) == {"limit": 20, "remaining": 19}


def test_multipart_body_shape():
    body = multipart_body([("model", "Fanar-Aura-STT-1")], "file", "a.mp3", b"\x00\x01", "BOUNDARY")
    assert body.startswith(b"--BOUNDARY\r\n") and body.endswith(b"--BOUNDARY--\r\n")
    assert b'name="model"\r\n\r\nFanar-Aura-STT-1\r\n' in body and b'filename="a.mp3"' in body


def test_server_registers_every_tool_and_prompt():
    from fanar_mcp.server import mcp

    tools = {t.name for t in asyncio.run(mcp.list_tools())}
    assert tools == {"fanar_list_models", "fanar_chat", "fanar_islamic_qa", "fanar_validate_quotations",
                     "fanar_deep_research", "fanar_deep_research_result", "fanar_translate", "fanar_text_to_speech",
                     "fanar_transcribe", "fanar_generate_image", "fanar_moderate", "fanar_poem"}
    prompts = {p.name for p in asyncio.run(mcp.list_prompts())}
    assert prompts == {"islamic_finance_question", "verify_islamic_quotations"}
