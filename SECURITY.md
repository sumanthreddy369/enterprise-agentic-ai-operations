# Security boundary

This repository is a local portfolio data foundation, not an approved production deployment. See [the guardrail matrix](docs/guardrails.md) for implemented controls, tests, limitations and production gates.

Do not publish source data, credentials, request bodies or sensitive logs in issues. For a suspected vulnerability, use the repository owner's private contact or GitHub private vulnerability reporting when enabled. Revoke any exposed credentials before sharing a sanitized report.

No autonomous remediation is available. Do not add arbitrary shell/SQL execution or bypass approvals when later introducing agents. Every new external connector, parser, tool or executor needs a threat-model update and negative tests at its enforcement boundary.
