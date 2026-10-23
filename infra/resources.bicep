param suffix string
param location string
param environmentName string
param tenantId string
param apiClientId string
@secure()
param apiClientSecret string
param apiRegistryMode string = 'bootstrap'
param apiImage string = 'mcr.microsoft.com/dotnet/samples:aspnetapp'

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
    dailyQuotaGb: '1'
    enableTelemetry: false
  }
}

module insights 'br/public:avm/res/insights/component:0.8.0' = {
  name: 'app-insights'
  params: {
    name: 'appi-${suffix}'
    location: location
    tags: tags
    workspaceResourceId: logs.outputs.resourceId
    applicationType: 'web'
    disableLocalAuth: true
    disableIpMasking: false
    retentionInDays: 30
    enableTelemetry: false
  }
}

module registryDeployment 'br/public:avm/res/container-registry/registry:0.9.1' = {
  name: 'registry'
  params: {
    name: 'registry${suffix}'
    location: location
    tags: tags
    acrAdminUserEnabled: false
    acrSku: 'Basic'
    enableTelemetry: false
  }
}

module containerEnvironment 'br/public:avm/res/app/managed-environment:0.11.2' = {
  name: 'container-environment'
  params: {
    name: 'env-${suffix}'
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    appLogsConfiguration: { destination: 'azure-monitor' }
    infrastructureResourceGroupName: take('ME_env-${suffix}', 63)
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
    diagnosticSettings: [{
      name: 'identity-lab-diagnostics'
      workspaceResourceId: logs.outputs.resourceId
      logCategoriesAndGroups: [{ categoryGroup: 'allLogs' }]
      metricCategories: [{ category: 'AllMetrics' }]
    }]
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

resource projectMonitoring 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'identity-lab-monitoring'
  properties: {
    category: 'AppInsights'
    target: insights.outputs.resourceId
    // The service supports this preview auth type before the published Bicep schema.
    authType: 'ProjectManagedIdentity'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: insights.outputs.resourceId
      ApplicationInsightsConnectionString: insights.outputs.connectionString
    }
  }
}

resource projectDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'identity-lab-diagnostics'
  scope: project
  properties: {
    workspaceId: logs.outputs.resourceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  name: 'registry${suffix}'
}

resource registryDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'identity-lab-diagnostics'
  scope: registry
  properties: {
    workspaceId: logs.outputs.resourceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
    logAnalyticsDestinationType: 'Dedicated'
  }
  dependsOn: [registryDeployment]
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = {
  name: 'env-${suffix}'
}

resource environmentDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'identity-lab-diagnostics'
  scope: environment
  properties: {
    workspaceId: logs.outputs.resourceId
    logs: [
      { category: 'ContainerAppConsoleLogs', enabled: true }
      { category: 'ContainerAppSystemLogs', enabled: true }
    ]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
  dependsOn: [containerEnvironment]
}

module api 'br/public:avm/res/app/container-app:0.23.0' = {
  name: 'api'
  params: {
    name: 'api-${suffix}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    environmentResourceId: containerEnvironment.outputs.resourceId
    managedIdentities: { systemAssigned: true }
    ingressExternal: true
    ingressAllowInsecure: false
    ingressTargetPort: 8000
    scaleSettings: { minReplicas: 0, maxReplicas: 1 }
    registries: apiRegistryMode == 'private'
      ? [{ server: registryDeployment.outputs.loginServer, identity: 'system' }]
      : []
    secrets: [
      { name: 'api-client-secret', value: apiClientSecret }
      { name: 'lab-appinsights', value: insights.outputs.connectionString }
    ]
    diagnosticSettings: [{
      name: 'identity-lab-diagnostics'
      workspaceResourceId: logs.outputs.resourceId
      metricCategories: [{ category: 'AllMetrics' }]
    }]
    containers: [{
      name: 'api'
      image: apiImage
      resources: { cpu: json('0.5'), memory: '1Gi' }
      env: [
        // Keep the bootstrap image on the same port as the eventual Python API.
        { name: 'ASPNETCORE_HTTP_PORTS', value: '8000' }
        { name: 'LAB_TENANT_ID', value: tenantId }
        { name: 'LAB_API_CLIENT_ID', value: apiClientId }
        { name: 'LAB_PUBLIC_HOST', value: 'api-${suffix}.${containerEnvironment.outputs.defaultDomain}' }
        { name: 'LAB_API_CLIENT_SECRET', secretRef: 'api-client-secret' }
        { name: 'LAB_TELEMETRY_ENABLED', value: 'true' }
        { name: 'LAB_APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'lab-appinsights' }
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
output registryName string = registryDeployment.outputs.name
output registryResourceId string = registry.id
output registryEndpoint string = registryDeployment.outputs.loginServer
output environmentResourceId string = containerEnvironment.outputs.resourceId
output apiName string = api.outputs.name
output apiEndpoint string = 'https://${api.outputs.fqdn}'
output apiPrincipalId string = api.outputs.systemAssignedMIPrincipalId!
output applicationInsightsConnectionString string = insights.outputs.connectionString
output applicationInsightsResourceId string = insights.outputs.resourceId
output workspaceResourceId string = logs.outputs.resourceId
