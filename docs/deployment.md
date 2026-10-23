# Deploy and reproduce in your own environment

**Provisioning and deployment have been exercised in one approved environment.**
This is not a completed two-user identity certification. Partial interactive
results are recorded below. Review every environment,
permission, billable resource, and preview support gate before reproducing it.

## Recorded single-operator smoke

The 2026-10-23 reference deployment used North Central US, azd 1.36.0, and
`azure.ai.agents` 1.0.0-beta.19. Infrastructure stayed in one lab resource group.
Both deterministic hosted agents deployed without a model. Raw responses,
identifiers, image digests, and cleanup records remain private.

| Check | Observed |
|---|---|
| Infrastructure provisioning | PASS after registry-permission recovery |
| Python API `/health` | PASS: HTTP 200 |
| Anonymous API `/invoke` | PASS: HTTP 401 |
| Direct A and B invocation | PASS: HTTP 200 and matching nonempty operator context |
| Application Insights operational telemetry | PASS: API/A/B requests, actual HTTP outcomes, and cross-agent parent links |
| Foundry/registry diagnostics and platform metrics | PASS: rows observed in the lab workspace |
| Container Apps persisted console/system logs | NOT VERIFIED: routing read back and cold start exercised, but no rows observed |
| A -> B Responses with current call ID | FAIL: HTTP 200 and call context present, but B's user identity absent |
| A -> B Responses without call ID | FAIL: B's user identity absent, not a proven different principal |
| Middleware OBO, A2A, and MCP OAuth | NOT RUN: interactive consent and connection prerequisites remain |
| Two-user identity matrix | All 42 observations remain NOT RUN |

These are bounded smoke observations, not two-user matrix results. A successful
HTTP response or a present call ID does not prove user propagation. In particular,
do not treat the chained Responses example as a verified delegation solution.
P03's custom impersonation role was not created because its definition would
exceed the reference deployment's resource-group-only authorization.

## Interactive two-user follow-up

On 2026-10-23, a tenant member and a guest authenticated separately against the
same target tenant. Account names, object IDs, raw probes, and HTTP error bodies
remain private. The middleware's declared Foundry delegated permission received
explicitly approved tenant-wide OAuth consent. The guest received an explicitly
approved Foundry Agent Consumer assignment at the lab project only; both exact
changes are recorded in the private cleanup inventory.

| Check | Member | Guest |
|---|---|---|
| Direct A identity | Present | Present and distinct from member |
| Middleware OBO to A | Matches direct A | Matches direct A |
| Direct B baseline | Present | BLOCKED: HTTP 403 requiring `agents/write` |
| Responses user chain, direct and OBO | FAIL: downstream identity missing | Missing identity observed; strict comparison BLOCKED without B baseline |
| Responses negative controls | Missing identity, except one direct service-control HTTP 500 | Missing identity observed; strict comparison BLOCKED without B baseline |

The supplemental A-only comparison establishes OBO continuity and distinct
identities for these two users, not downstream resource authorization.
The strict matrix retains its direct-B baseline requirement: **2 PASS, 5 FAIL,
9 BLOCKED, 26 NOT RUN** in [the evidence manifest](../results/latest.json).
An HTTP error is BLOCKED, not proof of a different principal or target denial.
No broader agent-write role was granted to bypass the guest's B denial.

The earlier single-operator table is historical, not the latest matrix count.
Toolbox/A2A/MCP configuration and the P03 permission boundary remain unresolved.

## Prerequisites and approval boundary

Use Python 3.12+, Azure CLI, Bicep, Azure Developer CLI 1.36+, the
`azure.ai.agents` extension, and a local Docker engine with BuildKit. Authenticate
to Azure and azd yourself. Choose one explicit tenant, subscription, region, and
short environment name. Confirm hosted-agent regional availability and quota.

The operator needs resource deployment rights, appropriate Foundry data-plane
rights, directory application-creation rights for bootstrap, and role-assignment
rights only when applying grants. Subscription Contributor alone does not grant
Foundry data-plane access. Existing apps can replace bootstrap.

