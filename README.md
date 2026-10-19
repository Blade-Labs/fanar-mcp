# fanar-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server for [Fanar](https://fanar.qa), the
Arabic-centric generative AI platform built by QCRI at Hamad Bin Khalifa University. It gives any MCP
client (Claude Desktop, Claude Code, Cursor, and other agent harnesses) Fanar's chat models, cited Islamic
question answering, Qur'an and hadith quotation checks, deep research, Arabic-English translation, Arabic
speech in both directions, and image generation.

Built for the Islamic finance community first: ask a fiqh question and get the sources, check every
quotation in a draft before it is published, and translate classical Arabic texts.

> Independent open-source project by Blade Labs. Not affiliated with or endorsed by QCRI or HBKU.
> Status: alpha.

## Tools

| Tool | What it does | Fanar model | Default limit per key |
|---|---|---|---|
| `fanar_list_models` | Models your key may call. Start here: entitlements differ per key | | |
| `fanar_chat` | Chat in Arabic (MSA and dialects) or English, optional step-by-step thinking | Fanar-C-2-27B, Fanar | 50 a minute |
| `fanar_islamic_qa` | Islamic Q&A with references; madhab and source filters on Sadiq-2 | Fanar-Sadiq, Fanar-Sadiq-2 | 50 a minute |
| `fanar_validate_quotations` | Finds and verifies Qur'an and hadith quotations in any text | Fanar-Sadiq-2 | 200 a minute |
| `fanar_deep_research`, `fanar_deep_research_result` | Structured, cited research report on an Islamic topic (minutes) | Fanar-Sadiq-2 | 20 a day |
| `fanar_translate` | Arabic-English translation, including classical texts | Fanar-3.0-Shaheen-Translate | 20 a day |
| `fanar_text_to_speech` | Arabic or English speech in ten voices; Qur'an reciters on Sadiq-TTS | Fanar-Aura-TTS-2 | 20 a day |
| `fanar_transcribe` | Arabic (with dialects) or English speech to text; long-form option | Fanar-Aura-STT-1, STT-LF-1 | 20 a day, 10 long-form |
| `fanar_generate_image` | Culturally aware image generation | Fanar-Oryx-IG-2 | 20 a day |
| `fanar_moderate` | Safety and cultural-awareness scores for a prompt and response | Fanar-Guard-2 | 50 a minute |
| `fanar_poem` | Arabic poetry in the classical tradition | Fanar-Diwan | 50 a minute |

Limits are Fanar's published defaults; every result carries the remaining quota Fanar reports. A tool
that needs a model your key lacks returns a clear error with the link to request access.

Prompts: `islamic_finance_question` (answer with sources and checked quotations) and
`verify_islamic_quotations` (check a text before publishing).

## Get a key

Request API access at <https://api.fanar.qa/request>. Fanar deactivates keys after 90 days without use.

## Install and configure

Requires Python 3.10 or later.

```bash
pip install fanar-mcp          # or run it without installing: uvx fanar-mcp
uvx --from git+https://github.com/Blade-Labs/fanar-mcp fanar-mcp   # straight from GitHub
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "fanar": {
      "command": "uvx",
      "args": ["fanar-mcp"],
      "env": { "FANAR_API_KEY": "your-key" }
    }
  }
}
```

Claude Code:

```bash
claude mcp add fanar -e FANAR_API_KEY=your-key -- uvx fanar-mcp
```

Cursor and other clients take the same command (`uvx fanar-mcp`) and the `FANAR_API_KEY` variable.
For a shared server, run `fanar-mcp --transport streamable-http --port 8765`.

Environment variables: `FANAR_API_KEY` (required), `FANAR_BASE_URL` (default `https://api.fanar.qa/v1`),
`FANAR_MCP_OUTPUT_DIR` (where audio and images are saved; default `~/fanar-mcp-output`).

## Responsible use

- Answers from `fanar_islamic_qa` are cited answers, not fatwas. Show the references, note differences
  between schools, and refer binding questions to a qualified scholar or Shariah board.
- A quotation that `fanar_validate_quotations` leaves untagged was not verified. Treat it as unverified.
- Your use of the API is governed by Fanar's own terms. Read them before using Fanar in a commercial product.
- The server never logs or returns your API key.

## Development

```bash
pip install -e ".[test]"
pytest                        # offline tests, no network or key needed
FANAR_API_KEY=... python scripts/smoke.py   # live check through a real MCP client
```

## License

Apache-2.0. See [LICENSE](LICENSE).
