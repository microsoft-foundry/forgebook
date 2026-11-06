param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$StorageAccount,
    [Parameter(Mandatory)][string]$RenderedForm
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $RenderedForm).Path
if ((Get-Content -LiteralPath $source -Raw).Contains('__DEMO_MARKER__')) {
    throw 'Render the per-run marker before uploading the form.'
}
$exists = az group exists --subscription $SubscriptionId --name $ResourceGroup --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Resource group lookup failed.' }
if ($exists -eq 'true') { throw 'Refusing to reuse or modify an existing hosting resource group.' }
az group create --subscription $SubscriptionId --name $ResourceGroup --location eastus --tags purpose=bat-forgebook-demo --output none --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Demo resource group creation failed.' }
az storage account create --subscription $SubscriptionId --resource-group $ResourceGroup --name $StorageAccount --location eastus --sku Standard_LRS --kind StorageV2 --https-only true --min-tls-version TLS1_2 --allow-blob-public-access false --tags purpose=bat-forgebook-demo --output none --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Demo storage creation failed; inspect the named resource group for cleanup.' }
az storage blob service-properties update --subscription $SubscriptionId --account-name $StorageAccount --auth-mode key --static-website --index-document invoice-entry.html --404-document invoice-entry.html --output none --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Static website configuration failed.' }
az storage blob upload --subscription $SubscriptionId --account-name $StorageAccount --auth-mode key --container-name '$web' --name invoice-entry.html --file $source --content-type 'text/html; charset=utf-8' --output none --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Synthetic form upload failed.' }
az storage account show --subscription $SubscriptionId --resource-group $ResourceGroup --name $StorageAccount --query primaryEndpoints.web --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve demo URL.' }
