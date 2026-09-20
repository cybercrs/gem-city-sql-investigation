"""Anonymous, validated URL progress for the SQL activity."""

from __future__ import annotations

import base64
import json
import secrets
import zlib
from collections.abc import MutableMapping
from typing import Any

from .case_data import (
    AMOUNT_CAUSE_OPTIONS,
    AMOUNT_FIELD_OPTIONS,
    MISSING_CAUSE_OPTIONS,
    MISSING_REPAIR_OPTIONS,
    READ_QUESTIONS,
    ROUTES,
)
from .engine import evaluate_amount, evaluate_custom_query, evaluate_missing, evaluate_reading

SNAPSHOT_PARAM = "progress"
SNAPSHOT_VERSION = 3
MAX_TOKEN_LENGTH = 20_000
MAX_JSON_BYTES = 40_000


def activity_defaults() -> dict[str, Any]:
    return {
        "si_stage": 0,
        "si_shuffle_seed": secrets.randbits(63),
        "si_drafts": {
            "reading": {},
            "missing": {},
            "amount": {},
        },
        "si_reading": {},
        "si_missing": {},
        "si_amount": {},
        "si_custom": {
            route: {"draft": "", "submitted": "", "passed": False}
            for route in ROUTES
        },
        "si_attempts": {},
        "si_scroll_to_top": False,
    }


def _encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def _decode(token: str) -> object:
    padding = "=" * (-len(token) % 4)
    compressed = base64.b64decode(token + padding, altchars=b"-_", validate=True)
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES or decompressor.unconsumed_tail:
        raise ValueError("Snapshot too large")
    raw += decompressor.flush(MAX_JSON_BYTES + 1 - len(raw))
    if len(raw) > MAX_JSON_BYTES or decompressor.unused_data:
        raise ValueError("Invalid snapshot")
    return json.loads(raw.decode("utf-8"))


def _response_map(raw: object, allowed: dict[str, tuple[str, ...]]) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) - set(allowed):
        raise ValueError("Invalid response map")
    for key, value in raw.items():
        if not isinstance(value, str) or value not in allowed[key]:
            raise ValueError("Invalid response")
    return dict(raw)


