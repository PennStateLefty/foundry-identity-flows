# Identity propagation specification

Normative terms **MUST**, **MUST NOT**, and **SHOULD** describe this lab's
acceptance rules, not additional Microsoft platform guarantees.

## Boundaries and identities

| Boundary | Credential/context | Meaning | Must not be confused with |
|---|---|---|---|
| Interactive client -> Foundry | Delegated Foundry access token | Entra user authenticated to Foundry | ID token, Graph token |
| Interactive client -> API | API-audience delegated access token | User authenticated to the API | Foundry-audience bearer passthrough |
| API -> Foundry, OBO | Exchanged delegated Foundry token | Same user, new audience | App-only token |
| Trusted backend -> Foundry | Workload token plus `x-ms-user-identity` | Backend asserts represented user with explicit permission | Downstream OAuth grant |
| Foundry -> hosted handler | Trusted `x-agent-user-id` | Opaque global platform user key | Original user bearer token |
| Hosted handler -> supported Foundry service | Workload token plus current `x-agent-foundry-call-id` | Request-scoped platform delegation context | Reusable user credential |
| Foundry -> remote A2A/MCP | Connection-selected OAuth credential | Principal and audience depend on connection | Automatic universal token forwarding |
| Custom MCP -> Foundry | Wrapper validates its token, then OBO | Explicit additional delegated hop | Protocol exposure implementing authentication |

The original incoming Authorization bearer is not forwarded into the hosted
container. User partition context and downstream OAuth authorization are separate
planes. The platform may preserve a user partition while a tool uses a service
principal; conversely, a custom wrapper may implement OBO without using the hosted
call-ID mechanism.

## Required experiment behavior

1. The lab MUST compare trusted runtime context, never a model's claimed identity.
2. Each run MUST establish direct B baselines for two distinct authenticated users.
3. Caller-selected arbitrary URLs MUST NOT become token forwarding destinations.
4. Incoming API tokens MUST pass signature, tenant, issuer, audience, expiry, and delegated-scope validation.
5. OBO failures MUST NOT silently switch to service authentication.
6. Represented-user headers MUST originate from validated backend claims.
7. Call IDs MUST remain request-scoped and MUST NOT be stored or replayed across users.
8. Public evidence MUST contain only aliases and allowlisted outcomes.
9. Configuration failures MUST NOT satisfy negative authorization expectations.
10. Conditional or unsupported platform combinations MUST remain BLOCKED or NOT RUN.

The [README index](../README.md#pattern-index) defines P01-P09, diagrams, concise
steps, and per-pattern acceptance criteria. The runner exercises three entry
patterns plus six two-agent patterns. Probe-only patterns run their positive
configuration; the other six each run user, service, and dropped-context variants:
**21 observations per user, 42 per full run**, plus two B baselines.

`service` and `drop-context` are intentionally the same omission control for
direct Responses chaining. They are not independent authentication mechanisms
in that transport. Tool connections can choose genuinely different principals.
Missing identity is a failed observation; ambiguous/missing protocol output is
a blocked harness case.

## Support and trust limits

Incoming A2A documentation explicitly names prompt agents. P04/P05's hosted
target is conditional until validated on the selected platform version.
Credentialed agent-card discovery and explicit A2A v1.0 negotiation are required.
Custom OAuth consent can require interactive completion that this deterministic
runner does not implement; perform that step separately.

Comparing an opaque platform user key demonstrates identity continuity only.
This specification does not establish Graph permissions, downstream ACL
enforcement, session ownership, cross-tenant behavior, or channel-specific
identity propagation. It MUST NOT be cited as evidence of those properties.

P03's application-user mapping to a direct Entra baseline is itself experimental.
A different mapping is not automatically an authorization vulnerability.
The backend remains responsible for session ownership; a represented-user header
is not a substitute for session authorization.

Authoritative contracts and reviewed implementation revisions:
[sources](sources.md). Environment setup: [configuration](configuration.md) and
[deployment](deployment.md).
