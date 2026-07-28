# ─────────────────────────────────────────────────────────────────────────────
# Azure AI Search (Cognitive Search) Service
# ─────────────────────────────────────────────────────────────────────────────

resource "azurerm_search_service" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  replica_count       = var.replica_count
  partition_count     = var.partition_count
  tags                = var.tags
}

# ── Store the primary admin key in Key Vault ──────────────────────────────────
resource "azurerm_key_vault_secret" "search_admin_key" {
  name         = "search-admin-key"
  value        = azurerm_search_service.this.primary_key
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "search_endpoint" {
  name         = "search-endpoint"
  value        = "https://${azurerm_search_service.this.name}.search.windows.net"
  key_vault_id = var.key_vault_id
  tags         = var.tags
}
