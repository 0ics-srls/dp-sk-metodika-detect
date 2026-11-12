"""Proc-protocol v1.1 detect for the sk-metodika Sources (Financna sprava sections, PDF sites): no network, deterministic."""
from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from jsonschema import Draft202012Validator

from conftest import Run, invoke_raw
from dp_sk_metodika_detect import detect

Invoke = Callable[..., Run]
SECTIONS = ["metodicke-pokyny", "metodicke-usmernenia", "zavery-komisii", "prehlady-zmluv-zdz"]
DEFAULT_SITES = ["mfsr-spravodajca", "nbs-metodicke"]
UVO_LEAVES = [
    "metodicke-usmernenia-k-zakonu-c-214-2021-zz",
    "metodicke-usmernenia-k-zakonu-c-25-2006-zz",
    "metodicke-usmernenia-k-zakonu-c-343-2015-zz",
    "vseobecne-metodicke-usmernenia-k-zakonu-c-25-2006-zz",
    "vseobecne-metodicke-usmernenia-k-zakonu-c-343-2015-zz",
    "prehlad-vykladovych-stanovisk-uradu-zakon-c-25-2006-z-z",
    "prehlad-vykladovych-stanovisk-uradu-zakon-c-343-2015-z-z",
]
NULLS = {"sections": None, "sites": None, "annoFrom": None, "annoTo": None, "uvoRobotsAck": None, "only": None, "maxDocs": None, "baseUrl": None,
         "delaySeconds": None, "verifyTls": None, "refreshToken": None, "tokenBudget": None, "dryRun": None, "state": None}


@pytest.fixture(autouse=True)
def fixed_year(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "current_year", lambda: 2026)


def keys(run: Run) -> list[str]:
    return [item["key"] for item in run.result["items"]]


def ids(run: Run) -> list[str]:
    return [item["meta"]["itemId"] for item in run.result["items"]]


def test_spec_declares_protocol_11_with_valid_schemas(invoke: Invoke) -> None:
    run = invoke("spec")

    assert run.result["protocol"] == "1.1"
    for name in ("configSchema", "outputSchema"):
        Draft202012Validator.check_schema(run.result[name])
    properties = run.result["configSchema"]["properties"]
    assert {"sections", "sites", "annoFrom", "annoTo", "uvoRobotsAck", "only", "maxDocs", "refreshToken", "state"} <= set(properties)


def test_default_sites_are_mf_sr_2010_to_the_current_year_plus_nbs(invoke: Invoke) -> None:
    run = invoke("run", sites=DEFAULT_SITES)

    years = list(range(2010, 2027))
    assert ids(run) == [f"pdf:mfsr-spravodajca:{y}" for y in years] + ["pdf:nbs-metodicke:all"]
    assert run.result["metrics"] == {"items": 18, "newItems": 18}


def test_annofrom_2024_gives_three_mf_sr_years_and_nbs(invoke: Invoke) -> None:
    run = invoke("run", sites=DEFAULT_SITES, annoFrom=2024)

    assert ids(run) == ["pdf:mfsr-spravodajca:2024", "pdf:mfsr-spravodajca:2025", "pdf:mfsr-spravodajca:2026", "pdf:nbs-metodicke:all"]
    assert keys(run)[0] == "pdf:mfsr-spravodajca:2024|v1"


def test_annofrom_2004_is_clamped_to_2010(invoke: Invoke) -> None:
    run = invoke("run", sites=["mfsr-spravodajca"], annoFrom=2004)

    assert ids(run)[0] == "pdf:mfsr-spravodajca:2010"
    assert len(ids(run)) == 17


def test_annoto_after_the_current_year_is_clamped_to_it(invoke: Invoke) -> None:
    run = invoke("run", sites=["mfsr-spravodajca"], annoFrom=2025, annoTo=2030)

    assert ids(run) == ["pdf:mfsr-spravodajca:2025", "pdf:mfsr-spravodajca:2026"]


def test_years_entirely_before_2010_give_no_mf_sr_item(invoke: Invoke) -> None:
    run = invoke("run", sites=["mfsr-spravodajca", "nbs-metodicke"], annoFrom=2001, annoTo=2005)

    assert ids(run) == ["pdf:nbs-metodicke:all"]


def test_mf_sr_item_meta_and_url(invoke: Invoke) -> None:
    run = invoke("run", sites=["mfsr-spravodajca"], annoFrom=2025, annoTo=2025)

    item = run.result["items"][0]
    assert item["key"] == "pdf:mfsr-spravodajca:2025|v1"
    assert item["meta"] == {"kind": "pdf", "itemId": "pdf:mfsr-spravodajca:2025", "version": "1", "site": "mfsr-spravodajca", "year": 2025}
    assert item["url"] == "https://www.mfsr.sk/sk/financie/financny-spravodajca/2025/"


