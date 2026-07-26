output "id" {
  value = azurerm_data_factory.this.id
}

output "name" {
  value = azurerm_data_factory.this.name
}

output "identity_principal_id" {
  value = azurerm_data_factory.this.identity[0].principal_id
}

output "github_puller_pipeline_name" {
  value = azurerm_data_factory_pipeline.github_puller.name
}

output "github_puller_trigger_name" {
  value = azurerm_data_factory_trigger_tumbling_window.github_puller_hourly.name
}
