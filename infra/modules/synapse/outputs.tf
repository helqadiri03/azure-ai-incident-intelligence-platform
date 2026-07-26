output "workspace_id" {
  description = "Synapse workspace resource ID"
  value       = azurerm_synapse_workspace.this.id
}

output "sql_on_demand_endpoint" {
  description = "Serverless SQL endpoint — use this in dbt profiles.yml as the 'server'"
  value       = azurerm_synapse_workspace.this.connectivity_endpoints["sqlOnDemand"]
}

output "managed_identity_principal_id" {
  description = "Object ID of the Synapse system-assigned managed identity"
  value       = azurerm_synapse_workspace.this.identity[0].principal_id
}
