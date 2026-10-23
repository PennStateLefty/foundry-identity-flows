# Sources and provenance

Research and deployment follow-up checked 2026-10-23. Prefer current first-party contracts over older
sample READMEs. Recheck support and versions when reproducing.

## Authoritative contracts

| Topic | Source |
|---|---|
| Hosted context headers | https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-contract |
| Hosted identity migration | https://learn.microsoft.com/azure/foundry/agents/how-to/migrate-hosted-agent-preview |
| Backend impersonation | https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions |
| Application-managed OBO | https://learn.microsoft.com/azure/foundry/agents/how-to/use-on-behalf-of-flow |
| Session isolation | https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user |
| Incoming A2A | https://learn.microsoft.com/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint |
| A2A authentication | https://learn.microsoft.com/azure/foundry/agents/concepts/agent-to-agent-authentication |
| Outgoing A2A | https://learn.microsoft.com/azure/foundry/agents/how-to/tools/agent-to-agent |
| Toolbox authentication | https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-authentication |
| Hosted toolbox integration | https://learn.microsoft.com/azure/foundry/agents/how-to/tools/use-toolbox-hosted-agent |
| Custom MCP authentication | https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication |
| Entra OBO protocol | https://learn.microsoft.com/entra/identity-platform/v2-oauth2-on-behalf-of-flow |
| azd Bicep | https://learn.microsoft.com/azure/developer/azure-developer-cli/ |
| Hosted telemetry and reserved settings | https://learn.microsoft.com/azure/foundry/agents/how-to/configure-hosted-agent-telemetry |
| Foundry Entra trace ingestion | https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication |
| Application Insights Entra ingestion | https://learn.microsoft.com/azure/azure-monitor/app/azure-ad-authentication |
| Container Apps log routing | https://learn.microsoft.com/azure/container-apps/log-options |
| Foundry project connection schema | https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/accounts/projects/connections |

## Implementation references

The lab is original integration code informed by the following implementations.
No source has been copied from unlicensed community repositories.

| Repository | Reviewed revision | License | Use |
|---|---|---|---|
| [Foundry samples](https://github.com/microsoft-foundry/foundry-samples/tree/86a5adfa0b61bb80c8fe5009c56cf2f6fa17518e) | `86a5adfa0b61bb80c8fe5009c56cf2f6fa17518e` | MIT | Protocol handler, A2A connection, hosting manifest patterns |
| [Python Azure SDK](https://github.com/Azure/azure-sdk-for-python/tree/eb4f27da55e7d3834bccd5e07828d58ebaea08e0/sdk/agentserver) | `eb4f27da55e7d3834bccd5e07828d58ebaea08e0` | MIT | Request context and call-ID wire contract |
| [Agent Framework](https://github.com/microsoft/agent-framework/tree/a8e284ca8ce7c2a6b4a4641ef35e131d75a5cda3) | `a8e284ca8ce7c2a6b4a4641ef35e131d75a5cda3` | MIT | MCP exposure versus identity delegation distinction |
| [Azure Verified Modules](https://github.com/Azure/bicep-registry-modules) | Version-pinned module references in `infra/resources.bicep` | MIT | Workspace, Insights, registry, environment, and application resource composition |
| [Community end-to-end OBO](https://github.com/cmw2/foundry-identity-passthrough) | README and middleware inspected | No detected license | Reference only; no code copied |
| [Community custom MCP/Fabric](https://github.com/anildwarepo/foundry_agents_with_obo_mcp_server) | README inspected | No detected license | Reference only; no code copied |

The official A2A sample still includes preview configuration. The lab targets
the current protocol-2.0 runtime and A2A 1.0 contract instead of reproducing that
sample verbatim. Some conceptual identity pages retain legacy Agent Application
lifecycle details; current endpoint guidance takes precedence for this lab.
