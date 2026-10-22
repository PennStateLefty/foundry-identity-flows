param suffix string
param location string
param environmentName string
param tenantId string
param apiClientId string
@secure()
param apiClientSecret string

var tags = { 'azd-env-name': environmentName }
var accountName = 'foundry${suffix}'
var projectName = 'identity-project'

module logs 'br/public:avm/res/operational-insights/workspace:0.16.1' = {
  name: 'logs'
  params: {
    name: 'logs-${suffix}'
    location: location
    tags: tags
    dataRetention: 30
    enableTelemetry: false
  }
}

module stack 'br/public:avm/ptn/azd/container-apps-stack:0.4.0' = {
  name: 'container-stack'
  params: {
    containerAppsEnvironmentName: 'env-${suffix}'
    containerRegistryName: 'registry${suffix}'
    logAnalyticsWorkspaceName: logs.outputs.name
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    acrSku: 'Basic'
    zoneRedundant: false
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    enableTelemetry: false
  }
}

module foundry 'br/public:avm/res/cognitive-services/account:0.19.1' = {
  name: 'foundry'
  params: {
    name: accountName
    location: location
    tags: tags
    kind: 'AIServices'
    sku: 'S0'
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    restrictOutboundNetworkAccess: false
    managedIdentities: { systemAssigned: true }
    enableTelemetry: false
  }
}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Foundry identity lab'
    description: 'Deterministic identity propagation experiments'
  }
  dependsOn: [foundry]
}

module api 'br/public:avm/res/app/container-app:0.23.0' = {
  name: 'api'
  params: {
    name: 'api-${suffix}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    environmentResourceId: stack.outputs.environmentResourceId
    managedIdentities: { systemAssigned: true }
    ingressExternal: true
    ingressAllowInsecure: false
    ingressTargetPort: 8000
    scaleSettings: { minReplicas: 0, maxReplicas: 1 }
    registries: [{ server: stack.outputs.registryLoginServer, identity: 'system' }]
    secrets: [{ name: 'api-client-secret', value: apiClientSecret }]
    containers: [{
      name: 'api'
      image: 'mcr.microsoft.com/dotnet/samples:aspnetapp'
      resources: { cpu: json('0.5'), memory: '1Gi' }
      env: [
        // Keep the bootstrap image on the same port as the eventual Python API.
        { name: 'ASPNETCORE_HTTP_PORTS', value: '8000' }
        { name: 'LAB_TENANT_ID', value: tenantId }
        { name: 'LAB_API_CLIENT_ID', value: apiClientId }
        { name: 'LAB_PUBLIC_HOST', value: 'api-${suffix}.${stack.outputs.defaultDomain}' }
        { name: 'LAB_API_CLIENT_SECRET', secretRef: 'api-client-secret' }
        { name: 'FOUNDRY_PROJECT_ENDPOINT', value: project.properties.endpoints['AI Foundry API'] }
        { name: 'LAB_AGENT_A_NAME', value: 'identity-agent-a' }
        { name: 'LAB_AGENT_B_NAME', value: 'identity-agent-b' }
      ]
    }]
    enableTelemetry: false
  }
}

output accountName string = foundry.outputs.name
output projectName string = project.name
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output projectResourceId string = project.id
output registryName string = stack.outputs.registryName
output registryEndpoint string = stack.outputs.registryLoginServer
output environmentResourceId string = stack.outputs.environmentResourceId
output apiName string = api.outputs.name
output apiEndpoint string = 'https://${api.outputs.fqdn}'
output apiPrincipalId string = api.outputs.systemAssignedMIPrincipalId!
