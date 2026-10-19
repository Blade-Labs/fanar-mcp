"""Live smoke test: start fanar-mcp over stdio, list its tools and call them against the real API.

Needs FANAR_API_KEY. Uses a few requests of the daily quotas (translation, speech, transcription, image).
Usage: python scripts/smoke.py [--skip-media]
"""
import asyncio
import json
import os
import pathlib
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = pathlib.Path(__file__).resolve().parents[1]


async def main(skip_media: bool) -> int:
    out = tempfile.mkdtemp(prefix="fanar-mcp-smoke-")
    env = dict(os.environ, FANAR_MCP_OUTPUT_DIR=out, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    params = StdioServerParameters(command=sys.executable, args=["-m", "fanar_mcp"], env=env)
    calls = [
        ("fanar_list_models", {}),
        ("fanar_islamic_qa", {"question": "What is the difference between mudarabah and musharakah?",
                              "max_tokens": 300}),
        ("fanar_translate", {"text": "Profit is shared as agreed; loss falls on the capital provider.",
                             "langpair": "en-ar"}),
        ("fanar_validate_quotations", {"text": "Allah has permitted trade and forbidden riba (2:275)."}),
    ]
    if not skip_media:
        calls += [
            ("fanar_text_to_speech", {"text": "السلام عليكم",
                                      "voice": "Huda", "filename": "smoke-tts.mp3"}),
            ("fanar_transcribe", {"audio_path": str(pathlib.Path(out) / "smoke-tts.mp3")}),
            ("fanar_generate_image", {"prompt": "A calm Doha skyline at dawn, watercolour",
                                      "filename": "smoke-image"}),
        ]
    failures = 0
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print(f"tools listed: {len(tools.tools)}")
        for name, args in calls:
            result = await session.call_tool(name, args)
            text = result.content[0].text if result.content else ""
            status = "ERROR" if result.isError else "ok"
            if result.isError and name != "fanar_validate_quotations":
                failures += 1
            try:
                shown = json.dumps(json.loads(text), ensure_ascii=False)
            except ValueError:
                shown = text
            print(f"{name}: {status}: {shown[:420]}")
    print(f"output dir: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main("--skip-media" in sys.argv)))
