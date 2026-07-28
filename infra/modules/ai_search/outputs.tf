output "id" {
  description = "Resource ID of the Azure AI Search service"
  value       = azurerm_search_service.this.id
}

output "name" {
  description = "Name of the Azure AI Search service"
  value       = azurerm_search_service.this.name
}

output "endpoint" {
  description = "HTTPS endpoint for the Azure AI Search service"
  value       = "https://${azurerm_search_service.this.name}.search.windows.net"
}

output "primary_key" {
  description = "Primary admin key for the Azure AI Search service"
  value       = azurerm_search_service.this.primary_key
  sensitive   = true
}
