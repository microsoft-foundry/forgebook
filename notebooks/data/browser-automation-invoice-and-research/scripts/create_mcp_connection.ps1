param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$Account,
    [Parameter(Mandatory)][string]$Project,
    [Parameter(Mandatory)][string]$ConnectionName,
    [Parameter(Mandatory)][string]$WorkspaceResourceId
)
$ErrorActionPreference = 'Stop'
if ($ConnectionName -notmatch '^bat-forgebook-[a-z0-9]+$' -or
    $WorkspaceResourceId -notmatch "^/subscriptions/$([regex]::Escape($SubscriptionId))/resourceGroups/[^/]+/providers/Microsoft.LoadTestService/playwrightWorkspaces/[^/]+$") {
    throw 'Use a unique demo connection and an explicitly scoped workspace in this subscription.'
}
$projectId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$Account/projects/$Project"
$connections = az rest --subscription $SubscriptionId --method get --url "https://management.azure.com${projectId}/connections?api-version=2025-06-01" --query 'value[].id' --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect project connections.' }
$connectionId = "$projectId/connections/$ConnectionName"
if (@($connections | ConvertFrom-Json) -contains $connectionId) {
    throw 'Refusing to replace an existing connection.'
}
$workspace = az resource show --subscription $SubscriptionId --ids $WorkspaceResourceId --output json --only-show-errors | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $workspace.properties.provisioningState -ne 'Succeeded') {
    throw 'Workspace lookup or provisioning state is invalid.'
}
$region = $workspace.location
$workspaceId = $workspace.properties.workspaceId
if ($region -notmatch '^[a-z0-9]+$' -or $workspaceId -notmatch '^[0-9a-f-]{36}$') {
    throw 'Workspace endpoint metadata is invalid.'
}
$endpoint = "https://$region.mcp.playwright.microsoft.com/playwrightworkspaces/$workspaceId/mcp"
$body = @{
    properties = @{
        category = 'RemoteTool'
        target = $endpoint
        authType = 'ProjectManagedIdentity'
        audience = 'https://mcp.playwright.microsoft.com'
        metadata = @{ ResourceId = $WorkspaceResourceId }
    }
} | ConvertTo-Json -Depth 5
$temp = [IO.Path]::GetTempFileName()
try {
    $body | Set-Content -LiteralPath $temp -Encoding utf8
    az rest --subscription $SubscriptionId --method put --url "https://management.azure.com${connectionId}?api-version=2025-06-01" --body "@$temp" --output none --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'MCP managed-identity connection creation failed.' }
    az rest --subscription $SubscriptionId --method get --url "https://management.azure.com${connectionId}?api-version=2025-06-01" --query '{id:id,properties:properties}' --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'MCP connection readback failed.' }
} finally {
    Remove-Item -LiteralPath $temp
}
