"""Tiny rule interpreter for ``tenant_services[].hooks`` ("cheaper
increments" workflow hooks).

We keep the engine deliberately small — three named hook points
(``pre_consent``, ``pre_submit``, ``post_submit``) and a flat list of
``{"if": <cond>, "then": <action>}`` rules per point. This covers 90% of
what tenants ask for ("if fee > 10000 send for manual review", "if
country is X show a warning before consent", "after submit email
compliance@…") without committing the platform to a full declarative
workflow engine.

Schema
======

::

    "hooks": {
      "pre_consent": [
        {
          "if": {"field": "country", "in": ["IN", "BD"]},
          "then": {"action": "show_message",
                   "message": "Processing for this country takes 3 weeks."}
        }
      ],
      "pre_submit": [
        {
          "if": {"field": "fee_amount", "gt": 10000},
          "then": {"action": "require_review",
                   "reason": "high_value_application"}
        }
      ],
      "post_submit": [
        {
          "if": true,
          "then": {"action": "send_email",
                   "to": "compliance@example.com",
                   "subject": "New {{service}} application"}
        }
      ]
    }

Conditions
==========

A condition is one of:
  * ``true`` / ``false`` / ``null`` — literal (null is treated as true so
    omitting ``if`` means "always fire")
  * ``{"and": [<cond>, …]}`` — every nested condition must hold
  * ``{"or":  [<cond>, …]}`` — at least one must hold
  * ``{"not": <cond>}`` — negation
  * Field predicate, with ``"field": "<key>"`` and ONE of:
        ``eq``, ``neq``, ``in``, ``not_in``,
        ``gt``, ``lt``, ``gte``, ``lte``,
        ``matches`` (regex), ``exists`` (truthy / falsy)

Anything we don't recognise evaluates to ``False`` so a malformed rule
silently fails closed rather than crashing the flow.

Actions
=======

The interpreter never *executes* actions — it only returns the list of
matched actions back to the caller. Action semantics live with the
caller (``application_flow.process_flow``), because they're tightly tied
to the bot's state machine.

Supported action names (callers must handle these):
  * ``show_message``  — append text to the bot's next reply
  * ``block``         — short-circuit the flow with a message
  * ``require_review`` — mark the application for manual review
  * ``send_email``    — fire a notification (post_submit only)
  * ``set_field``     — override a form field value before submit
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# Hook points known to the framework. Anything not in this set is
# ignored — typos in tenant config don't silently misfire.
KNOWN_HOOK_POINTS = ("pre_consent", "pre_submit", "post_submit")

# Actions the framework recognises. The interpreter doesn't execute
# them — it just hands them back. Callers should defend against unknown
# names so a tenant config typo doesn't break the flow.
KNOWN_ACTIONS = (
    "show_message",
    "block",
    "require_review",
    "send_email",
    "set_field",
)


def evaluate_hooks(
    hooks: Optional[Sequence[Dict[str, Any]]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return the list of triggered action payloads from ``hooks``.

    Rules are evaluated in declared order. All matching rules contribute
    their action to the output list; the caller decides what to do with
    each one (some actions, like ``block``, short-circuit by convention
    at the call site).
    """
    if not hooks:
        return []
    out: List[Dict[str, Any]] = []
    for idx, rule in enumerate(hooks):
        if not isinstance(rule, dict):
            logger.warning("[hooks] rule %d is not an object — skipping", idx)
            continue
        cond = rule.get("if", True)
        try:
            matched = _eval_condition(cond, context)
        except Exception as exc:  # malformed regex etc.
            logger.warning("[hooks] rule %d condition raised %s — skipping", idx, exc)
            continue
        if not matched:
            continue
        then = rule.get("then")
        if not isinstance(then, dict):
            logger.warning("[hooks] rule %d matched but has no action — skipping", idx)
            continue
        out.append(then)
    return out


def first_action(
    actions: Sequence[Dict[str, Any]],
    name: str,
) -> Optional[Dict[str, Any]]:
    """Find the first action with ``action == name`` in a result list.

    Handy when the caller only cares about one action type at a hook
    point (e.g. ``block`` is short-circuiting — there's no point in
    processing later actions once one has fired)."""
    for a in actions:
        if a.get("action") == name:
            return a
    return None


# ── condition evaluator ─────────────────────────────────────────────


def _eval_condition(cond: Any, ctx: Dict[str, Any]) -> bool:
    # Literals
    if cond is None or cond is True:
        return True
    if cond is False:
        return False
    if not isinstance(cond, dict):
        return False

    # Boolean combinators
    if "and" in cond:
        nested = cond.get("and") or []
        return all(_eval_condition(c, ctx) for c in nested)
    if "or" in cond:
        nested = cond.get("or") or []
        return any(_eval_condition(c, ctx) for c in nested)
    if "not" in cond:
        return not _eval_condition(cond.get("not"), ctx)

    # Field predicate
    field = cond.get("field")
    if field is None:
        return False
    value = _lookup(field, ctx)

    if "eq" in cond:
        return value == cond["eq"]
    if "neq" in cond:
        return value != cond["neq"]
    if "in" in cond:
        return value in (cond["in"] or [])
    if "not_in" in cond:
        return value not in (cond["not_in"] or [])
    if "gt" in cond:
        return _num(value) > _num(cond["gt"])
    if "lt" in cond:
        return _num(value) < _num(cond["lt"])
    if "gte" in cond:
        return _num(value) >= _num(cond["gte"])
    if "lte" in cond:
        return _num(value) <= _num(cond["lte"])
    if "matches" in cond:
        pattern = str(cond["matches"])
        return bool(re.search(pattern, str(value or "")))
    if "exists" in cond:
        present = value is not None and value != ""
        return present == bool(cond["exists"])

    # Unknown predicate → False (fail closed)
    return False


def _lookup(field: str, ctx: Dict[str, Any]) -> Any:
    """Dotted-path lookup, so a rule can read ``user.email`` or
    ``form_data.country``. Returns ``None`` for any missing segment."""
    cur: Any = ctx
    for part in str(field).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _num(v: Any) -> float:
    """Coerce to float for comparisons. Strings that don't parse → -inf
    so the rule deterministically fails ``gt`` etc. (rather than raising)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("-inf")
