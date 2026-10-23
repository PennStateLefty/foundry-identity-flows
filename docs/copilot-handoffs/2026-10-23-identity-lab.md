# Identity lab handoff: execution repair and remaining baselines

Recorded: 2026-10-23. Runtime repair source: `67c270f`.

## Objective and immediate priority

Complete the nine Microsoft Foundry identity-flow experiments described in the
[README](../../README.md) and [specification](../specification.md).
The operator requested remaining flow baselines before identity triage, then
correctly stopped testing when execution errors prevented those measurements.

**Next: configure and verify executable A2A/MCP paths before asking for another
full two-user authentication run.** Fixing error reporting is not the same as
making a flow operational. Never count an HTTP 500/502, a completed Responses
envelope, or a missing probe as evidence of identity propagation.

## Current verified state

| Surface | Latest verified result |
|---|---|
| Infrastructure | Deployed through azd/Bicep in the operator-approved lab resource group |
| API | Repaired immutable image deployed; health 200, anonymous invocation 401 |
| Hosted A and B | Active version 3; identities retained; direct probes return trusted identity |
| Direct A / middleware OBO | Two distinct target-tenant users have distinct direct-A identities; OBO matches each user's direct-A identity |
| Direct B | Member baseline succeeded; guest initially got 403 but later obtained a distinct baseline without another permission change |
| Responses chaining | Measured downstream user identity absent with and without call context |
| A2A/MCP | Not operational: deployed toolbox endpoints/tool names are empty |
| P03 backend delegation | Workload authentication succeeds after repair; downstream Foundry returns 403, surfaced as middleware 502 |
| Operational telemetry | API/A/B ingestion, HTTP outcomes, parent links, and fixed toolbox failure codes verified |
| Container Apps console/system persistence | NOT VERIFIED; live console reads work, workspace ingestion remains unresolved |

No model deployment is used: hosted agents are deterministic protocol-2.0
Responses handlers, not LLM-generated identity simulations.

## Evidence: distinguish history from new measurements

The published [strict matrix](../../results/latest.json) still contains
**2 PASS, 5 FAIL, 9 BLOCKED, 26 NOT RUN**. It represents the earlier reviewed
observations and requires each user's direct-B baseline.

All 26 previously unattempted configurations were subsequently submitted for
both users, but returned execution errors without identity probes. Those
attempts were not promoted into a completed identity baseline or used to
overwrite the matrix. Their private raw observations are preserved.

