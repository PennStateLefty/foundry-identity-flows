# Evidence and acceptance

## Status vocabulary

| Status | Meaning |
|---|---|
| PASS | The measured outcome satisfies the explicitly recorded expectation. |
| FAIL | A valid observation contradicts the expectation. |
| BLOCKED | Authentication, consent, infrastructure, schema, or harness prerequisites prevented measurement. |
| NOT RUN | No live observation exists. |

Negative tests can PASS when they demonstrate changed identity. A blanket HTTP
denial is not enough: it may originate from a proxy, discovery, or expired token,
not B. The live runner conservatively marks HTTP errors BLOCKED. The evaluator
can accept a target-attributed denial for separate, manually verified tests.

## Live procedure

Run `identity-lab --config .local/config.json`. Sign in twice for each user:
once for Foundry and once for the API. Use the same account within each pair,
and different accounts across pairs. No token cache is persisted.

The runner first invokes B directly for each user. Every successful scenario
must contain exactly one `identity-probe-v1` result, even through nested
Responses, MCP, or A2A envelopes. Ambiguous or missing probes cannot pass.

Positive cases compare B's trusted runtime identity against the user's baseline.
Negative cases require a different resolved identity. Missing identity is FAIL,
not proof of denial. Equal baselines for two distinct users abort the run.
Cross-user collisions in positive cases fail the affected scenario.

The runner exits nonzero for any FAIL or BLOCKED result. It writes raw observed
identifiers only under `.local/evidence/latest.json` with restrictive permissions.
The public candidate contains aliases, fixed reason codes, and comparison
outcomes, not tokens or identifiers. Review it before copying to `results/`.

## Deliberate limits

- This is not an authorization penetration test or production security certification.
- B's observed user context does not prove a downstream resource enforced an ACL.
- P03 identifier mapping must be investigated if different from direct Entra context.
- Connection consent can authenticate a different upstream account; inspect consent separately.
- Cross-project, cross-tenant, Teams, Copilot Activity, durable/background, and session-sharing flows are unverified.
- Local unit tests do not substitute for deployed two-user evidence.
- No success is inferred from an HTTP 200 or a model's description of the user.

## Evidence manifest

Keep runtime versions and source revision in reviewed evidence. Do not publish
resource URLs, deployment IDs, traces, identity hashes, sign-in names, or opaque
call IDs. See [publication policy](../PUBLICATION.md).
