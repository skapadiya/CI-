# Twilio CI Custom Operator Sync (Intelligence v3)

Conversational Intelligence custom operators are **account-scoped**, they don't
inherit across subaccounts. These two scripts do code-driven replication from a
parent account out to all of its subaccounts.

## Scripts

| Script | What it does |
|---|---|
| `sync_operators.py` | Upserts the operators defined in the `OPERATORS` list onto the parent **and** every subaccount (create or update, matched by display name). |
| `attach_operators.py` | Wires each operator into a rule on each account's Intelligence Configuration (v3: `Configuration → Rules → Operators`) so it actually runs. Creates a configuration on accounts that have none. |

Both are **idempotent** and default to a **dry-run** (print the plan, write nothing). Pass `--apply` to write.

## Usage

```bash
pip install -r requirements.txt

export TWILIO_ACCOUNT_SID=ACxxxx      # PARENT account sid
export TWILIO_AUTH_TOKEN=xxxxx        # PARENT auth token

python sync_operators.py              # dry-run
python sync_operators.py --apply      # create/update operators everywhere

python attach_operators.py            # dry-run
python attach_operators.py --apply    # attach operators into config rules
```

Re-run `sync_operators.py` whenever a prompt changes — it pushes the new prompt
to every account. It's a copy, not a live link: each account gets its own operator id.

## Notes

- Uses the **v3** Intelligence API. The older v2 "attach to a Service" flow does not apply.
- Edit `OPERATORS` in `sync_operators.py` to define your operators.
- Edit `OPERATOR_DISPLAY_NAME` / `PARENT_CONFIG_ID` in `attach_operators.py` to match.
- Credentials are read from env vars only — no secrets are stored in the code.