def test_nbs_is_one_item(invoke: Invoke) -> None:
    run = invoke("run", sites=["nbs-metodicke"])

    assert run.result["items"] == [{
        "key": "pdf:nbs-metodicke:all|v1",
        "url": "https://nbs.sk/dohlad-nad-financnym-trhom/ofs/informacie-pre-odbornu-verejnost/metodicke-usmernenia-stanoviska-a-odporucania/",
        "meta": {"kind": "pdf", "itemId": "pdf:nbs-metodicke:all", "version": "1", "site": "nbs-metodicke"},
    }]


def test_uvo_gives_one_item_per_leaf_constant_and_only_when_listed(invoke: Invoke) -> None:
    run = invoke("run", sites=["uvo-metodicke"])

    assert ids(run) == [f"pdf:uvo-metodicke:{leaf}" for leaf in UVO_LEAVES]
    assert len(UVO_LEAVES) == 7
    assert run.result["items"][0]["meta"] == {"kind": "pdf", "itemId": f"pdf:uvo-metodicke:{UVO_LEAVES[0]}", "version": "1", "site": "uvo-metodicke", "leaf": UVO_LEAVES[0]}
    assert not any("uvo" in i for i in ids(invoke("run", sites=DEFAULT_SITES)))


def test_uvo_items_need_no_robots_ack_in_detect(invoke: Invoke) -> None:
    run = invoke("run", sites=["uvo-metodicke"], uvoRobotsAck=False)

    assert len(run.result["items"]) == 7  # the grab refuses without uvoRobotsAck (D141), detect only lists


def test_sections_default_gives_four_fs_items(invoke: Invoke) -> None:
    run = invoke("run", sections=SECTIONS)

    assert ids(run) == [f"fs:{s}" for s in SECTIONS]
    assert run.result["items"][0]["meta"] == {"kind": "fs", "itemId": "fs:metodicke-pokyny", "version": "1", "section": "metodicke-pokyny"}
    assert run.result["items"][0]["url"].startswith("https://www.financnasprava.sk/")


def test_one_section_is_one_item_and_duplicates_collapse(invoke: Invoke) -> None:
    assert ids(invoke("run", sections=["zavery-komisii", "zavery-komisii"])) == ["fs:zavery-komisii"]


def test_sample_filters_do_not_trim_the_catalog_or_leak_into_meta(invoke: Invoke) -> None:
    run = invoke("run", sections=SECTIONS, maxDocs=2, only=[{"section": "metodicke-pokyny", "docId": "x"}])

    assert len(run.result["items"]) == 4
    assert set(run.result["items"][0]["meta"]) == {"kind", "itemId", "version", "section"}


def test_refresh_token_changes_only_the_version(invoke: Invoke) -> None:
    plain = invoke("run", sections=["metodicke-pokyny"])
    refreshed = invoke("run", sections=["metodicke-pokyny"], refreshToken="2026-11-12")

    version = "1-" + hashlib.sha256(b"2026-11-12").hexdigest()[:8]
    assert keys(refreshed) == [f"fs:metodicke-pokyny|v{version}"]
    assert refreshed.result["items"][0]["meta"]["version"] == version
    assert plain.result["items"][0]["meta"]["itemId"] == refreshed.result["items"][0]["meta"]["itemId"]
    assert invoke("run", sections=["metodicke-pokyny"], refreshToken="").result["items"][0]["meta"]["version"] == "1"


def test_same_state_gives_no_items_and_a_new_refresh_token_gives_all_again(invoke: Invoke) -> None:
    first = invoke("run", sites=DEFAULT_SITES, annoFrom=2025)

    again = invoke("run", sites=DEFAULT_SITES, annoFrom=2025, state=first.result["state"])
    refreshed = invoke("run", sites=DEFAULT_SITES, annoFrom=2025, state=first.result["state"], refreshToken="new")

    assert len(first.result["items"]) == 3
    assert again.result["items"] == []
    assert again.result["metrics"] == {"items": 3, "newItems": 0}
    assert again.result["state"]["seen"] == first.result["state"]["seen"]
    assert len(refreshed.result["items"]) == 3
    assert all("|v1-" in key for key in keys(refreshed))


def test_state_skips_only_the_known_keys(invoke: Invoke) -> None:
    run = invoke("run", sections=SECTIONS, state={"seen": ["fs:zavery-komisii|v1"]})

    assert ids(run) == ["fs:metodicke-pokyny", "fs:metodicke-usmernenia", "fs:prehlady-zmluv-zdz"]
    assert run.result["state"]["seen"][0] == "fs:zavery-komisii|v1"
    assert run.result["metrics"] == {"items": 4, "newItems": 3}


def test_execute_is_an_alias_of_run(invoke: Invoke) -> None:
    assert keys(invoke("execute", sections=["zavery-komisii"])) == ["fs:zavery-komisii|v1"]


