# dp-sk-metodika-detect

Detect class of the `sk-metodika` package (open-lex-it phase 81b). Proc-protocol 1.1 (stdin NDJSON: `spec`, `check`, `run`, alias `execute`), Python 3.12,
standard library only. Pure: no network, no clock except `current_year()`.

The Source type is told by the key only it has: `sections` (fs-sections) or `sites` (pdf-sites); neither or both is a `config_error`. Settings that arrive as
JSON null are absent (the Host resolves an undeclared Source key to null).

| Config | Items |
|---|---|
| `sections` | one per section: `fs:<section>`, `meta {kind: "fs", itemId, version, section}` |
| `sites` has `mfsr-spravodajca` | one per year `annoFrom..annoTo` (annoFrom default 2010, clamped to 2010..current year, annoTo default and maximum the current year): `pdf:mfsr-spravodajca:<yyyy>`, `meta {kind: "pdf", itemId, version, site, year}` |
| `sites` has `nbs-metodicke` | `pdf:nbs-metodicke:all`, `meta {kind: "pdf", itemId, version, site}` |
| `sites` has `uvo-metodicke` | one per leaf constant (7): `pdf:uvo-metodicke:<leaf>`, `meta {..., site, leaf}`; detect only lists, the grab refuses UVO without `uvoRobotsAck` (D141) |

`annoFrom > annoTo` (as given) is a `config_error`. Item key `<itemId>|v<version>`, `version` = `1` or `1-<first 8 hex of sha256(refreshToken)>`. The state
`seen` skips every key already emitted. Sample filters (`only`, `maxDocs`) and the other settings are validated by type only and do not enter `meta`.
Conformance file: `dp-sk-metodika/tests/conformance/detect.json`.

## Develop

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -m "not integration" tests
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy .
docker build -f Dockerfile.test .
```

Test image (`docker build -f Dockerfile.test .`, measured 2026-11-12): 348 MB on disk, build 0.25 min with `--no-cache`, the container runs 49 tests green offline.
