"""MCP server for Fanar, QCRI's Arabic-centric generative AI platform (https://api.fanar.qa).

Run with an API key in FANAR_API_KEY:  fanar-mcp            (stdio, for Claude Desktop, Claude Code, Cursor...)
                                       fanar-mcp --transport streamable-http --port 8765
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import os
import pathlib
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .client import FanarClient, FanarError

INSTRUCTIONS = """Tools for Fanar, the Arabic-centric AI platform built by QCRI at Hamad Bin Khalifa University.
- Call fanar_list_models first: each key is entitled to a different set of models.
- fanar_islamic_qa gives answers grounded in cited sources. Present them as cited answers with their
  references, never as a fatwa or a ruling, and say when the sources show a difference between schools.
- fanar_validate_quotations checks Qur'an and hadith quotations. A quotation it leaves untagged was not
  verified; say so rather than repeating it as authentic.
- Limits per key: chat about 50 requests a minute; translation, speech, transcription and images about
  20 a day; deep research about 20 a day. Rate-limit headroom is returned with each result.
- Audio and image files are saved under FANAR_MCP_OUTPUT_DIR and returned as file paths."""

mcp = FastMCP("fanar", instructions=INSTRUCTIONS)

Voice = Literal["Abdulrahman", "Amelia", "Emily", "Hamad", "Harry", "Huda", "Jake", "Jasim", "Noor", "Radwa"]
Reciter = Literal["abdul-basit", "maher-al-muaiqly", "mahmoud-al-husary"]


def _client() -> FanarClient:
    try:
        return FanarClient()
    except FanarError as exc:
        raise ToolError(f"{exc.message}: {exc.hint}") from None


def _run(call):
    try:
        return call()
    except FanarError as exc:
        detail = exc.message + (f" | {exc.hint}" if exc.hint else "")
        raise ToolError(f"Fanar returned {exc.status or 'no response'} ({exc.code}): {detail}") from None


def _output_path(kind: str, ext: str, filename: str | None) -> pathlib.Path:
    root = pathlib.Path(os.environ.get("FANAR_MCP_OUTPUT_DIR") or pathlib.Path.home() / "fanar-mcp-output")
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = pathlib.Path(filename).name if filename else f"fanar-{kind}-{stamp}.{ext}"
    if not pathlib.Path(name).suffix:
        name = f"{name}.{ext}"
    return root / name


def _image_ext(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "bin"


@mcp.tool()
def fanar_list_models() -> dict:
    """List the Fanar models this API key may call. Entitlements differ per key: for example
    Fanar-Sadiq-2, which powers the quotation validator and deep research, must be enabled by Fanar."""
    resp = _run(lambda: _client().models())
    body = resp.json()
    listed = body.get("data") or body.get("models") or []
    return {"models": [m.get("id") for m in listed if isinstance(m, dict)], "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_chat(prompt: str, model: str = "Fanar-C-2-27B", system: str | None = None, thinking: bool = False,
               max_tokens: int = 1024, temperature: float | None = None) -> dict:
    """Chat with a Fanar language model. Fanar-C-2-27B is the Fanar 2.0 27B model for Arabic (MSA and
    Gulf, Levantine and Egyptian dialects) and English; "Fanar" is the default alias. Set thinking=true
    for step-by-step reasoning. About 50 requests a minute."""
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    resp = _run(lambda: _client().chat(model, messages, max_tokens=max_tokens, temperature=temperature,
                                       enable_thinking=thinking or None))
    body = resp.json()
    message = body["choices"][0]["message"]
    return {"model": body.get("model", model), "answer": message.get("content"), "usage": body.get("usage"),
            "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_islamic_qa(question: str, model: str = "Fanar-Sadiq", madhab: list[str] | str | None = None,
                     restrict_to_islamic: bool | None = None, preferred_sources: list[str] | None = None,
                     exclude_sources: list[str] | None = None, max_tokens: int = 1024) -> dict:
    """Ask Fanar-Sadiq an Islamic question and get an answer grounded in cited sources such as the
    Qur'an, hadith collections and fatwa collections. Show the references with the answer and present
    it as a cited answer, never as a fatwa. Fanar-Sadiq-2 adds madhab and source filters when your key
    is entitled to it; madhab is a list such as ["hanafi"], from all, hanafi, maliki, shafii and hanbali.
    About 50 requests a minute."""
    resp = _run(lambda: _client().chat(
        model, [{"role": "user", "content": question}], max_tokens=max_tokens, madhab=madhab,
        restrict_to_islamic=restrict_to_islamic, preferred_sources=preferred_sources,
        exclude_sources=exclude_sources))
    body = resp.json()
    message = body["choices"][0]["message"]
    return {"model": body.get("model", model), "answer": message.get("content"),
            "references": message.get("references") or [], "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_validate_quotations(text: str) -> dict:
    """Detect and verify Qur'an and hadith quotations inside any text: an LLM answer, a draft, an
    article. Verified quotations come back tagged and linked to canonical sources; a quotation left
    untagged could not be confirmed and must be treated as unverified. Requires Fanar-Sadiq-2 on the
    key. About 200 requests a minute."""
    resp = _run(lambda: _client().validate_quotations(text))
    body = resp.json()
    return {"validated_text": body.get("text"), "id": body.get("id"), "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_deep_research(topic: str, depth: Literal["quick", "standard", "comprehensive"] = "quick",
                        web_search: bool = False) -> dict:
    """Start a Fanar-Sadiq-2 deep research job: a structured report on an Islamic topic, with headings
    and cited sources. It takes minutes (quick about 3-6, standard about 7-10); poll it with
    fanar_deep_research_result. Requires Fanar-Sadiq-2 on the key. About 20 jobs a day."""
    resp = _run(lambda: _client().deep_research_start(topic, depth=depth, web_search=web_search))
    body = resp.json() if resp.body else {}
    return {"job": body, "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_deep_research_result(job_id: str) -> dict:
    """Fetch the status, progress or finished report of a Fanar-Sadiq-2 deep research job."""
    resp = _run(lambda: _client().deep_research_get(job_id))
    return {"job": resp.json(), "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_translate(text: str, langpair: Literal["ar-en", "en-ar"],
                    model: Literal["Fanar-3.0-Shaheen-Translate", "Fanar-Shaheen-MT-1"] = "Fanar-3.0-Shaheen-Translate",
                    preprocessing: Literal["default", "preserve_html", "preserve_whitespace",
                                           "preserve_whitespace_and_html"] = "default") -> dict:
    """Translate between Arabic and English with Fanar's Shaheen models, including classical Arabic such
    as hadith and fiqh texts. About 20 requests a day; keep each request under about 4,000 words."""
    resp = _run(lambda: _client().translate(text, langpair, model=model, preprocessing=preprocessing))
    body = resp.json()
    return {"model": model, "langpair": langpair, "translation": body.get("text"), "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_text_to_speech(text: str, voice: Voice = "Hamad",
                         model: Literal["Fanar-Aura-TTS-2", "Fanar-Sadiq-TTS-1"] = "Fanar-Aura-TTS-2",
                         response_format: Literal["mp3", "wav"] = "mp3", quran_reciter: Reciter | None = None,
                         filename: str | None = None) -> dict:
    """Speak Arabic or English text with a Fanar Aura voice and save it as an audio file; returns the
    file path. Qur'an recitation by a named reciter needs Fanar-Sadiq-TTS-1. About 20 requests a day."""
    resp = _run(lambda: _client().speech(text, voice, model=model, response_format=response_format,
                                         quran_reciter=quran_reciter))
    path = _output_path("speech", response_format, filename)
    path.write_bytes(resp.body)
    return {"path": str(path), "bytes": len(resp.body), "voice": voice, "model": model, "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_transcribe(audio_path: str, long_form: bool = False,
                     output: Literal["text", "srt", "json"] = "text") -> dict:
    """Transcribe Arabic (including dialects) or English audio from a local file with Fanar Aura.
    long_form=true uses the long-audio model (about 10 requests a day); otherwise about 20 a day."""
    if not pathlib.Path(audio_path).is_file():
        raise ToolError(f"no such audio file: {audio_path}")
    model = "Fanar-Aura-STT-LF-1" if long_form else "Fanar-Aura-STT-1"
    resp = _run(lambda: _client().transcribe(audio_path, model=model, fmt=output))
    body = resp.json()
    return {"model": model, "transcript": body.get(output if output != "text" else "text"),
            "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_generate_image(prompt: str, revise: bool = True, filename: str | None = None) -> dict:
    """Generate a culturally aware image with Fanar Oryx and save it; returns the file path and the
    prompt as Fanar revised it. About 20 requests a day."""
    resp = _run(lambda: _client().image(prompt, revise=revise))
    item = (resp.json().get("data") or [{}])[0]
    data = base64.b64decode(item.get("b64_json") or b"")
    if not data:
        raise ToolError("Fanar returned no image data")
    path = _output_path("image", _image_ext(data), filename)
    path.write_bytes(data)
    return {"path": str(path), "bytes": len(data), "revised_prompt": item.get("revised_prompt"),
            "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_moderate(prompt: str, response: str) -> dict:
    """Score a prompt and response pair with FanarGuard for safety and cultural awareness, in Arabic or
    English. Requires Fanar-Guard-2 on the key."""
    resp = _run(lambda: _client().moderate(prompt, response))
    return {**resp.json(), "rate_limit": resp.rate_limit}


@mcp.tool()
def fanar_poem(prompt: str) -> dict:
    """Compose Arabic poetry in the classical tradition with Fanar-Diwan. Requires Fanar-Diwan on the key."""
    resp = _run(lambda: _client().poem(prompt))
    body = resp.json()
    return {"poem": body.get("poem"), "rate_limit": resp.rate_limit}


@mcp.prompt()
def islamic_finance_question(question: str) -> str:
    """Answer an Islamic finance question with cited sources and verified quotations."""
    return (f"Answer this Islamic finance question: {question}\n\n"
            "1. Call fanar_islamic_qa with the question.\n"
            "2. If the answer quotes the Qur'an or hadith, call fanar_validate_quotations on it when available, "
            "and mark any quotation it leaves untagged as unverified.\n"
            "3. Reply with the answer, then its references. Say it is a cited answer, not a fatwa, and note any "
            "difference between schools that the sources show. For a binding ruling, refer the reader to a "
            "qualified scholar or Shariah board.")


@mcp.prompt()
def verify_islamic_quotations(text: str) -> str:
    """Check every Qur'an and hadith quotation in a text before it is published."""
    return ("Call fanar_validate_quotations on the text below. List each quotation as verified, with its "
            "source, or unverified. Recommend removing or sourcing every unverified quotation before the text "
            f"is published.\n\nText:\n{text}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fanar-mcp", description="MCP server for the Fanar API")
    parser.add_argument("--transport", choices=("stdio", "streamable-http", "sse"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    mcp.settings.host, mcp.settings.port = args.host, args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
