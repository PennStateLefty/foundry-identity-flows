# Deploy and reproduce in your own environment

**No Azure deployment has been executed for the published preview.** Local
compilation is not a successful provisioning run. Review every environment,
permission, billable resource, and preview support gate before proceeding.

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
consumption environment, API/MCP app, and Log Analytics workspace. It declares
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
path containing your approved index configuration. The azd manifests pass it as
a BuildKit secret; neither its path nor contents are baked into the image.
Public PyPI is not an automatic fallback. The local feed must be reachable from
the Docker engine. Hosted agents also use the container build, not cloud ZIP
dependency resolution, to preserve this feed boundary.

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
| `PIP_CONFIG_FILE` | Absolute local pip configuration path |

Set the credential through your secret manager or a non-echoing shell prompt.
The Bicep parameter is secure, and Container Apps stores it as a secret reference,
not a plain environment value. This preview uses Container Apps secrets rather
than provisioning a Key Vault; production should use Key Vault references and
certificate/federated credentials where supported.

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

## 4. Apply only the required permissions and deploy the API

Run `scripts/rbac.py --help` for explicit tenant/principal/type/scope arguments.
Every grant defaults to a plan and requires `--apply` plus typed confirmation.
Use project or agent scopes where supported:

| Principal | Scope | Role |
|---|---|---|
| Two test users or test group | A/B or project | Foundry Agent Consumer |
| API's system-assigned identity | A or project | Foundry Agent Consumer |
| API's system-assigned identity | A or project | Custom impersonation role, only for P03 |
| API's system-assigned identity | ACR | AcrPull |
| Deployment operator | ACR | AcrPush |
| Agent A identity | B/project and toolboxes | Required endpoint/tool access |

The deployment operator also needs Foundry authoring rights. Review
[hosted-agent permissions](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agent-permissions)
for the Foundry project's registry image-pull access and role changes introduced
by the hosted deployment tooling; do not grant subscription-wide Owner.

```bash
azd deploy api
```

Set the public API HTTPS endpoint in `.local/config.json`. `/health` is anonymous;
`/invoke` and `/tools/mcp` require delegated API-audience tokens. Disable public
request/body/header logging; the Docker command disables Uvicorn access logs.
`LAB_PUBLIC_HOST` must be the exact deployed API hostname; Bicep sets it for
Container Apps. MCP DNS-rebinding protection stays enabled and rejects other
Host/Origin values. Hosted handlers disable SDK observability setup and access
logging to avoid exporting identity-probe response content.

## 5. Bind and deploy the hosted agents

The second azd project is `agents/azure.yaml`. It references the existing,
successfully provisioned Foundry project rather than declaring another project.
Initialize its local state using the **actual ARM project ID** returned by the
first deployment; do not derive an ID from its endpoint:

```bash
cd agents
azd ai agent init -t ./azure.yaml --project-id "<provisioned-project-resource-id>" --deploy-mode container
```

Review any generated manifest changes before provisioning/deployment. Select an
existing ACR connection or approve the registry connection required by the
current extension. Confirm the selected subscription, existing project, registry,
container deployment mode, and protocol `responses` version `2.0.0`.
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
cd ..
```

Provision/init behavior is extension-version-sensitive. This path has only been
manifest-parsed locally, not live-provisioned. Follow
[current hosted deployment guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
if the extension requests additional project setup. Do not rerun root
infrastructure provisioning blindly: it declares a placeholder API image.

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

Inspect your exact resource inventory before approving destruction. The root
`azd down` deletes the resource group and its resources, but does not remove
directory apps, service principals, consent grants, or all subscription-level
custom role definitions. Stop hosted agents before leaving a lab idle, and
explicitly review directory/role cleanup against local manifests.

No cleanup script auto-deletes objects or retries partial deletions.