def test_check_validates_the_config_only(invoke: Invoke) -> None:
    assert invoke("check", sections=SECTIONS).result == {"ok": True}
    assert invoke("check", sites=DEFAULT_SITES, annoFrom=2030, annoTo=2025).error["code"] == "config_error"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"sections": SECTIONS, "sites": DEFAULT_SITES},
        {"sites": DEFAULT_SITES, "annoFrom": 2025, "annoTo": 2024},
        {"sites": DEFAULT_SITES, "annoFrom": 2030},
        {"sites": DEFAULT_SITES, "annoFrom": "2025"},
        {"sites": DEFAULT_SITES, "annoFrom": True},
        {"sites": DEFAULT_SITES, "annoTo": 1500},
        {"sites": []},
        {"sites": ["ecb"]},
        {"sites": "nbs-metodicke"},
        {"sections": []},
        {"sections": ["dane"]},
        {"sections": SECTIONS, "maxDocs": 0},
        {"sections": SECTIONS, "only": [{"docId": "x"}]},
        {"sites": DEFAULT_SITES, "only": [{"section": "metodicke-pokyny", "docId": "x"}]},
        {"sections": SECTIONS, "delaySeconds": 0.1},
        {"sections": SECTIONS, "uvoRobotsAck": "yes"},
        {"sections": SECTIONS, "verifyTls": "no"},
    ],
)
def test_invalid_config_is_a_config_error(invoke: Invoke, params: dict[str, object]) -> None:
    run = invoke("run", **params)

    assert run.returncode == 1
    assert run.error["code"] == "config_error"


def test_neither_or_both_source_keys_name_the_problem(invoke: Invoke) -> None:
    assert "sections" in invoke("run").error["message"]
    both = invoke("run", sections=SECTIONS, sites=DEFAULT_SITES).error["message"]
    assert "sections" in both
    assert "sites" in both


def test_invalid_state_and_refresh_token_are_config_errors(invoke: Invoke) -> None:
    assert invoke("run", sections=SECTIONS, state={"seen": [1]}).error["code"] == "config_error"
    assert invoke("run", sections=SECTIONS, refreshToken=5).error["code"] == "config_error"


def test_settings_the_host_resolves_to_null_count_as_absent(invoke: Invoke) -> None:
    fs = invoke("run", **{**NULLS, "sections": SECTIONS})
    pdf = invoke("run", **{**NULLS, "sites": DEFAULT_SITES, "annoFrom": 2025})

    assert ids(fs) == [f"fs:{s}" for s in SECTIONS]
    assert ids(pdf) == ["pdf:mfsr-spravodajca:2025", "pdf:mfsr-spravodajca:2026", "pdf:nbs-metodicke:all"]
    assert invoke("run", **NULLS).error["code"] == "config_error"  # nothing at all is still an error
    both_null_but_one = invoke("run", **{**NULLS, "sites": ["nbs-metodicke"], "sections": None})
    assert ids(both_null_but_one) == ["pdf:nbs-metodicke:all"]


def test_every_item_has_kind_url_and_matches_the_output_schema(invoke: Invoke) -> None:
    schema = Draft202012Validator(invoke("spec").result["outputSchema"])
    for params in ({"sections": SECTIONS}, {"sites": ["mfsr-spravodajca", "nbs-metodicke", "uvo-metodicke"]}):
        run = invoke("run", **params)
        assert all(item["meta"]["kind"] in {"fs", "pdf"} and item["url"] and item["meta"]["itemId"] for item in run.result["items"])
        assert list(schema.iter_errors(run.result)) == []


def test_item_keys_are_unique(invoke: Invoke) -> None:
    run = invoke("run", sites=["mfsr-spravodajca", "nbs-metodicke", "uvo-metodicke"])

    assert len(set(keys(run))) == len(keys(run)) == 17 + 1 + 7


def test_current_year_default_matches_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()

    assert detect.current_year() == datetime.now(tz=UTC).year


def test_protocol_loop_emits_one_error_line_for_a_bad_request() -> None:
    run = invoke_raw("not json\n")

    assert run.returncode == 1
    assert [line["type"] for line in run.lines] == ["error"]


def test_protocol_loop_unknown_action_and_terminate() -> None:
    run = invoke_raw(json.dumps({"_action": "frobnicate", "_meta": {"executionId": "e"}}) + "\n" + json.dumps({"_action": "terminate", "_meta": {"executionId": "e"}}) + "\n")

    assert [line["type"] for line in run.lines] == ["error", "result"]


def test_stdout_carries_protocol_events_only(invoke: Invoke) -> None:
    run = invoke("run", sections=["zavery-komisii"])

    assert all(line.get("type") in {"progress", "result", "error"} for line in run.lines)
    assert io.StringIO(run.stdout).read().count("\n") == len(run.lines)
