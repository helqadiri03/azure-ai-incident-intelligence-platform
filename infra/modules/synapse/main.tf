data "azurerm_client_config" "current" {}

# ── Synapse Workspace (Serverless SQL Pool is built-in — no dedicated pool needed) ──
resource "azurerm_synapse_workspace" "this" {
  name                                 = var.name
  resource_group_name                  = var.resource_group_name
  location                             = var.location
  storage_data_lake_gen2_filesystem_id = var.adls_filesystem_id
  sql_administrator_login              = var.sql_admin_login
  sql_administrator_login_password     = var.sql_admin_password

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# ── Firewall: allow Azure services + current caller's public IP ───────────────
resource "azurerm_synapse_firewall_rule" "allow_azure_services" {
  name                 = "AllowAllWindowsAzureIps"
  synapse_workspace_id = azurerm_synapse_workspace.this.id
  start_ip_address     = "0.0.0.0"
  end_ip_address       = "0.0.0.0"
}

resource "azurerm_synapse_firewall_rule" "allow_caller" {
  name                 = "AllowCallerIP"
  synapse_workspace_id = azurerm_synapse_workspace.this.id
  start_ip_address     = var.caller_ip_address
  end_ip_address       = var.caller_ip_address
}

# ── Grant Synapse managed identity Storage Blob Data Reader on the ADLS account ──
resource "azurerm_role_assignment" "synapse_storage_reader" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_synapse_workspace.this.identity[0].principal_id
}

# ── Store SQL serverless endpoint in Key Vault so dbt profiles.yml can reference it ──
resource "azurerm_key_vault_secret" "synapse_sql_endpoint" {
  name         = "synapse-sql-endpoint"
  value        = azurerm_synapse_workspace.this.connectivity_endpoints["sqlOnDemand"]
  key_vault_id = var.key_vault_id
  tags         = var.tags

  depends_on = [azurerm_synapse_workspace.this]
}

# ── Grant Synapse managed identity Key Vault secret read permissions ──────────
resource "azurerm_key_vault_access_policy" "synapse" {
  key_vault_id = var.key_vault_id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_synapse_workspace.this.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}