The infrastructure creates a Foundry resource/project, Basic ACR, Container Apps
consumption environment, API/MCP app, Log Analytics workspace, and workspace-based
Application Insights component, plus resource diagnostic settings. It declares
**no model deployment**: the hosted handlers are deterministic. Hosting charges,
registry charges, log ingestion, network usage, and A2A retention still apply.
No universal dollar estimate is asserted; price your selected region using the
[Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/).

Review both subscription and inherited management-group policies before approval.
Governance can independently deploy
[Foundry diagnostic settings](https://learn.microsoft.com/azure/foundry/how-to/diagnostic-logging)
or enable security monitoring. Disabling application/SDK logging does not disable
platform diagnostics or guarantee that identity metadata remains local.
Verify destinations, access, retention, and content capture with the environment
owner; never automatically bypass policy. Policy-managed workspaces and security
services are outside this lab's Log Analytics quota and may add charges.

This lab deliberately uses public HTTPS endpoints with application-level Entra
authentication. It is not a private-network production baseline. The initial
Container Apps image is a public Microsoft placeholder; no lab API is available
until the application image is deployed.

## 1. Prepare local-only configuration

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock.txt -e '.[hosted]'
mkdir -p .local
chmod 700 .local
cp config.example.json .local/config.json
cp .env.example .local/runtime.env
chmod 600 .local/config.json .local/runtime.env
```

Populate placeholders locally. Never commit these files or export shell
environments to public logs. Do not use shell tracing. Install through your
approved package feeds only.

For Docker builds, set `PIP_CONFIG_FILE` to an absolute **local** pip configuration
path containing your approved index configuration. Explicit Docker builds pass it
as a BuildKit secret; neither its path nor contents are baked into the image.
Public PyPI is not an automatic fallback. The local feed must be reachable from
the Docker engine. Both azd manifests consume prebuilt images, not cloud ZIP
dependency resolution, to preserve this feed boundary. `docker.buildArgs` cannot
pass `--secret`: azd turns those entries into Docker `--build-arg` values.
Do not put feed credentials in build arguments or depend on a warm build cache.

Build both images locally before any registry upload:

```bash
docker buildx build --platform linux/amd64 --load \
  --secret "id=pip_config,src=${PIP_CONFIG_FILE:?Set your approved local pip configuration}" \
  --file Dockerfile --tag foundry-identity-api:local .
docker buildx build --platform linux/amd64 --load \
  --secret "id=pip_config,src=${PIP_CONFIG_FILE:?Set your approved local pip configuration}" \
  --file Dockerfile.hosted --tag foundry-identity-hosted:local .
```

These commands do not upload images or create Azure resources.

## 2. Bootstrap directory objects, optionally

```bash
python scripts/tenant.py --tenant "<tenant-id>"
python scripts/tenant.py --tenant "<tenant-id>" --apply
```

The default invocation only prints a plan. `--apply` additionally requires typed
confirmation. It creates four objects and saves each completed mutation in
`.local/tenant-objects.json`; an interrupted manifest is never automatically
retried or adopted by name.

Using the [configuration specification](configuration.md), explicitly configure:
the desktop app's delegated Foundry/API permissions, the API app's delegated
Foundry permission, required consent, and a confidential API credential. The
script intentionally creates no credential, consent grant, user, or role
assignment. Follow tenant policy; do not bypass Conditional Access.

`python scripts/permissions.py --tenant "<tenant-id>"` inspects the exact
delegated permission declaration plan for these two apps; `--apply` plus typed
confirmation configures the declarations only. It discovers the existing
Foundry resource and scope definitions instead of hardcoding application IDs.
It grants no consent, Graph permissions, or application permissions.

For an explicitly approved 24-hour API credential, run
`python scripts/credential.py --tenant "<tenant-id>"` to inspect the plan, then
add `--apply` and confirm. It uses the non-destructive `addPassword` operation,
records each request locally, refuses automatic repeats, and saves the secret
with owner-only access. It never prints the value or replaces existing credentials.

The runtime accepts version-2 API access tokens with audience equal to the API
application's client ID. The API scope is `api://<application-id>/access_as_user`.

## 3. Provision the infrastructure

Review `infra/main.bicep` and its pinned Azure Verified Modules. Set the following
locally before provisioning:

| Variable | Value |
|---|---|
| `LAB_TENANT_ID` | Approved tenant |
| `LAB_API_CLIENT_ID` | Confidential API application ID |
| `LAB_API_CLIENT_SECRET` | API credential; never print or put into command history |
| `LAB_API_IMAGE` | Initially `mcr.microsoft.com/dotnet/samples:aspnetapp`; replace with the reviewed API registry digest before deploying |
| `LAB_API_REGISTRY_MODE` | `bootstrap` initially; `private` only after the API identity's AcrPull grant propagates |

Set the credential through your secret manager or a non-echoing shell prompt.
The Bicep parameter is secure, and Container Apps stores it as a secret reference,
not a plain environment value. This preview uses Container Apps secrets rather
than provisioning a Key Vault; production should use Key Vault references and
certificate/federated credentials where supported.
Even provisioning initializes the prebuilt-image service, so `LAB_API_IMAGE`
must be set. The initial value matches Bicep's explicit public bootstrap image;
it is not the lab API and must never be mistaken for a completed API deployment.
Bootstrap mode deliberately omits registry credentials: Container Apps validates
configured registry identities even when the container image itself is public.
Adding an ungranted system identity would stall its first revision.

After approving costs and the explicit resource plan:

```bash
azd env new "<environment>" --subscription "<subscription-id>" --location "<region>"
azd provision
```

The parent azd environment must match the approved tenant. Both CLI logins need
to target that tenant. No script selects a subscription on your behalf.

Save outputs locally, not in an issue or public CI artifact:

```bash
azd env get-values > .local/provisioned.env
chmod 600 .local/provisioned.env
```

## 4. Apply required permissions, publish reviewed images, and deploy the API

Run `scripts/rbac.py --help` for explicit tenant/principal/type/scope arguments.
Every grant defaults to a plan and requires `--apply` plus typed confirmation.
Use project or agent scopes where supported:

| Principal | Scope | Role |
|---|---|---|
| Two test users or test group | A/B or project | Foundry Agent Consumer |
| API's system-assigned identity | A or project | Foundry Agent Consumer |
| API's system-assigned identity | A or project | Custom impersonation role, only for P03 |
| API's system-assigned identity | ACR | AcrPull |
| Foundry project's managed identity | ACR | AcrPull |
| Deployment operator | ACR | AcrPush |
| Agent A identity | B/project and toolboxes | Required endpoint/tool access |
| API and each hosted agent identity | Lab Application Insights component only | Monitoring Metrics Publisher |
| Foundry project's managed identity | Lab Application Insights component only | Monitoring Metrics Publisher |

The deployment operator also needs Foundry authoring rights. Review
[hosted-agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)
for the Foundry project's registry image-pull access and role changes introduced
by the hosted deployment tooling; do not grant subscription-wide Owner.

After separate approval for registry access and image upload, authenticate to the
new registry, tag the locally reviewed images, and push only those two images:

```bash
az acr login --name "<provisioned-registry-name>"
docker tag foundry-identity-api:local "<registry-login-server>/identity-api:<reviewed-tag>"
docker tag foundry-identity-hosted:local "<registry-login-server>/identity-hosted:<reviewed-tag>"
docker push "<registry-login-server>/identity-api:<reviewed-tag>"
docker push "<registry-login-server>/identity-hosted:<reviewed-tag>"
```

Record the returned digests privately. Set `LAB_API_IMAGE` in the root project's
private azd environment to the fully qualified registry reference, preferably
`<registry-login-server>/identity-api@sha256:<reviewed-digest>`.
The manifest's `docker.imagePassthrough: true` makes `azd package api` package
that reference without rebuilding, pulling, or pushing it. Packaging success
does not prove the image exists remotely or that a workload can pull it.
Verify the remote digest and scoped pull permissions before deployment.

After verifying the API's AcrPull assignment and the registry's
`authentication-as-arm` policy, set `LAB_API_REGISTRY_MODE=private` in the root
project's private environment and run a reviewed `azd provision` preview/pass
before deploying the API image. This second pass adds its registry configuration.
Infrastructure and service deployment both consume `LAB_API_IMAGE`; retain the
reviewed digest in the root environment rather than reverting to the bootstrap
image when reprovisioning an experiment.

```bash
azd package api
azd deploy api
```

The installed CLI also supports `azd deploy api --from-package "<image-reference>"`;
it skips packaging, not the need to review the image and deployment permissions.
This lab uses the manifest's explicit prebuilt-image setting as its default.

Set the public API HTTPS endpoint in `.local/config.json`. `/health` is anonymous;
`/invoke` and `/tools/mcp` require delegated API-audience tokens. Disable public
request/body/header logging; the Docker command disables Uvicorn access logs.
`LAB_PUBLIC_HOST` must be the exact deployed API hostname; Bicep sets it for
Container Apps. MCP DNS-rebinding protection stays enabled and rejects other
Host/Origin values. Hosted handlers disable SDK observability setup and access
logging to avoid exporting identity-probe response content through SDK defaults.
The lab's separate allowlisted operational spans remain enabled in deployed
configuration. See [observability](observability.md) for both telemetry paths,
the publisher grants, and live ingestion checks.

## 5. Bind and deploy the hosted agents

The second azd project's portable template is `agents/azure.yaml`. It references
the existing, successfully provisioned Foundry project rather than declaring
another project. The tested agent extension validates raw `image` fields before
substituting `${LAB_HOSTED_IMAGE}` during initialization. Set that environment
variable to the reviewed immutable registry digest, then render an ignored,
owner-only manifest; do not replace the public template with tenant values.
Initialize its local state using the **actual ARM project ID** returned by the
first deployment; do not derive an ID from its endpoint:

```bash
python scripts/render_agents.py
cd .local/agents
azd env new "<agent-environment>" --subscription "<subscription-id>" --location "<region>"
azd env set AZURE_AI_PROJECT_ID "<provisioned-project-resource-id>"
azd env set AZURE_AI_PROJECT_ENDPOINT "<provisioned-project-endpoint>"
azd env set FOUNDRY_PROJECT_ENDPOINT "<same-provisioned-project-endpoint>"
azd env set AZURE_TENANT_ID "<tenant-id>"
```

This is an already-authored image-only project, so no template-adoption init is
needed. The tested init command cannot adopt a local template into its own source
tree. Configure the existing-project environment directly instead of copying
tenant values into source or allowing init to create another Foundry project.
Image-only services use `project: .`; the tested extension rejects `..` paths
even though no source packaging is required.
Bind `AZURE_RESOURCE_GROUP`, `AZURE_AI_ACCOUNT_NAME`, `AZURE_AI_PROJECT_NAME`,
`AZURE_CONTAINER_REGISTRY_NAME`, `AZURE_CONTAINER_REGISTRY_ENDPOINT`, and
`AZURE_CONTAINER_REGISTRY_RESOURCE_ID` from the root deployment's actual outputs.
The installed extension also requires the `FOUNDRY_PROJECT_ENDPOINT` alias for
project inspection.

Supply the root `APPLICATIONINSIGHTS_CONNECTION_STRING` output to this project's
private environment without printing it or putting values in shell history.
Both agents map it to `LAB_APPLICATIONINSIGHTS_CONNECTION_STRING`, and each
workload needs its separately approved App-Insights-scoped publisher role.
The root infrastructure also creates the project's Entra-authenticated
`AppInsights` connection. Confirm it and the project identity's publisher grant
before starting sessions; do not configure the reserved
`APPLICATIONINSIGHTS_CONNECTION_STRING` as an agent environment variable.
Set `LAB_HOSTED_IMAGE` in that same private environment to the reviewed registry
image, preferably `<registry-login-server>/identity-hosted@sha256:<reviewed-digest>`.
Both services deliberately use the same image with different fixed service roles.
Their service-level `image` setting tells the extension to reuse the prebuilt
image rather than build or publish another image.

Review any generated manifest changes before provisioning/deployment. Select an
existing ACR connection or approve the registry connection required by the
current extension. Confirm the selected subscription, existing project, registry,
container deployment mode, and protocol `responses` version `2.0.0`.
Preserve the prebuilt `image` fields; reject generated changes that reintroduce
feed-blind builds or remote dependency resolution.
No model is used by these handlers; if your platform/extension requires a model
despite this, stop and record the deployment prerequisite as BLOCKED rather than
creating an unapproved model deployment.

Configure A's toolbox endpoints, discovered tool names, and fixed argument JSON
from [configuration](configuration.md). The project endpoint is platform-injected
as `FOUNDRY_PROJECT_ENDPOINT`. A's B target is `LAB_AGENT_B_NAME`.

Deploy B first, then A, using the current extension's existing-project workflow:

```bash
azd deploy identity-agent-b
azd deploy identity-agent-a
cd ../..
```

Provision/init behavior is extension-version-sensitive. This existing-project
path was exercised in the reference deployment above. Image-reference packaging
alone is not a successful remote upload, pull, or agent deployment. Follow
[current hosted deployment guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
if the extension requests additional project setup. Before rerunning root
provisioning, confirm its private image digest, registry mode, credential
expiration, and preview.

Both image types have been built for **linux/amd64** through the configured
Microsoft package feed and smoke-tested offline. The API image checks health
and unauthenticated rejection; the hosted image executes the real Responses
handler with synthetic trusted-context headers. Build-secret contents are absent
from both images. These checks are **not** live identity-propagation results.

For P04/P05, first run the A2A endpoint configuration script without `--apply`,
then approve its exact PATCH. **Hosted-target incoming-A2A support is not
established by the current prompt-agent prerequisite**; preserve BLOCKED if
unsupported. Configure remote A2A connections explicitly for v1.0, not default
preview v0.3. Configure OAuth/consent for the custom MCP connection separately.
Toolbox creation and OAuth grants are operator steps, not hidden bootstrap writes.

## 6. Run the two-user experiments

Start with direct invocation:

```bash
identity-lab --config .local/config.json --pattern P01
identity-lab --config .local/config.json
```

Use two distinct existing users. The runner checks a direct B baseline for each
user, then runs each supported configuration. Full runs currently request both
Foundry and API sign-ins even when selecting a direct-only pattern.
Complete toolbox OAuth consent before running; pending-consent cases are BLOCKED.
See [evidence semantics](evidence.md) before interpreting any PASS.

Raw opaque identities remain in `.local/evidence/latest.json`. Review
`.local/evidence/public-candidate.json` manually, copy only reviewed rows into
`results/latest.json`, and run `python scripts/check_public.py`. The checker is a
defense-in-depth allowlist, not proof that arbitrary prose contains no sensitive
information. Never upload the raw evidence, terminal output, or deployment logs.

## 7. Cleanup, explicitly

Maintain a private execution ledger before each write: exact resource group,
resource ID, role-assignment ID/scope/principal, application/service-principal
IDs, credential key ID and expiration, operation status, and whether an object
was newly created or merely reused. Never put credential values in the ledger.
After partial failures, reconcile live state against those exact identifiers
before retrying or deleting; do not adopt objects by display name.

Inspect your exact resource inventory before approving destruction. The root
`azd down` deletes the resource group and its resources, but does not remove
directory apps, service principals, consent grants, or all subscription-level
custom role definitions. Stop hosted agents before leaving a lab idle, and
explicitly review directory/role cleanup against local manifests.
Do not create subscription-wide custom roles merely to run a lab configuration.
If authorization permits changes in only one group, an unsupported permission
path stays BLOCKED rather than widening the deployment boundary.

No cleanup script auto-deletes objects or retries partial deletions.
