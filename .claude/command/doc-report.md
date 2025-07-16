---

title: "/lib-dossier ‑ Library & API Integration Dossier" 

< description: > Slash‑command that gathers authoritative docs, real‑world code examples, and best‑practice guidance for any Python package or HTTP API you supply as <\$ARGUMENTS>. Returns a single, structured Markdown dossier optimised for later reuse by Claude Code.

# -----------------------------------------------------------------------------

# MCP TOOL ACCESS (whitelisted for this command)

# -----------------------------------------------------------------------------

# These names match the endpoints defined in your \~/.claude.json → "mcp.servers".

# Update the hostnames/ports to match your own infrastructure.

allowed-tools:

- mcp\_\_context7\_\_get\_snippets        # Official docs, changelogs, code blocks
- mcp\_\_fetch\_\_get                    # Raw README / files over HTTP(S)
- mcp\_\_exa\_\_search                   # Search GitHub for usage examples
- mcp\_\_playwright\_\_open              # Headless browser for JS‑rendered docs
- mcp\_\_playwright\_\_scrape            # Extract HTML/Markdown after navigation

# Example \~/.claude.json fragment

# {

# "mcp": {

# "servers": {

# "context7":  "[https://ctx7.acme.dev/api](https://ctx7.acme.dev/api)",

# "fetch":     "[https://fetch.acme.dev](https://fetch.acme.dev)",

# "exa":       "[https://exa.acme.dev](https://exa.acme.dev)",

# "playwright":"[https://browser.acme.dev](https://browser.acme.dev)"

# }

# }

# }

---

## 📑 Command Definition (drop into \~/.claude/commands/lib-dossier.md)

````markdown
> Using **Context7**, **Fetch**, **Exa Search**, and, if necessary, **Playwright**,
> compile a **Library Integration Dossier** for `$ARGUMENTS`.
>
> ### Step 1 – Gather Sources
> 1. Context7 → latest stable docs, version history, breaking‑change notes.
> 2. Fetch    → README, docs/ index, CHANGELOG, LICENSE directly from GitHub.
> 3. Exa      → up to 15 real‑world snippets (Python, stars≥25, ≤200 lines).
> 4. Playwright (fallback) → scrape “Quick‑Start” and “Getting Started” pages.
>
> ### Step 2 – Synthesize Dossier (Markdown)
> Output **exactly** this structure:
>
> ```yaml
> title: "$ARGUMENTS — Implementation Cheat‑Sheet"
> sections:
>   - Overview               # one‑sentence description
>   - Installation           # pip/uv command, system reqs, env vars
>   - Quick Start            # ≤ 30‑line runnable snippet
>   - Core API Map           # table [class|func|endpoint → purpose] + version notes
>   - Extended Recipes       # ≥ 3 sourced snippets, each with source URL comment
>   - Best Practices         # bullets: perf, security, testing
>   - Troubleshooting FAQ    # top 5 errors + fixes (from GitHub Issues/StackO)
>   - Edge Cases & Pitfalls  # nuanced behaviours, gotchas
>   - Version Matrix         # chart of breaking changes by version
>   - Further Reading        # official docs, blog posts, videos, communities
> metadata:
>   lib: $ARGUMENTS
>   latest_version: <auto>
>   generated: <UTC‑ISO8601>
>   mcp_sources: [context7, fetch, exa_search, playwright]
> ```
>
> ### Step 3 – Validate & Deliver
> * Verify code imports exist in `latest_version`.
> * HEAD‑check all outbound links (HTTP 2xx).
> * Flag unresolved gaps with “⚠️ TODO”.
>
> Return the dossier as Markdown. No additional commentary.
````

---

### Example Invocation

```bash
> /lib-dossier fastapi
> /lib-dossier requests==2.32.0
```

### What Each MCP Tool Provides

| Tool                     | Purpose                                                   | Typical Payload |
| ------------------------ | --------------------------------------------------------- | --------------- |
| context7.get\_snippets   | Official docs, changelog entries, version‑scoped snippets | Markdown/Code   |
| fetch.get                | Raw files (README, docs/index.md) via direct HTTP(S)      | Plain text      |
| exa.search               | Live GitHub code examples with repo URLs & star counts    | Code blocks     |
| playwright.open + scrape | JS‑rendered docs sites; extract HTML → Markdown           | Markdown/HTML   |

---

### Safety & Quality Notes

- Context7 is authoritative—prefer its content over third‑party blogs.
- Exclude deprecated APIs; indicate replacement methods.
- Do **not** embed API keys or secrets in examples.
- If no official docs are located, abort after Step 1 with an error message.

---

### Sample Output Snippet (excerpt)

````markdown
## Quick Start
```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/ping")
async def ping():
    return {"status": "ok"}
````

Run `uv`; visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the Swagger UI. \`\`
