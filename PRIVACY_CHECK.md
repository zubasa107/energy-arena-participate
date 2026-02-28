# Privacy / secrets check (energy-arena-participate)

**Last check:** No hardcoded API keys or other secrets found in this repository.

- All references to `ENTSOE_API_KEY` and `ARENA_API_KEY` are either:
  - Placeholders (e.g. `your_entsoe_api_key_here`, `YOUR_KEY`), or
  - Reading from environment variables (`os.environ.get(...)`).
- `.env` is listed in `.gitignore` and is not tracked.
- No real API keys, passwords, or tokens appear in any committed file.

**Recommendation:** Keep API keys only in environment variables or in a local `.env` file (never committed).
