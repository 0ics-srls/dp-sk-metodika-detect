"""Detect of the sk-metodika Sources: validates the config, emits catalog items, never uses the network (P81b-04).

One pipeline serves two Source types; the kind of an item is its ``meta.kind``:

* ``fs`` (Source type fs-sections, told by the key ``sections``): one item per Financna sprava section (``fs:metodicke-pokyny``);
* ``pdf`` (Source type pdf-sites, told by the key ``sites``): MF SR Financny spravodajca = one item per year ``annoFrom..annoTo`` clamped to 2010..current year
  (``pdf:mfsr-spravodajca:2026``), NBS = one item (``pdf:nbs-metodicke:all``), UVO = one item per known leaf (``pdf:uvo-metodicke:<leaf>``) and only when the
  Source lists ``uvo-metodicke``. Detect only lists; the grab refuses UVO without ``uvoRobotsAck`` (D141).

Item key = ``<itemId>|v<version>``; the version is ``1`` and a non-blank ``refreshToken`` makes it ``1-<hash8>``. How many documents a listing
holds is found out by grab. The sample filters (``only``, ``maxDocs``) and the other settings are not detect's business:
they never trim the Catalog and do not travel in ``meta``.
Unset (null) settings are absent: the Host sends null for a Source key the type does not declare.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, TypeGuard
from urllib.parse import urlencode

from v11 import ProcErrorCode

SEEN_LIMIT = 2000
MAX_ITEMS = 2000
BASE_VERSION = "1"
MFSR_FIRST_YEAR = 2010
MIN_YEAR = 1900
MAX_YEAR = 2200
MIN_DELAY_SECONDS = 0.6

FS_BASE = "https://www.financnasprava.sk/sk/danovi-a-colni-specialisti/dane"
MFSR_BASE = "https://www.mfsr.sk/sk/financie/financny-spravodajca"
NBS_URL = "https://nbs.sk/dohlad-nad-financnym-trhom/ofs/informacie-pre-odbornu-verejnost/metodicke-usmernenia-stanoviska-a-odporucania/"
UVO_BASE = "https://www.uvo.gov.sk/metodika-vzdelavanie/metodicke-usmernenia-a-vykladove-stanoviska"

SECTIONS = ("metodicke-pokyny", "metodicke-usmernenia", "zavery-komisii", "prehlady-zmluv-zdz")
SECTION_PATHS = {
    "metodicke-pokyny": "metodicke-pokyny",
    "metodicke-usmernenia": "metodicke-usmernenia",
    "zavery-komisii": "zavery-zo-zasadnuti-MFSR",
    "prehlady-zmluv-zdz": "prehlady-zmluv-zdz",
}
SITES = ("mfsr-spravodajca", "nbs-metodicke", "uvo-metodicke")
UVO_LEAVES = (
    "metodicke-usmernenia-k-zakonu-c-214-2021-zz",
    "metodicke-usmernenia-k-zakonu-c-25-2006-zz",
    "metodicke-usmernenia-k-zakonu-c-343-2015-zz",
    "vseobecne-metodicke-usmernenia-k-zakonu-c-25-2006-zz",
    "vseobecne-metodicke-usmernenia-k-zakonu-c-343-2015-zz",
    "prehlad-vykladovych-stanovisk-uradu-zakon-c-25-2006-z-z",
    "prehlad-vykladovych-stanovisk-uradu-zakon-c-343-2015-z-z",
)
FS_KEYS = ("sections",)
PDF_KEYS = ("sites",)


class DetectError(Exception):
    """A protocol error: ``code`` is one of the three v1.1 codes."""

    def __init__(self, code: ProcErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _config_error(message: str) -> DetectError:
    return DetectError(ProcErrorCode.CONFIG_ERROR, message)


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def current_year() -> int:
    """The year used when a Source gives no range; a function so that tests can fix it."""
    return datetime.now(tz=UTC).year


def validate_refresh_token(token: Any) -> str | None:
    if token is None or token == "":
        return None
    if not isinstance(token, str):
        raise _config_error("refreshToken must be a string")
    return token


def validate_state(state: Any) -> dict[str, Any] | None:
    if state is None:
        return None
    seen = state.get("seen") if isinstance(state, dict) else None
    if not isinstance(state, dict) or (seen is not None and not (isinstance(seen, list) and all(isinstance(s, str) for s in seen))):
        raise _config_error("state must be an object {seen: [string]}")
    return state


def version_of(refresh_token: str | None) -> str:
    if not refresh_token:
        return BASE_VERSION
    return f"{BASE_VERSION}-{hashlib.sha256(refresh_token.encode('utf-8')).hexdigest()[:8]}"


def _with_refresh(url: str, version: str, refresh_token: str | None) -> str:
    if not refresh_token:
        return url
    return url + ("&" if "?" in url else "?") + urlencode({"refresh": version})


def resolve_source(params: dict[str, Any]) -> str:
    """``fs`` or ``pdf``, told by the key only one Source type has; neither or both is a config error."""
    fs = [key for key in FS_KEYS if key in params]
    pdf = [key for key in PDF_KEYS if key in params]
    if fs and pdf:
        msg = f"the config mixes the two Source types: {fs} belongs to fs-sections, {pdf} to pdf-sites"
        raise _config_error(msg)
    if not fs and not pdf:
        raise _config_error("the Source type cannot be told: give sections (fs-sections) or sites (pdf-sites)")
    return "fs" if fs else "pdf"


def _choice(params: dict[str, Any], name: str, allowed: tuple[str, ...]) -> list[str]:
    """The distinct values of an enum array setting, in the given order."""
    value = params.get(name)
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v in allowed for v in value):
        raise _config_error(f"{name} must be a non-empty array of {list(allowed)}")
    return list(dict.fromkeys(value))


def _years(params: dict[str, Any]) -> list[int]:
    """The MF SR years: annoFrom (default 2010) .. annoTo (default the current year), clamped to 2010..current year."""
    now = current_year()
    first = params.get("annoFrom", MFSR_FIRST_YEAR)
    last = params.get("annoTo", now)
    for name, value in (("annoFrom", first), ("annoTo", last)):
        if not _is_int(value) or not MIN_YEAR <= value <= MAX_YEAR:
            raise _config_error(f"{name} must be an integer year {MIN_YEAR}..{MAX_YEAR}, got {value!r}")
    if first > last:
        raise _config_error(f"annoFrom ({first}) must not be after annoTo ({last})")
    return list(range(max(first, MFSR_FIRST_YEAR), min(last, now) + 1))


def _validate_common(params: dict[str, Any], only_key: str, allowed: tuple[str, ...]) -> None:
    """Types of the settings detect does not use (the Manifest passes them to every step); a wrong type is caught early by ``check``."""
    max_docs = params.get("maxDocs")
    if max_docs is not None and (not _is_int(max_docs) or max_docs < 1):
        raise _config_error("maxDocs must be an integer >= 1")
    only = params.get("only")
    if only is not None:
        ok = isinstance(only, list) and all(
            isinstance(o, dict) and o.get(only_key) in allowed and isinstance(o.get("docId"), str) and o["docId"] for o in only
        )
        if not ok:
            raise _config_error(f"only must be an array of {{{only_key}, docId}} ({only_key}: {' | '.join(allowed)})")
    delay = params.get("delaySeconds")
    if delay is not None and (isinstance(delay, bool) or not isinstance(delay, int | float) or delay < MIN_DELAY_SECONDS):
        raise _config_error(f"delaySeconds must be a number >= {MIN_DELAY_SECONDS}")
    for name in ("verifyTls", "uvoRobotsAck", "dryRun"):
        if params.get(name) is not None and not isinstance(params[name], bool):
            raise _config_error(f"{name} must be a boolean")
    budget = params.get("tokenBudget")
    if budget is not None and (not _is_int(budget) or budget < 0):
        raise _config_error("tokenBudget must be an integer >= 0")
    base_url = params.get("baseUrl")
    if base_url is not None and not isinstance(base_url, str):
        raise _config_error("baseUrl must be a string")


def _fs_items(params: dict[str, Any], version: str, token: str | None) -> list[dict[str, Any]]:
    sections = _choice(params, "sections", SECTIONS)
    _validate_common(params, "section", SECTIONS)
    items: list[dict[str, Any]] = []
    for section in sections:
        item_id = f"fs:{section}"
        meta = {"kind": "fs", "itemId": item_id, "version": version, "section": section}
        items.append({"key": f"{item_id}|v{version}", "url": _with_refresh(f"{FS_BASE}/{SECTION_PATHS[section]}", version, token), "meta": meta})
    return items


def _pdf_items(params: dict[str, Any], version: str, token: str | None) -> list[dict[str, Any]]:
    sites = _choice(params, "sites", SITES)
    years = _years(params)
    _validate_common(params, "site", SITES)
    found: list[tuple[str, str, dict[str, Any]]] = []  # (item id, url, meta extras)
    for site in sites:
        if site == "mfsr-spravodajca":
            found.extend((f"pdf:{site}:{year}", f"{MFSR_BASE}/{year}/", {"site": site, "year": year}) for year in years)
        elif site == "nbs-metodicke":
            found.append((f"pdf:{site}:all", NBS_URL, {"site": site}))
        else:
            found.extend((f"pdf:{site}:{leaf}", f"{UVO_BASE}/{leaf}", {"site": site, "leaf": leaf}) for leaf in UVO_LEAVES)
    return [
        {"key": f"{item_id}|v{version}", "url": _with_refresh(url, version, token), "meta": {"kind": "pdf", "itemId": item_id, "version": version, **extras}}
        for item_id, url, extras in found
    ]


def build_found(params: dict[str, Any], refresh_token: str | None) -> list[dict[str, Any]]:
    """Every item of the Source config, in stable order (validates the whole config)."""
    version = version_of(refresh_token)
    items = _fs_items(params, version, refresh_token) if resolve_source(params) == "fs" else _pdf_items(params, version, refresh_token)
    if len(items) > MAX_ITEMS:
        raise _config_error(f"at most {MAX_ITEMS} items per Source, got {len(items)}")
    return items


def build_run_result(found: list[dict[str, Any]], state_in: dict[str, Any] | None) -> dict[str, Any]:
    """Items = those whose key is not in state.seen; state keeps the newest SEEN_LIMIT keys."""
    seen = list((state_in or {}).get("seen") or [])
    known = set(seen)
    new = [item for item in found if item["key"] not in known]
    seen_out = (seen + [item["key"] for item in new])[-SEEN_LIMIT:]
    return {
        "items": new,
        "state": {"seen": seen_out},
        "metrics": {"items": len(found), "newItems": len(new)},
        "checks": [{"name": "items_found", "passed": len(found) > 0, "severity": "error"}],
    }


CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "sections": {"type": "array", "minItems": 1, "items": {"enum": list(SECTIONS)}, "uniqueItems": True, "description": "fs-sections: sections"},
        "sites": {"type": "array", "minItems": 1, "items": {"enum": list(SITES)}, "uniqueItems": True, "description": "pdf-sites: MF SR, NBS, UVO"},
        "annoFrom": {"type": "integer", "minimum": MIN_YEAR, "description": "first MF SR year (default and minimum 2010)"},
        "annoTo": {"type": "integer", "minimum": MIN_YEAR, "description": "last MF SR year (default and maximum the current year)"},
        "uvoRobotsAck": {"type": ["boolean", "null"]},
        "only": {"type": ["array", "null"]},
        "maxDocs": {"type": ["integer", "null"], "minimum": 1},
        "baseUrl": {"type": ["string", "null"]},
        "delaySeconds": {"type": ["number", "null"], "minimum": MIN_DELAY_SECONDS},
        "verifyTls": {"type": ["boolean", "null"]},
        "refreshToken": {"type": ["string", "null"], "description": "change it to fetch every item again"},
        "tokenBudget": {"type": ["integer", "null"], "minimum": 0},
        "dryRun": {"type": ["boolean", "null"]},
        "state": {"type": ["object", "null"], "properties": {"seen": {"type": "array", "items": {"type": "string"}}}},
    },
    "additionalProperties": True,
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["items", "state", "metrics", "checks"],
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "required": ["key", "url", "meta"], "properties": {
            "key": {"type": "string", "minLength": 1}, "url": {"type": "string", "minLength": 1},
            "meta": {"type": "object", "required": ["kind", "itemId", "version"], "properties": {
                "kind": {"enum": ["fs", "pdf"]}, "itemId": {"type": "string"}, "version": {"type": "string"}}}}}},
        "state": {"type": "object", "required": ["seen"], "properties": {"seen": {"type": "array", "items": {"type": "string"}}}},
        "metrics": {"type": "object", "properties": {"items": {"type": "integer"}, "newItems": {"type": "integer"}}},
        "checks": {"type": "array"},
    },
}
