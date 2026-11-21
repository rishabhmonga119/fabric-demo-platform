targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workspaceName string = 'dbw-demo'
param storageAccountName string = 'stdemolake${uniqueString(resourceGroup().id)}'
param accessConnectorName string = 'ac-dbw-demo'
param owner string = 'rishabhmonga119/fabric-demo-platform'

var tags = {
  demoOwner: owner
  createdBy: 'copilot-demo-build'
}
var blobContributorRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)
var managedResourceGroupId = '${subscription().id}/resourceGroups/rg-demo-databricks-managed'

// https://learn.microsoft.com/azure/templates/microsoft.storage/2023-05-01/storageaccounts
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    isHnsEnabled: true
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Public network access is demo-only; containers still require authentication.
// https://learn.microsoft.com/azure/templates/microsoft.storage/2023-05-01/storageaccounts/blobservices/containers
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  name: 'default'
  parent: storage
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for stage in ['dev', 'test', 'prod']: {
    name: 'uc-${stage}'
    parent: blobService
    properties: {
      publicAccess: 'None'
      metadata: {
        demoOwner: owner
        createdBy: 'copilot-demo-build'
      }
    }
  }
]

// https://learn.microsoft.com/azure/templates/microsoft.databricks/2023-05-01/accessconnectors
resource connector 'Microsoft.Databricks/accessConnectors@2023-05-01' = {
  name: accessConnectorName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// https://learn.microsoft.com/azure/templates/microsoft.authorization/2022-04-01/roleassignments
// https://learn.microsoft.com/azure/databricks/connect/unity-catalog/cloud-storage/azure-managed-identities
resource storageGrant 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, connector.id, blobContributorRole)
  scope: storage
  properties: {
    roleDefinitionId: blobContributorRole
    principalId: connector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// https://learn.microsoft.com/azure/templates/microsoft.databricks/2024-05-01/workspaces
// https://learn.microsoft.com/azure/databricks/data-governance/unity-catalog/enable-workspaces
resource workspace 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: workspaceName
  location: location
  tags: tags
  sku: {
    name: 'premium'
  }
  properties: {
    managedResourceGroupId: managedResourceGroupId
    defaultCatalog: {
      initialType: 'UnityCatalog'
    }
    publicNetworkAccess: 'Enabled'
    parameters: {
      enableNoPublicIp: {
        value: true
      }
    }
  }
}

output workspaceId string = workspace.id
output workspaceUrl string = 'https://${workspace.properties.workspaceUrl}'
output accessConnectorId string = connector.id
output accessConnectorPrincipalId string = connector.identity.principalId
output storageAccountName string = storage.name
output storageAccountId string = storage.id
output managedResourceGroupId string = managedResourceGroupId
