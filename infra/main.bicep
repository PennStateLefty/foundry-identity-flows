targetScope = 'subscription'

@minLength(2)
@maxLength(32)
param environmentName string
param location string
param tenantId string = tenant().tenantId
param apiClientId string
@secure()
param apiClientSecret string

var suffix = uniqueString(subscription().id, environmentName, location)
resource group 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

module resources 'resources.bicep' = {
  name: 'identity-lab'
  scope: group
  params: {
    suffix: suffix
    location: location
    environmentName: environmentName
    tenantId: tenantId
    apiClientId: apiClientId
    apiClientSecret: apiClientSecret
  }
}

output AZURE_RESOURCE_GROUP string = group.name
output AZURE_AI_ACCOUNT_NAME string = resources.outputs.accountName
output AZURE_AI_PROJECT_NAME string = resources.outputs.projectName
output AZURE_AI_PROJECT_ENDPOINT string = resources.outputs.projectEndpoint
output AZURE_AI_PROJECT_RESOURCE_ID string = resources.outputs.projectResourceId
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryEndpoint
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = resources.outputs.environmentResourceId
output SERVICE_API_NAME string = resources.outputs.apiName
output SERVICE_API_ENDPOINT_URL string = resources.outputs.apiEndpoint
output API_PRINCIPAL_ID string = resources.outputs.apiPrincipalId