The later guest B success does not retroactively validate earlier calls.
Refresh baselines and measure the actual flows after setup is complete.
The A-only OBO comparison is supplemental, not a substituted B baseline.
See [deployment evidence](../deployment.md#interactive-two-user-follow-up) and
[execution findings](../deployment.md#execution-errors-found-before-further-identity-testing).

## Confirmed execution defects and repair

| Defect | Evidence | Repair |
|---|---|---|
| API image omitted `aiohttp` | API console traceback during real async managed-identity credential construction | Explicit constrained runtime dependency in `pyproject.toml`; real credential construction regression |
| Empty toolbox endpoint raised unhandled `ValueError` | Exact failing hosted session console; empty settings read from deployed agent definition | Validate endpoints/tool names before authentication; fixed prerequisite diagnostic |
| Empty toolbox argument setting would fail JSON decoding | Source inspection of next execution step | Treat empty value as `{}`; reject malformed/non-object arguments explicitly |
| Generic gateway responses obscured prerequisites | Correlated API/agent failure spans | Fixed `LabError` codes, middleware status mapping, allowlisted telemetry |

Operational errors use `identity-lab-error-v1`, never `identity-probe-v1`.
Hosted Responses can carry the error in a completed HTTP 200 output envelope;
`transport.invoke()` recognizes it and raises `LabError`. Middleware maps
configuration/schema/tool-discovery prerequisites to 503 and tool-reported
execution failures to 502. Handler spans record `lab.error.code` and failure
status without raw exception text, identities, tokens, or endpoints.
Unexpected errors are not broadly caught and relabeled as prerequisites.

Live post-repair checks confirmed:

- Direct A/B probes still return trusted identity.
- A2A/MCP explicitly report `toolbox-not-configured`, not unhandled 500.
- P05/P09 middleware return 503 with that exact fixed diagnostic.
- P03 `auth.workload` succeeds; its outbound dependency returns 403.
- Application Insights contains the corresponding failures and fixed codes.

P03 is not fixed end to end. Toolbox flows are not configured by this repair.

## Next steps, in order

1. Read the private deployment target and cleanup inventory; preserve the
   existing resource-group boundary and current identities.
2. Inspect current project connections and toolbox definitions before creating
   anything; use [configuration](../configuration.md#a2a-and-toolboxes).
3. Check incoming A2A support for hosted B. Current documentation names prompt
   agents; do not replace deterministic identity evidence with model output.
   An unsupported hosted combination must remain explicitly BLOCKED.
4. Configure user/service toolbox connections and discover actual tool names
   and schemas. User A2A uses `UserEntraToken`; its control uses `AgenticIdentity`.
   Verify A2A 1.0 negotiation and authenticated agent-card discovery.
5. Configure the custom OAuth connection to the deployed MCP wrapper and
   complete operator consent. The wrapper validates delegated API tokens and
   exchanges them through OBO; app-only requests must not become user access.
6. Bind the discovered endpoints/tool names/arguments to A and deploy through
   the existing prebuilt-image process. Verify one focused execution path
   before asking both users to repeat the full matrix.
7. Resolve P03 only within explicit permission approval. Its custom
   impersonation-role definition was not created because it exceeds the
   resource-group-only authorization. Do not silently widen access.
8. Run distinct-user baselines and valid flows, review the alias-only candidate,
   and update matrix plus README tables together. Preserve failed controls and
   support gates honestly.

Use correlated Application Insights requests/dependencies first, then the exact
session console log for crashes. A historical session list did not locate the
latest failure; the actual invocation's `x-agent-session-id` enabled retrieval.
Keep that header and raw logs private. Resource-context KQL uses `requests` and
`dependencies`; workspace-context KQL uses `AppRequests` and `AppDependencies`.
See [observability](../observability.md).

## Authentication and approval

- `user-a` is the tenant-local member/administrator; `user-b` is a guest in the
  same target tenant. Ask the operator for the exact account names from private
  context; never publish names or infer cross-tenant testing.
- Use the same account for its Foundry and API sign-ins; compare acquired-token
  tenant/object claims locally to avoid browser account-selection mistakes.
- Login hints guide selection but are not proof of the authenticated account.
- Tokens stay in memory; no persistent MSAL token cache.
- The operator explicitly approved the middleware's declared Foundry delegated
  `user_impersonation` consent tenant-wide and a guest Foundry Agent Consumer
  assignment at the lab project. Exact records are private.
- No roles, consent, or connections changed during the runtime repair.
- Autopilot is off. Obtain specific approval for additional permission/consent
  changes or anything beyond the recorded deployment boundary.
- Check existing credential expiration privately before continuing. Do not
  print, extend, rotate, or create credentials without applicable approval.

## Implementation and validation

Relevant source:

- `src/identity_lab/errors.py`: fixed operational codes and HTTP mapping.
- `src/identity_lab/hosted.py`: toolbox preflight and hosted diagnostic output.
- `src/identity_lab/transport.py`: Responses diagnostic recognition.
- `src/identity_lab/api.py`: middleware diagnostic handler.
- `src/identity_lab/telemetry.py`: allowlisted error-code attributes.
- `tests/test_runtime.py`, `tests/test_telemetry.py`: regression coverage.

Latest checks: 67 tests pass. Network-disabled runtime tests pass in both
deployment images (API skips two hosted-only checks); telemetry tests pass
(API skips one hosted-only check). Repository CI passed for `67c270f`.

Build only through the operator's configured approved package feed using a
BuildKit secret mount; no public-feed fallback. Both Dockerfiles install with
`requirements.lock.txt` constraints. `aiohttp` was already pinned there.
Do not copy private feed configuration into images or build arguments.

Use existing root/hosted azd environments, not obsolete local state. Set
`AZURE_DEV_USER_AGENT=microsoft_foundry_skill` process-only for every azd command.
The installed extension requires a privately rendered digest-pinned agent
manifest. Follow [deployment](../deployment.md); do not replace this with remote
dependency resolution or provision new infrastructure to repair application code.

## Private artifacts on the original operator workspace

These are ignored files, not part of a fresh clone. Never force-add or upload
them. If unavailable, request the operator's environment configuration rather
than reconstructing real identifiers from public examples.

| Relative path | Purpose |
|---|---|
| `.local/deployment-target.json` | Approved target and constraints |
| `.local/deployment_ops.py` | Resource-group scope guard and locked mutation journal |
| `.local/deployment-ledger.json` | Exact attempted/completed mutations and cleanup records |
| `.local/cleanup-inventory.json` | Resources, grants, consent, credential references and repair digests |
| `.local/api-credential-state.json` | Credential expiration/key reference; actual secret is separate |
| `.local/interactive-user-a-smoke.json`, `.local/interactive-user-b-smoke.json` | Earlier completed direct/OBO observations |
| `.local/interactive-user-a-remaining.json`, `.local/interactive-user-b-remaining.json` | Execution-error attempts for remaining configurations |
| `.local/runtime-repair-live-verification.json` | Focused post-repair live observations and correlation |
| `.local/runtime-repair-summary.json` | Telemetry-backed repair findings |
| `.local/repair-before-hosted-console.log` | Exact hosted endpoint-validation traceback |
| `.local/diagnose-api-console-300.log` | Missing async transport traceback |
| `.local/published-images.json`, `.local/published-images-pre-repair.json` | Current and previous image digests |
| `.local/agents/azure.yaml`, `.local/agents/azure-pre-repair.yaml` | Current and previous private hosted manifests |
| `.local/repair-root-endpoints.log` | Actual API endpoint from azd |
| `.azure/deployment-plan.md` | Private validation/deployment proof; historical sections are labeled |

Do not automatically delete resources, grants, identities or credentials.
Cleanup requires explicit operator approval and the exact private inventory.
Follow [PUBLICATION.md](../../PUBLICATION.md) for every commit and artifact.
