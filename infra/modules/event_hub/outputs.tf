output "namespace_id" {
  value = azurerm_eventhub_namespace.this.id
}

output "namespace_name" {
  value = azurerm_eventhub_namespace.this.name
}

output "deployment_events_hub_name" {
  value = azurerm_eventhub.deployment_events.name
}

output "incident_events_hub_name" {
  value = azurerm_eventhub.incident_events.name
}

output "send_listen_rule_primary_connection_string" {
  value     = azurerm_eventhub_namespace_authorization_rule.send_listen.primary_connection_string
  sensitive = true
}
