resource "azurerm_storage_account" "this" {
  name                     = var.name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.account_tier
  account_replication_type = var.account_replication_type
  is_hns_enabled           = var.is_hns_enabled
  https_traffic_only_enabled = true

  tags = var.tags
}

# ── ADLS Gen2 filesystem (container) — required by Synapse workspace ──────────
resource "azurerm_storage_data_lake_gen2_filesystem" "raw" {
  name               = "raw"
  storage_account_id = azurerm_storage_account.this.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "checkpoints" {
  name               = "checkpoints"
  storage_account_id = azurerm_storage_account.this.id
}
