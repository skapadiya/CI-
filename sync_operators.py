#!/usr/bin/env python3
"""
Sync Conversational Intelligence custom (generative) operators from a PARENT
Twilio account out to all of its SUBACCOUNTS.

What it does, per subaccount:
  1. Authenticates AS the subaccount (parent can read each sub's auth token).
  2. Upserts each operator defined in OPERATORS below:
       - if an operator with the same display_name already exists -> UPDATE it
       - otherwise -> CREATE it

Re-run it any time you change a prompt -> it pushes the new prompt everywhere.
This is a COPY, not a live link: each subaccount gets its own operator id.

To make the operators actually RUN, attach them to each account's Intelligence
Configuration (v3: Configuration -> Rules -> Operators) — see attach_operators.py.

Usage:
    export TWILIO_ACCOUNT_SID=ACxxxxxxxx      # PARENT account sid
    export TWILIO_AUTH_TOKEN=xxxxxxxx         # PARENT auth token
    python sync_operators.py                  # dry-run (prints plan, no writes)
    python sync_operators.py --apply          # actually create/update
"""

import os
import sys
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.rest.intelligence.v3.operator import OperatorList


# Source of truth for the operators. display_name is the match key, keep it stable.
# Optional per-operator keys: output_schema (required for JSON), training_examples,
# context, parameters.
OPERATORS = [
    {
        "display_name": "Escalation Risk",
        "description": "Classifies escalation risk of a conversation.",
        "prompt": (
            "Analyze the transcript and classify the escalation risk as "
            "low, medium, or high. Briefly explain why."
        ),
        "output_format": "TEXT",  # "TEXT", "JSON", or "CLASSIFICATION"
    },
]

# Specific subaccount SIDs to target, or None for all active subaccounts.
ONLY_SUBACCOUNTS = None


def build_language_operator(op):
    """Build the SDK's LanguageOperator model (expects a camelCase payload)."""
    payload = {
        "displayName": op["display_name"],
        "prompt": op["prompt"],
        "outputFormat": op.get("output_format", "TEXT"),
    }
    if op.get("description") is not None:
        payload["description"] = op["description"]
    if op.get("output_schema") is not None:
        payload["outputSchema"] = op["output_schema"]
    if op.get("training_examples") is not None:
        payload["trainingExamples"] = op["training_examples"]
    if op.get("context") is not None:
        payload["context"] = op["context"]
    if op.get("parameters") is not None:
        payload["parameters"] = op["parameters"]
    return OperatorList.LanguageOperator(payload)


def find_existing(client, display_name):
    """Return an existing operator with this display_name, or None."""
    for existing in client.intelligence.v3.operators.list(limit=1000):
        if existing.display_name == display_name:
            return existing
    return None


def sync_subaccount(sub_sid, sub_token, apply, label="account"):
    client = Client(sub_sid, sub_token)
    print(f"\n=== {label} {sub_sid} ===")

    for op in OPERATORS:
        name = op["display_name"]
        language_operator = build_language_operator(op)
        try:
            existing = find_existing(client, name)
        except TwilioRestException as e:
            print(f"  ! could not list operators ({e.status} {e.msg}); "
                  f"is Conversational Intelligence enabled here? Skipping.")
            return

        if existing:
            action = f"UPDATE {name} (id={existing.id})"
            if apply:
                op_obj = client.intelligence.v3.operators(existing.id).update(
                    language_operator=language_operator
                )
                op_id = op_obj.id
            else:
                op_id = existing.id
        else:
            action = f"CREATE {name}"
            if apply:
                op_obj = client.intelligence.v3.operators.create(
                    language_operator=language_operator
                )
                op_id = op_obj.id
            else:
                op_id = "(new)"
        print(f"  {'✓' if apply else '•'} {action}" + (f" -> {op_id}" if apply else ""))


def main():
    apply = "--apply" in sys.argv

    parent_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    parent_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not parent_sid or not parent_token:
        sys.exit("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN (parent account).")

    parent = Client(parent_sid, parent_token)

    if ONLY_SUBACCOUNTS:
        subs = [parent.api.v2010.accounts(s).fetch() for s in ONLY_SUBACCOUNTS]
    else:
        subs = parent.api.v2010.accounts.list(status="active")
        subs = [s for s in subs if s.sid != parent_sid]

    # Parent first, then every subaccount.
    targets = [(parent_sid, parent_token)] + [(s.sid, s.auth_token) for s in subs]

    print(f"Mode: {'APPLY (writing changes)' if apply else 'DRY-RUN (no changes)'}")
    print(f"Operators to sync: {[o['display_name'] for o in OPERATORS]}")
    print(f"Targets: parent + {len(subs)} subaccount(s) = {len(targets)} account(s)")

    for sid, token in targets:
        label = "PARENT" if sid == parent_sid else "subaccount"
        sync_subaccount(sid, token, apply, label=label)

    if not apply:
        print("\nDry-run complete. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