def validate_snapshot(raw: object) -> dict[str, Any]:
    expected = {"v", "s", "z", "d", "r", "m", "a", "c", "t"}
    if not isinstance(raw, dict) or set(raw) != expected or raw["v"] != SNAPSHOT_VERSION:
        raise ValueError("Unsupported snapshot")
    stage = raw["s"]
    if type(stage) is not int or not 0 <= stage <= 5:
        raise ValueError("Invalid stage")
    shuffle_seed = raw["z"]
    if type(shuffle_seed) is not int or not 0 <= shuffle_seed < 2**63:
        raise ValueError("Invalid shuffle seed")

    reading = _response_map(raw["r"], {item_id: options for item_id, _, options, _, _ in READ_QUESTIONS})
    missing = _response_map(raw["m"], {"cause": MISSING_CAUSE_OPTIONS, "repair": MISSING_REPAIR_OPTIONS})
    amount = _response_map(raw["a"], {"cause": AMOUNT_CAUSE_OPTIONS, "field": AMOUNT_FIELD_OPTIONS})

    draft_specs = {
        "reading": (1, {item_id: options for item_id, _, options, _, _ in READ_QUESTIONS}, reading),
        "missing": (2, {"cause": MISSING_CAUSE_OPTIONS, "repair": MISSING_REPAIR_OPTIONS}, missing),
        "amount": (3, {"cause": AMOUNT_CAUSE_OPTIONS, "field": AMOUNT_FIELD_OPTIONS}, amount),
    }
    raw_drafts = raw["d"]
    if not isinstance(raw_drafts, dict) or set(raw_drafts) != set(draft_specs):
        raise ValueError("Invalid draft groups")
    drafts: dict[str, dict[str, str]] = {}
    for group, (group_stage, choices_by_key, submitted_response) in draft_specs.items():
        raw_group = raw_drafts[group]
        if not isinstance(raw_group, dict) or set(raw_group) - set(choices_by_key):
            raise ValueError("Invalid draft answers")
        normalized_group: dict[str, str] = {}
        for key, value in raw_group.items():
            if not isinstance(value, str) or value not in choices_by_key[key]:
                raise ValueError("Invalid draft choice")
            normalized_group[key] = value
        if group_stage > stage and normalized_group:
            raise ValueError("Future draft is not allowed")
        if submitted_response and normalized_group != submitted_response:
            raise ValueError("Draft and submitted response disagree")
        drafts[group] = normalized_group

    raw_custom = raw["c"]
    if not isinstance(raw_custom, dict) or set(raw_custom) != set(ROUTES):
        raise ValueError("Invalid custom-query groups")
    custom: dict[str, dict[str, Any]] = {}
    for route in ROUTES:
        entry = raw_custom[route]
        if not isinstance(entry, dict) or set(entry) != {"d", "q", "p"}:
            raise ValueError("Invalid custom-query state")
        draft = entry["d"]
        submitted = entry["q"]
        passed = entry["p"]
        if not isinstance(draft, str) or len(draft) > 8_000:
            raise ValueError("Invalid custom query draft")
        if not isinstance(submitted, str) or len(submitted) > 8_000 or type(passed) is not bool:
            raise ValueError("Invalid custom query submission")
        if stage < 4 and (draft or submitted or passed):
            raise ValueError("Future custom-query work is not allowed")
        if submitted and submitted != draft:
            raise ValueError("Draft and submitted query disagree")
        if passed and not evaluate_custom_query(route, submitted)[0]:
            raise ValueError("Saved custom query does not satisfy the assignment")
        custom[route] = {"draft": draft, "submitted": submitted, "passed": passed}

    attempts = raw["t"]
    if not isinstance(attempts, dict) or set(attempts) - {"reading", "missing", "amount", "accounting", "audit"}:
        raise ValueError("Invalid attempts")
    if any(type(value) is not int or not 1 <= value <= 99 for value in attempts.values()):
        raise ValueError("Invalid attempt count")

    if stage >= 2 and not evaluate_reading(reading)[0]:
        raise ValueError("Reading stage is incomplete")
    if stage >= 3 and not evaluate_missing(missing)[0]:
        raise ValueError("Missing-record stage is incomplete")
    if stage >= 4 and not evaluate_amount(amount)[0]:
        raise ValueError("Amount stage is incomplete")
    if stage >= 5 and not all(custom[route]["passed"] for route in ROUTES):
        raise ValueError("Custom query stage is incomplete")

    return {
        "si_stage": stage,
        "si_shuffle_seed": shuffle_seed,
        "si_drafts": drafts,
        "si_reading": reading,
        "si_missing": missing,
        "si_amount": amount,
        "si_custom": custom,
        "si_attempts": dict(attempts),
    }


def snapshot_from_state(state: MutableMapping[str, Any]) -> dict[str, Any]:
    return {
        "v": SNAPSHOT_VERSION,
        "s": state["si_stage"],
        "z": state["si_shuffle_seed"],
        "d": state["si_drafts"],
        "r": state["si_reading"],
        "m": state["si_missing"],
        "a": state["si_amount"],
        "c": {
            route: {
                "d": state["si_custom"][route]["draft"],
                "q": state["si_custom"][route]["submitted"],
                "p": state["si_custom"][route]["passed"],
            }
            for route in ROUTES
        },
        "t": state["si_attempts"],
    }


def encode_state(state: MutableMapping[str, Any]) -> str:
    return _encode(snapshot_from_state(state))


def decode_snapshot(token: object) -> dict[str, Any] | None:
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    try:
        return validate_snapshot(_decode(token))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, zlib.error):
        return None


def restore_session_state(state: MutableMapping[str, Any], token: object) -> bool:
    restored = decode_snapshot(token)
    if restored is None:
        return False
    state.update(restored)
    return True


def sync_progress_query(state: MutableMapping[str, Any], query_params: MutableMapping[str, Any]) -> None:
    token = encode_state(state)
    current = query_params.get(SNAPSHOT_PARAM)
    if isinstance(current, list):
        current = current[0] if current else None
    if current != token:
        query_params[SNAPSHOT_PARAM] = token


def reset_saved_progress(state: MutableMapping[str, Any], query_params: MutableMapping[str, Any]) -> None:
    for key in list(state):
        if key.startswith("si_") or key.startswith("widget_si_"):
            del state[key]
    state.update(activity_defaults())
    query_params[SNAPSHOT_PARAM] = encode_state(state)


def record_attempt(state: MutableMapping[str, Any], key: str) -> None:
    attempts = dict(state["si_attempts"])
    attempts[key] = attempts.get(key, 0) + 1
    state["si_attempts"] = attempts
