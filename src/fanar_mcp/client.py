"""A small, dependency-free client for the Fanar API (https://api.fanar.qa).

Fanar is the Arabic-centric generative AI platform built by QCRI at Hamad Bin Khalifa University.
This client covers the public v1 surface: chat (including Fanar-Sadiq Islamic Q&A), the Sadiq
quotation validator and deep research, translation, speech, transcription, images, moderation and
poetry. It never logs or returns the API key.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://api.fanar.qa/v1"
USER_AGENT = "fanar-mcp/0.1.0"
ACCESS_URL = "https://api.fanar.qa/request"

Transport = Callable[[str, str, dict, "bytes | None", float], "tuple[int, dict, bytes]"]


class FanarError(Exception):
    """An API or configuration error with a short, actionable hint. Never carries the key."""

    def __init__(self, status: int, code: str, message: str, hint: str = "", rate_limit: dict | None = None):
        self.status, self.code, self.message, self.hint = status, code, message, hint
        self.rate_limit = rate_limit or {}
        super().__init__(f"Fanar error {status} {code}: {message}" + (f" ({hint})" if hint else ""))

    def as_dict(self) -> dict:
        out = {"error": self.code, "status": self.status, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        if self.rate_limit:
            out["rate_limit"] = self.rate_limit
        return out


@dataclass
class FanarResponse:
    status: int
    headers: dict = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    @property
    def rate_limit(self) -> dict:
        return rate_limit_from(self.headers)


def rate_limit_from(headers: dict) -> dict:
    """Fanar reports quota on every rate-limited response; keep only what is present."""
    lowered = {str(k).lower(): v for k, v in (headers or {}).items()}
    out = {}
    for name, key in (("limit", "x-ratelimit-limit"), ("remaining", "x-ratelimit-remaining"),
                      ("reset_seconds", "x-ratelimit-reset")):
        value = lowered.get(key)
        if value not in (None, ""):
            try:
                out[name] = int(float(value))
            except ValueError:
                out[name] = value
    return out


def multipart_body(fields: list[tuple[str, str]], file_field: str, filename: str, payload: bytes,
                   boundary: str) -> bytes:
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode() + payload + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def _urllib_transport(method: str, url: str, headers: dict, data: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read()


class FanarClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 180.0,
                 transport: Transport | None = None):
        key = (api_key if api_key is not None else os.environ.get("FANAR_API_KEY", "")).strip()
        if not key:
            raise FanarError(0, "no_api_key", "FANAR_API_KEY is not set",
                             f"request a key at {ACCESS_URL} and export it as FANAR_API_KEY")
        self._key = key
        self.base_url = (base_url or os.environ.get("FANAR_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._transport = transport or _urllib_transport

    # ---- transport -------------------------------------------------------------------------------
    def request(self, method: str, path: str, json_body: Any = None, data: bytes | None = None,
                content_type: str | None = None) -> FanarResponse:
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json", "User-Agent": USER_AGENT}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        try:
            status, resp_headers, body = self._transport(method, self.base_url + path, headers, data, self.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FanarError(0, "unreachable", f"could not reach {self.base_url}: {type(exc).__name__}") from None
        if status >= 400:
            raise self._error(status, resp_headers, body)
        return FanarResponse(status, resp_headers, body)

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "[redacted]")

    def _error(self, status: int, headers: dict, body: bytes) -> FanarError:
        code, message = f"http_{status}", ""
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
            err = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
            if isinstance(err, dict):
                code = str(err.get("code") or code)
                message = str(err.get("message") or err.get("detail") or "")
            elif isinstance(err, str):
                message = err
        except (ValueError, AttributeError):
            message = body.decode("utf-8", "replace")[:300]
        message = self._scrub(message)[:500]
        limits = rate_limit_from(headers)
        if status == 401:
            hint = "Fanar rejected the key; check FANAR_API_KEY. Fanar deactivates keys after 90 days without use."
        elif status in (403, 422) and ("authoriz" in message.lower() or "authoriz" in code.lower()):
            hint = f"this key is not entitled to that model or endpoint; ask Fanar for access ({ACCESS_URL})"
        elif status == 429:
            hint = ("rate limit reached" + (f"; retry in {limits['reset_seconds']} s" if "reset_seconds" in limits
                                            else "") + ". Defaults: chat 50 a minute; translation, speech and images 20 a day")
        else:
            hint = ""
        return FanarError(status, code, message or f"HTTP {status}", hint, limits)

    # ---- endpoints -------------------------------------------------------------------------------
    def models(self) -> FanarResponse:
        return self.request("GET", "/models")

    def chat(self, model: str, messages: list[dict], **params: Any) -> FanarResponse:
        body = {"model": model, "messages": messages}
        body.update({k: v for k, v in params.items() if v is not None})
        # The API types madhab as a list and rejects a bare string with 422 (measured 2026-10-20).
        if isinstance(body.get("madhab"), str):
            body["madhab"] = [body["madhab"]]
        return self.request("POST", "/chat/completions", json_body=body)

    def translate(self, text: str, langpair: str, model: str = "Fanar-3.0-Shaheen-Translate",
                  preprocessing: str = "default") -> FanarResponse:
        return self.request("POST", "/translations", json_body={
            "model": model, "text": text, "langpair": langpair, "preprocessing": preprocessing})

    def speech(self, text: str, voice: str, model: str = "Fanar-Aura-TTS-2", response_format: str = "mp3",
               quran_reciter: str | None = None) -> FanarResponse:
        body = {"model": model, "input": text, "voice": voice, "response_format": response_format}
        if quran_reciter:
            body["quran_reciter"] = quran_reciter
        return self.request("POST", "/audio/speech", json_body=body)

    def transcribe(self, audio_path: str, model: str = "Fanar-Aura-STT-1", fmt: str = "text") -> FanarResponse:
        path = pathlib.Path(audio_path)
        boundary = uuid.uuid4().hex
        body = multipart_body([("model", model), ("format", fmt)], "file", path.name, path.read_bytes(), boundary)
        return self.request("POST", "/audio/transcriptions", data=body,
                            content_type=f"multipart/form-data; boundary={boundary}")

    def image(self, prompt: str, model: str = "Fanar-Oryx-IG-2", revise: bool = True) -> FanarResponse:
        return self.request("POST", "/images/generations", json_body={"model": model, "prompt": prompt, "revise": revise})

    def validate_quotations(self, text: str, model: str = "Fanar-Sadiq-2") -> FanarResponse:
        return self.request("POST", "/sadiq/validate", json_body={"model": model, "text": text})

    def deep_research_start(self, topic: str, depth: str = "quick", web_search: bool = False,
                            model: str = "Fanar-Sadiq-2") -> FanarResponse:
        return self.request("POST", "/sadiq/deep-research", json_body={
            "model": model, "input": topic, "depth": depth, "web_search": web_search, "background": True})

    def deep_research_get(self, job_id: str) -> FanarResponse:
        return self.request("GET", f"/sadiq/deep-research/{job_id}")

    def moderate(self, prompt: str, response: str, model: str = "Fanar-Guard-2") -> FanarResponse:
        return self.request("POST", "/moderations", json_body={"model": model, "prompt": prompt, "response": response})

    def poem(self, prompt: str, model: str = "Fanar-Diwan") -> FanarResponse:
        return self.request("POST", "/poems/generations", json_body={"model": model, "prompt": prompt})
