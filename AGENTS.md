# AGENTS.md

Guidance for any AI agent (Codex, Cursor, Claude Code, Gemini CLI and others) that is asked to use or work on
fanar-mcp, an MCP server for QCRI's Fanar API. This project is independent of QCRI and is not affiliated with
or endorsed by it.

## If a person asked you to use Fanar through this server

**Key.** The person needs their own Fanar API key from https://api.fanar.qa. Use it only through the
`FANAR_API_KEY` variable. Never print it, commit it or share it: Fanar's terms forbid sharing access
credentials.

**Set it up.**
- Any MCP client: the command is `uvx fanar-mcp`, with `FANAR_API_KEY` set.
- Claude Code: `claude mcp add fanar -e FANAR_API_KEY=your-key -- uvx fanar-mcp`
- Codex (`~/.codex/config.toml`):

  ```toml
  [mcp_servers.fanar]
  command = "uvx"
  args = ["fanar-mcp"]
  env = { FANAR_API_KEY = "your-key" }
  ```

**Start with `fanar_list_models`.** Entitlements differ from key to key. The quotation validator and deep
research, for example, need Fanar-Sadiq-2 to be enabled on that key.

**Rules when you use it.**
1. `fanar_islamic_qa` returns cited answers, not fatwas. Show the references, note where scholars differ, and
   leave binding rulings to qualified scholars.
2. Run `fanar_validate_quotations` on any Qur'an or hadith quotation before it reaches the person. Treat any
   quotation it leaves untagged as unverified.
3. Respect the rate limits in the README. The heavier tools allow 20 calls a day.
4. Fanar's terms let QCRI use prompts and outputs. Keep private client data out unless the person accepts that.
5. Do not publish Fanar performance or evaluation results, and do not use Fanar's name or logo in advertising,
   without QCRI's written consent (Fanar API licence 2.4 and 5.1(e)).

## If you are working on this repository

- Python 3.10 or later: `pip install -e ".[test]"`, then `pytest`. Tests mock the API. For a live check, run
  `FANAR_API_KEY=... python scripts/smoke.py`.
- The `mcp` dependency is pinned below 2, because version 2 renamed FastMCP.
- Releases: a `v*` tag publishes to PyPI by trusted publishing, then to the MCP Registry through
  `server.json`.
- Never commit keys. Licence: Apache-2.0.
