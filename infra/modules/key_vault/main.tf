resource "azurerm_key_vault" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = lower(var.sku_name)

  purge_protection_enabled = false

  tags = var.tags
}

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault_access_policy" "access" {
  for_each = var.access_principal_ids

  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = each.value

  secret_permissions = [
    "Get",
    "List",
  ]
}

# Always grant the current caller (Terraform executor) full permissions on secrets
resource "azurerm_key_vault_access_policy" "current_caller" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get",
    "List",
    "Set",
    "Delete",
    "Purge",
  ]
}

resource "azurerm_key_vault_access_policy" "databricks_platform" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d" # fixed Databricks App ID

  secret_permissions = ["Get", "List"]
}
