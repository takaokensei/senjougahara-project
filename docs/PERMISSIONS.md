# Permission Model

Senjougahara uses a three-tier risk model to gate all desktop automation actions.
No tool executes "blindly" — the risk tier is assigned by the tool author at registration time, not by the LLM at call time.

---

## Risk Tiers

| Tier | Default Behavior | Examples |
|---|---|---|
| **LOW** | Auto-execute + log to audit trail | Open an app, read a file, list directory, take screenshot, navigate to URL |
| **MEDIUM** | Notify user + proceed (default); or require confirmation (configurable) | Write a file, focus a window, type text, run a read-only command (`git log`, `dir`) |
| **HIGH** | Always require explicit confirmation — never silently auto-approved | Delete files, run mutating commands, install software, send messages on user's behalf |

---

## Fixed "Never Auto-Approve" Set

Some actions are hardcoded as requiring confirmation regardless of `policy.yaml` overrides:

- `delete_file`, `delete_directory`, `move_file`
- `modify_registry`, `change_firewall_rule`
- `install_software`, `uninstall_software`
- `send_email`, `send_message`, `post_tweet`, `submit_form_payment`

This set is defined in `brain/permissions/policy.py` as `NEVER_AUTO_APPROVE_TOOLS`. A malformed or compromised `policy.yaml` cannot remove these from the confirmation requirement.

---

## Confirmation Behavior

- **HIGH-risk confirmation timeout**: if the user does not respond within `confirmation_timeout_seconds` (default: 30s), the action is **CANCELLED**, not auto-approved. Fail-safe semantics.
- **Confirmation UI**: displayed via the avatar overlay (rendered in the Electron renderer via the bridge protocol's `confirmation_request` message type).

---

## policy.yaml Overrides

You can re-tier individual tools in `brain/permissions/policy.yaml`:

```yaml
overrides:
  # Relax a MEDIUM tool to LOW (auto-execute):
  type_text: LOW
  
  # Promote a LOW tool to require confirmation:
  read_file: HIGH
```

Restrictions:
- Tools in the `NEVER_AUTO_APPROVE_TOOLS` set cannot be downgraded to silent.
- Invalid tier strings are ignored with a warning.

---

## Audit Log

Every tool execution (any tier) is appended to:
```
%LOCALAPPDATA%\Senjougahara\logs\audit.jsonl
```

Format:
```json
{"ts": "2026-08-16T19:00:00Z", "tool": "read_file", "risk": "LOW", "args": {"path": "C:\\Users\\..."}, "outcome": "auto_approved"}
```

Outcome values: `auto_approved`, `notify_proceed`, `confirmed`, `denied_by_user`, `denied_no_callback`, `denied_timeout`.