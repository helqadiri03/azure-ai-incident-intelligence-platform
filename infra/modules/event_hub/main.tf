# ── Namespace (already existed) ──────────────────────────────────────────────
resource "azurerm_eventhub_namespace" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = var.sku
  capacity            = var.capacity
  tags                = var.tags
}

# ── Hub: deployment events (GitHub Actions runs) ───────────────────────────
resource "azurerm_eventhub" "deployment_events" {
  name                = "aiip-deployment-events"
  namespace_id        = azurerm_eventhub_namespace.this.id
  partition_count     = 4
  message_retention   = 7
}

# ── Hub: incident telemetry (app logs, k8s, metrics, traces) ──────────────
resource "azurerm_eventhub" "incident_events" {
  name                = "aiip-incident-events"
  namespace_id        = azurerm_eventhub_namespace.this.id
  partition_count     = 8   # higher throughput — 4 signal types × 2
  message_retention   = 7
}

# ── Send and Listen authorization rule (used by producers and consumers) ────────────
resource "azurerm_eventhub_namespace_authorization_rule" "send_listen" {
  name                = "aiip-ingestion-auth"
  namespace_name      = azurerm_eventhub_namespace.this.name
  resource_group_name = var.resource_group_name

  listen = true
  send   = true
  manage = false
}

# ── Store connection string and names in Key Vault so producers/consumers never hard-code it ──
resource "azurerm_key_vault_secret" "eventhub_connection_string" {
  name         = "eventhub-connection-string"
  value        = azurerm_eventhub_namespace_authorization_rule.send_listen.primary_connection_string
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "eventhub_name" {
  name         = "eventhub-name"
  value        = azurerm_eventhub.deployment_events.name
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "eventhub_namespace" {
  name         = "eventhub-namespace"
  value        = azurerm_eventhub_namespace.this.name
  key_vault_id = var.key_vault_id
  tags         = var.tags
}
