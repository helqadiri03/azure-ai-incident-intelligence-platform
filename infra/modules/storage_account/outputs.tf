output "id" {
  value = azurerm_storage_account.this.id
}

output "name" {
  value = azurerm_storage_account.this.name
}

output "primary_connection_string" {
  value     = azurerm_storage_account.this.primary_connection_string
  sensitive = true
}

# Needed by Synapse module
output "adls_raw_filesystem_id" {
  description = "ADLS Gen2 'raw' filesystem resource ID — passed to Synapse as adls_filesystem_id"
  value       = azurerm_storage_data_lake_gen2_filesystem.raw.id
}

output "primary_access_key" {
  description = "Storage account primary access key — stored in Key Vault"
  value       = azurerm_storage_account.this.primary_access_key
  sensitive   = true
}
