# LUNASTAV — Claude Instructions

## Repository
Auto-deploys to Railway at `lunastav-production.up.railway.app` from the `main` branch.
GitHub: `https://github.com/JakubDlabola/lunastav-orders.git`

## Rules for all Claude sessions

### Branch discipline
- **Never push directly to `main`.** Always create a feature branch, commit there, and open a PR.
- Branch naming: `feature/<short-name>` or `fix/<short-name>`.
- One feature or fix per branch. Docs changes go in the same branch as the code they describe.

### Docs workflow
All documentation lives in `docs/`. Update or create the relevant doc in the same commit as the code change.

| File | Purpose |
|------|---------|
| `docs/CHANGELOG.md` | Prepend a new entry for every PR — never edit old entries |
| `docs/user-guide.md` | Living doc — edit in place (written in Czech) |

Code structure and architecture are documented via comments in the scripts themselves — do not create separate code-overview documents.

**Changelog format:**
```
## [YYYY-MM-DD] — <short title>
- What changed and why (one bullet per logical change)
```

### Security
- `.env` must **never** be committed.
- `SERVICE_KEY = 'lunastav-smlouva-2025'` — never log or expose.
- Test constants (`_SIGN_TEST_PARTNER_ID = 889`, `_SIGN_TEST_EMAIL`) must be removed before go-live.
- Company signee: partner_id=3 (Lukáš Najman), email=lukas.najman@lunastav.cz.

### Odoo connection
- XML-RPC via `execute_kw`. Credentials come from `.env` — never hardcode.
- `TAX_RATE = 1.12`, `COSMETIC_DISC = 3.0` — do not change without updating contract.py too.
- Product code suffixes: `A` = střecha/šikminy, `B` = strop.
- Sign request roles: id=15 Objednatel (client), id=18 Zhotovitel (company).

### Code style
- No unnecessary comments. Only explain the non-obvious.
- Edit existing files rather than creating new ones.
- Python patch scripts (read → replace → write) for sections with Czech characters that confuse the Edit tool.
