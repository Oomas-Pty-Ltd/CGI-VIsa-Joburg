"""Non-input step types for the application_flow state machine.

The chatbot's `collecting` state walks a list of ``fields`` and asks the
user one question per field. Sprint 4E adds two field types that DON'T
prompt the user — they're evaluated automatically between user-facing
questions:

  * ``conditional`` — evaluate a predicate on prior form data and either
    continue, or short-circuit the form (skip the remaining input fields
    and jump to document upload). Useful for "South African nationals
    get visa free — skip the rest of the form" patterns.

  * ``api_call`` — make an HTTP call (URL/body rendered with ``{{var}}``
    substitution from the collected form data), optionally store the
    response back into form_data, then advance.

A field with no ``type`` (or ``type: "input"``) is the legacy behaviour:
ask the user, validate, store. Operators add the new types via the
super-admin services CRUD; no migration is required because ``fields``
is already stored as a free-form list of dicts.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("services.flow_steps")

# Same syntax as services.bot_config's template renderer so operators
# learn one substitution scheme. Only top-level keys — nested paths are
# out of scope (form data is a flat dict of strings).
_TPL_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Conservative HTTP timeout. Operators can raise per-call via api_config,
# but never exceed this absolute ceiling — a misconfigured api_call must
# not be able to wedge a chat conversation indefinitely.
_MAX_TIMEOUT_SECONDS = 30.0
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _render(template: Any, data: Dict[str, Any]) -> Any:
    """Recursively substitute {{var}} placeholders in any string values
    inside the template (string, dict, list — leaves other types alone)."""
    if isinstance(template, str):
        return _TPL_RE.sub(lambda m: str(data.get(m.group(1), m.group(0))), template)
    if isinstance(template, dict):
        return {k: _render(v, data) for k, v in template.items()}
    if isinstance(template, list):
        return [_render(v, data) for v in template]
    return template


def _eval_condition(condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
    """Evaluate a single-operator predicate against the collected form data.

    Supported shapes (exactly one operator per condition):
      {"field": "nationality", "equals":     "south african"}
      {"field": "nationality", "not_equals": "indian"}
      {"field": "nationality", "in":         ["south african", "lesotho"]}
      {"field": "passport_number", "matches": "^[A-Z]\\d{7}$"}
    """
    field_key = condition.get("field")
    if not field_key:
        return False
    actual = data.get(field_key, "")
    actual_str = str(actual).strip().lower() if actual is not None else ""

    if "equals" in condition:
        return actual_str == str(condition["equals"]).strip().lower()
    if "not_equals" in condition:
        return actual_str != str(condition["not_equals"]).strip().lower()
    if "in" in condition:
        opts = condition["in"]
        if not isinstance(opts, list):
            return False
        return any(actual_str == str(o).strip().lower() for o in opts)
    if "matches" in condition:
        try:
            return bool(re.search(str(condition["matches"]), str(actual), re.IGNORECASE))
        except re.error:
            logger.warning("Invalid regex in conditional: %r", condition["matches"])
            return False
    return False


@dataclass
class StepResult:
    """Outcome of evaluating a non-input step.

    ``advance`` is either ``"continue"`` (move to the next field) or
    ``"skip_to_docs"`` (jump past every remaining input field to start
    document upload). ``form_updates`` is merged into ``flow.data`` so
    api_call results can be referenced by later fields.

    Failures are intentionally non-fatal — a broken api_call returns
    ``advance="continue"`` with a ``note`` so the user is never stuck
    on a backend hiccup. Look at logs to diagnose."""
    advance: str = "continue"
    form_updates: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


async def _execute_conditional(field_def: Dict[str, Any], data: Dict[str, Any]) -> StepResult:
    condition  = field_def.get("condition") or {}
    on_match   = field_def.get("on_match")    or "continue"
    on_no_match = field_def.get("on_no_match") or "continue"
    if on_match not in ("continue", "skip_to_docs") or on_no_match not in ("continue", "skip_to_docs"):
        logger.warning(
            "conditional step %r has unknown on_match/on_no_match; defaulting to continue",
            field_def.get("key"),
        )
        on_match = on_match if on_match in ("continue", "skip_to_docs") else "continue"
        on_no_match = on_no_match if on_no_match in ("continue", "skip_to_docs") else "continue"
    matched = _eval_condition(condition, data)
    return StepResult(advance=on_match if matched else on_no_match)


async def _execute_api_call(field_def: Dict[str, Any], data: Dict[str, Any]) -> StepResult:
    cfg     = field_def.get("api_config") or {}
    method  = (cfg.get("method") or "GET").upper()
    url     = _render(cfg.get("url") or "", data)
    headers = _render(cfg.get("headers") or {}, data)
    body    = _render(cfg.get("body") or {}, data)
    store_as = cfg.get("store_response_as")

    timeout = float(cfg.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS)
    timeout = min(max(timeout, 1.0), _MAX_TIMEOUT_SECONDS)

    if not url:
        return StepResult(advance="continue", note="api_call missing url; step skipped")

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers or None)
            elif method in ("POST", "PUT", "PATCH"):
                # Send body as JSON if it's a dict/list, else as raw text.
                if isinstance(body, (dict, list)):
                    resp = await client.request(method, url, headers=headers or None, json=body)
                else:
                    resp = await client.request(method, url, headers=headers or None, content=str(body))
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers or None)
            else:
                return StepResult(advance="continue", note=f"unsupported method {method!r}")
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # Don't block the user — log and let the form continue. If the
        # response is needed downstream, that field will be empty and any
        # validation on it will catch the issue at the natural point.
        logger.warning(
            "api_call step %r → %s %s failed: %s",
            field_def.get("key"), method, url, exc,
        )
        return StepResult(advance="continue", note=f"api_call failed: {exc}")

    if store_as:
        try:
            payload = resp.json()
        except ValueError:
            payload = resp.text
        return StepResult(advance="continue", form_updates={store_as: payload})
    return StepResult(advance="continue")


async def execute_step(field_def: Dict[str, Any], data: Dict[str, Any]) -> Optional[StepResult]:
    """If ``field_def`` is a non-input step, evaluate and return the result.
    Returns ``None`` for input fields (the caller should ask the user)."""
    step_type = (field_def.get("type") or "input").lower()
    if step_type == "input":
        return None
    if step_type == "conditional":
        return await _execute_conditional(field_def, data)
    if step_type == "api_call":
        return await _execute_api_call(field_def, data)
    logger.warning(
        "Unknown field type %r on field %r; treating as input.",
        step_type, field_def.get("key"),
    )
    return None


VALID_STEP_TYPES = ("input", "conditional", "api_call")


def validate_field_definition(field_def: Dict[str, Any]) -> Optional[str]:
    """Return an error message if the field is structurally invalid for its
    declared type, or None if it's well-formed. Called by the super-admin
    CRUD before persisting."""
    step_type = (field_def.get("type") or "input").lower()
    if step_type not in VALID_STEP_TYPES:
        return f"unknown field type {step_type!r}; expected one of {VALID_STEP_TYPES}"

    if step_type == "input":
        if not (field_def.get("question") or "").strip():
            return f"input field {field_def.get('key')!r} requires a non-empty question"
        return None

    if step_type == "conditional":
        cond = field_def.get("condition")
        if not isinstance(cond, dict) or not cond.get("field"):
            return f"conditional field {field_def.get('key')!r} requires a condition with a 'field' key"
        if not any(op in cond for op in ("equals", "not_equals", "in", "matches")):
            return f"conditional field {field_def.get('key')!r} condition needs one of equals/not_equals/in/matches"
        for slot in ("on_match", "on_no_match"):
            v = field_def.get(slot)
            if v is not None and v not in ("continue", "skip_to_docs"):
                return f"conditional field {field_def.get('key')!r} {slot} must be 'continue' or 'skip_to_docs'"
        return None

    if step_type == "api_call":
        cfg = field_def.get("api_config")
        if not isinstance(cfg, dict) or not cfg.get("url"):
            return f"api_call field {field_def.get('key')!r} requires api_config.url"
        method = (cfg.get("method") or "GET").upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            return f"api_call field {field_def.get('key')!r} api_config.method must be GET/POST/PUT/PATCH/DELETE"
        return None

    return None
