#!/usr/bin/env python3
"""
Wire the synced operators into each account's Intelligence Configuration so they
actually RUN. v3 model: Configuration -> Rules -> Operators.

Per account:
  - find the operator by display name (created earlier by sync_operators.py)
  - PARENT: add a new rule (operator + CONVERSATION_END trigger) to the
    existing configuration, preserving any rules already on it.
  - SUBACCOUNT: create a configuration (if none), then add the same rule.

Dry-run by default; pass --apply to write.

Usage:
    TWILIO_ACCOUNT_SID=ACparent TWILIO_AUTH_TOKEN=token \
        python attach_operators.py            # dry-run
    TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... \
        python attach_operators.py --apply
"""

import os
import sys
from twilio.rest import Client
from twilio.rest.intelligence.v3.configuration import ConfigurationList

OPERATOR_DISPLAY_NAME = "Escalation Risk"   # must match the synced operator
TRIGGER_ON = "CONVERSATION_END"             # COMMUNICATION | CONVERSATION_END | CONVERSATION_INACTIVE

# Parent config to extend, or "" to auto-pick the account's first config.
PARENT_CONFIG_ID = ""
# Name used when creating a config on an account that has none.
NEW_CONFIG_DISPLAY_NAME = "Conversation Intelligence"


def find_operator_id(client, display_name):
    for op in client.intelligence.v3.operators.list(limit=1000):
        if op.display_name == display_name:
            return op.id
    return None


def rule_has_operator(rule, operator_id):
    for op in (rule.get("operators") or []):
        if (op.get("id") if isinstance(op, dict) else getattr(op, "id", None)) == operator_id:
            return True
    return False


def new_rule_payload(operator_id):
    return {
        "operators": [{"id": operator_id}],
        "triggers": [{"on": TRIGGER_ON}],
        "actions": [],
    }


def process_account(label, client, operator_id, apply, existing_config_id=None):
    print(f"\n=== {label} ===")

    # Locate or create the configuration
    config = None
    if existing_config_id:
        try:
            config = client.intelligence.v3.configurations.get(existing_config_id).fetch()
        except Exception as e:
            print(f"  ! configured id not found ({e}); will look for any config")
    if config is None:
        configs = client.intelligence.v3.configurations.list(limit=50)
        config = configs[0] if configs else None

    if config is None:
        print(f"  no configuration -> CREATE '{NEW_CONFIG_DISPLAY_NAME}' with 1 rule")
        if apply:
            req = ConfigurationList.CreateConfigurationRequest({
                "displayName": NEW_CONFIG_DISPLAY_NAME,
                "rules": [new_rule_payload(operator_id)],
            })
            created = client.intelligence.v3.configurations.create(
                create_configuration_request=req
            )
            print(f"  ✓ created config {created.id} with operator {operator_id}")
        else:
            print(f"  • would create config and add operator {operator_id}")
        return

    # Config exists -> append a rule (preserving existing rules)
    existing_rules = list(config.rules or [])
    print(f"  config {config.id} '{config.display_name}' has {len(existing_rules)} rule(s)")

    if any(rule_has_operator(r, operator_id) for r in existing_rules):
        print(f"  = operator {operator_id} already in a rule; nothing to do")
        return

    if len(existing_rules) >= 5:
        print("  ! config already has 5 rules (max); cannot add. Skipping.")
        return

    updated_rules = existing_rules + [new_rule_payload(operator_id)]
    print(f"  {'✓' if apply else '•'} add rule (operator {operator_id}, on={TRIGGER_ON}) "
          f"-> {len(updated_rules)} rule(s) total")
    if apply:
        req = ConfigurationList.UpdateConfigurationRequest({
            "displayName": config.display_name,
            "rules": updated_rules,
        })
        client.intelligence.v3.configurations.get(config.id).update(
            update_configuration_request=req
        )
        print(f"  ✓ updated config {config.id}")


def main():
    apply = "--apply" in sys.argv
    parent_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    parent_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not parent_sid or not parent_token:
        sys.exit("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN (parent account).")

    parent = Client(parent_sid, parent_token)
    subs = [s for s in parent.api.v2010.accounts.list(status="active")
            if s.sid != parent_sid]

    print(f"Mode: {'APPLY (writing changes)' if apply else 'DRY-RUN (no changes)'}")
    print(f"Operator: '{OPERATOR_DISPLAY_NAME}'  trigger: {TRIGGER_ON}")

    # Parent
    op_id = find_operator_id(parent, OPERATOR_DISPLAY_NAME)
    if not op_id:
        print(f"\n=== PARENT {parent_sid} ===\n  ! operator '{OPERATOR_DISPLAY_NAME}' not found")
    else:
        process_account(f"PARENT {parent_sid}", parent, op_id, apply,
                         existing_config_id=PARENT_CONFIG_ID)

    # Subaccounts
    for s in subs:
        client = Client(s.sid, s.auth_token)
        sub_op_id = find_operator_id(client, OPERATOR_DISPLAY_NAME)
        if not sub_op_id:
            print(f"\n=== subaccount {s.sid} ===\n  ! operator not found")
            continue
        process_account(f"subaccount {s.sid}", client, sub_op_id, apply)

    if not apply:
        print("\nDry-run complete. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
