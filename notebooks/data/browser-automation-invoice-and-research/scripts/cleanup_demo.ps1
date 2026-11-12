param([Parameter(Mandatory)][string]$Inventory)
$ErrorActionPreference = 'Stop'
$data = Get-Content -LiteralPath $Inventory -Raw | ConvertFrom-Json
$sub = $data.subscription
$group = $data.created_resource_group
$storage = $data.created_storage_account
$connection = $data.created_connection
$role = $data.created_role_assignment
if ($group -notmatch '^rg-bat-forgebook-[a-z0-9]+$' -or $storage -notmatch '^batforge[a-z0-9]+$' -or
    $connection -notmatch '/connections/bat-forgebook-[a-z0-9]+$' -or
    $role -notmatch '/providers/Microsoft.Authorization/roleAssignments/[0-9a-f-]+$') {
    throw 'Inventory scope validation failed; refusing cleanup.'
}
$failures = @()
az rest --subscription $sub --method delete --url "https://management.azure.com${connection}?api-version=2025-06-01" --output none --only-show-errors
if ($LASTEXITCODE -ne 0) { $failures += 'connection' }
az role assignment delete --subscription $sub --ids $role --only-show-errors
if ($LASTEXITCODE -ne 0) { $failures += 'role assignment' }
$resources = az resource list --subscription $sub --resource-group $group --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect hosting group; refusing hosting deletion.' }
$resources = @($resources | ConvertFrom-Json)
if ($resources.Count -ne 1 -or $resources[0].name -ne $storage -or
    $resources[0].type -ne 'Microsoft.Storage/storageAccounts' -or
    $resources[0].tags.purpose -ne 'bat-forgebook-demo') {
    throw 'Hosting inventory differs from the single demo storage account; refusing deletion.'
}
az storage account delete --subscription $sub --resource-group $group --name $storage --yes --only-show-errors
if ($LASTEXITCODE -ne 0) {
    $failures += 'storage'
} else {
    az group delete --subscription $sub --name $group --yes --only-show-errors
    if ($LASTEXITCODE -ne 0) { $failures += 'resource group' }
}
if ($failures.Count) { throw "Cleanup failed for: $($failures -join ', ')" }
Write-Output 'Removed only the inventoried demo connection, role, storage account, and resource group.'
