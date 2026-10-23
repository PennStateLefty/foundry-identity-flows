# Configuration specification

## Direct clients

Use one tenant and two distinct existing test users. Do not create real users
from scripts or assign directory administrator roles for this lab.

1. Create a public client registration with the `http://localhost` desktop redirect URI.
2. Grant its delegated Foundry permission and the lab API's `access_as_user` permission.
3. Grant both users Foundry Agent Consumer on A and B, preferably through a test group.
4. Keep all registration IDs in `.local/config.json`, copied from `config.example.json`.

The runner opens interactive authentication separately for Foundry and the API,
checks that both grants represent the same user, and requires distinct test users.
An ID token is never used to invoke Foundry. Tenant matching is required for
documented toolbox passthrough; cross-tenant exchange is outside this lab.

Sources: [Foundry RBAC](https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry),
[public-client authentication](https://learn.microsoft.com/entra/identity-platform/scenario-desktop-overview).

## Middleware OBO

The API registration exposes `api://<application-id>/access_as_user`, requests
version-2 access tokens, and has consented delegated Foundry permissions. Its
confidential credential remains in a local environment or Key Vault. The public
client obtains an API-audience token; `auth.py` verifies signature, issuer,
audience, expiry, tenant, object claim, and delegated scope before OBO.

The lab deliberately does not fall back to app-only authentication. Consent
and Conditional Access errors stop the request. Production integrations should
implement the full claims-challenge roundtrip; this lab marks interaction-blocked
cases BLOCKED and requires consent before running.

Workload authentication is also explicit: the platform uses its federated
workload credential when `AZURE_FEDERATED_TOKEN_FILE` is injected, otherwise its
managed identity. It never silently falls back to a developer's CLI credentials.
For an intentionally local workload experiment only, set
`LAB_WORKLOAD_AUTH=azure-cli` with the approved `LAB_TENANT_ID`.

Source: [Entra OBO](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-on-behalf-of-flow).

## Operational monitoring

Operational monitoring is independent of identity delegation. See
[observability](observability.md) for the common Application Insights/Log
Analytics destination, explicit telemetry configuration, scoped publisher
permissions, privacy boundaries, and troubleshooting queries.

## Backend delegation

Assign the API workload Foundry Agent Consumer on A. Separately create a custom
role containing only:

```text
Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action
```

Assign that role to the API workload at A or project scope. `scripts/tenant.py`
prints a local change plan before directory creation; use `scripts/rbac.py` for
explicit role assignments. Built-in role identifiers are resolved locally by
name; no environment-specific IDs are checked into source.

The API derives `x-ms-user-identity` from the validated user's object claim, never
from a caller-supplied impersonation header. That identifier is not a downstream
credential. This implementation does **not** send Graph tokens or claim Graph OBO
coverage. It also does not implement session ownership tests.

Sources: [explicit permission](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions#delegate-the-end-user-identity),
[delegated session caveat](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user#isolate-sessions-for-your-own-users).

## A2A and toolboxes

1. Enable B's Responses and A2A endpoint protocols using `scripts/configure_foundry.py`.
2. Create `identity-user` and `identity-service` toolboxes in the same project.
3. Add B's A2A endpoint using a `RemoteA2A` connection.
4. Use `UserEntraToken`, audience `https://ai.azure.com`, for the user connection.
5. Use `AgenticIdentity` with the same audience for the service connection.
6. Grant the appropriate users or calling agent access to B.
7. Configure `TOOLBOX_USER_ENDPOINT` and `TOOLBOX_SERVICE_ENDPOINT` on A.
8. Discover actual tool names and schemas with `scripts/tool_schema.py`.
9. Set `A2A_USER_TOOL`, `A2A_SERVICE_TOOL`, and `A2A_ARGS_JSON` accordingly.

Use generally available A2A **1.0**, not a copied preview manifest. Follow
`send_credentials_for_agent_card` guidance for the deployed endpoint version:
current incoming documentation requires authenticated agent-card discovery,
while some outgoing guidance describes platform-specific automatic handling.
Verify discovery explicitly rather than assuming the documents are identical.

**Hosted-target support gate:** the current incoming-A2A article lists a deployed
**prompt agent** as its prerequisite. This lab's B is a deterministic **hosted**
agent. Treat P04/P05 as conditional experiments, not a documented guarantee of
hosted-target support: if the deployed platform rejects enabling A2A or cannot
return B's trusted probe, record BLOCKED. Do not silently replace B with a
model-generated identity string. Explicitly select A2A 1.0 on the remote
connection; the service defaults to preview 0.3 if version negotiation is absent.

The raw MCP client in `hosted.py` forwards only the current opaque call ID in
addition to its workload token. This explicitly implements the runtime contract;
it does not rely on generic MCP clients magically forwarding user context.

Sources: [incoming A2A](https://learn.microsoft.com/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint),
[outgoing A2A](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/agent-to-agent),
[runtime contract](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract).

## Responses chaining

Set `LAB_AGENT_B_NAME` on A. The destination is constructed exclusively from the
operator-controlled project endpoint and B's validated name. A obtains its own
Foundry workload token and forwards the current `x-agent-foundry-call-id`.
This is an experiment, not a guarantee that the Responses endpoint consumes that
header for user delegation. The deployed single-operator smoke returned no B user
identity with or without it; see the [recorded result](deployment.md#recorded-single-operator-smoke).

`service` and `drop-context` both omit that header for the Responses experiment.
They are intentionally equivalent controls here. A call ID is not persisted,
replayed between users, or sent to arbitrary external servers. Neither
`previous_response_id` nor `x-agent-user-id` is an outbound credential.

Source: [protocol 2.0 migration](https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-hosted-agent-preview#container-protocol-200).

## Custom MCP wrapper

The authenticated API also mounts `/tools/mcp`. Its `invoke_agent_b` tool validates
the wrapper-audience delegated token and performs OBO for Foundry. This is a real
MCP server, not a model-generated simulation.

Configure a **custom OAuth** project connection targeting this HTTPS MCP endpoint.
Use your API app registration as the OAuth client, configure the returned
Foundry redirect URI, and request the API's `access_as_user` scope plus
`offline_access`. Obtain the required administrative/user consent explicitly.

Add this connection to `identity-user`. The service-control toolbox references
the same endpoint through service authentication; the wrapper intentionally
rejects app-only tokens because it requires a delegated scope.

Set `MCP_USER_TOOL`, `MCP_SERVICE_TOOL`, and `MCP_ARGS_JSON` from discovery. The
wrapper's tool takes no arguments. A toolbox may prefix the tool name.

Surface `oauth_consent_request` to the operator and complete it before running.
This deterministic harness does not automatically resume pending tool-consent
transactions; incomplete consent produces BLOCKED, never PASS.

Sources: [MCP authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication),
[toolbox authentication](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-authentication).
