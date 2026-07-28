module "resource_group" {
	source = "../../modules/resource_group"
	name   = var.resource_group_name
	location = var.location
	tags   = var.tags
}

module "storage_account" {
	source              = "../../modules/storage_account"
	name                = var.storage_account_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "event_hub_namespace" {
	source              = "../../modules/event_hub"
	name                = var.event_hub_namespace_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
	key_vault_id        = module.key_vault.id
	depends_on          = [module.key_vault]
}

module "key_vault" {
	source              = "../../modules/key_vault"
	name                = var.key_vault_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
	access_principal_ids = {
		data_factory = module.data_factory.identity_principal_id
	}
}

module "data_factory" {
	source              = "../../modules/data_factory"
	name                = var.data_factory_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
	key_vault_id               = module.key_vault.id
	storage_connection_string  = module.storage_account.primary_connection_string
	# github_puller_endpoint defaults to placeholder; update once Container App is deployed
}

module "databricks" {
	source              = "../../modules/databricks"
	name                = var.databricks_workspace_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "log_analytics" {
	source              = "../../modules/log_analytics"
	name                = var.log_analytics_workspace_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "container_apps_env" {
	source              = "../../modules/container_apps"
	name                = var.container_apps_env_name
	resource_group_name = module.resource_group.name
	location            = var.location
	log_analytics_workspace_id = module.log_analytics.workspace_id
}

resource "databricks_secret_scope" "kv" {
	name = "aiip-kv"
	keyvault_metadata {
		resource_id = module.key_vault.id
		dns_name    = module.key_vault.vault_uri
	}
}

# ── Phase 2: Synapse Serverless SQL Pool ────────────────────────────────────
module "synapse" {
	source              = "../../modules/synapse"
	name                = var.synapse_workspace_name
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags

	# Link Synapse to the ADLS Gen2 filesystem
	adls_filesystem_id  = module.storage_account.adls_raw_filesystem_id
	storage_account_id  = module.storage_account.id

	# SQL admin credentials (pass via TF_VAR_synapse_sql_admin_password env var)
	sql_admin_login     = var.synapse_sql_admin_login
	sql_admin_password  = var.synapse_sql_admin_password

	# Key Vault to store the SQL endpoint secret
	key_vault_id        = module.key_vault.id

	# Your local public IP for Synapse firewall (run: curl -s https://checkip.amazonaws.com)
	caller_ip_address   = var.my_ip_address

	depends_on = [module.key_vault, module.storage_account]
}

# ── Store storage account key in Key Vault (needed by Databricks event_hub_to_delta.py) ──
resource "azurerm_key_vault_secret" "storage_account_key" {
	name         = "storage-account-key"
	value        = module.storage_account.primary_access_key
	key_vault_id = module.key_vault.id
	tags         = var.tags
	depends_on   = [module.key_vault]
}

# ── Phase 4: Azure AI Search ─────────────────────────────────────────────────
module "ai_search" {
	source              = "../../modules/ai_search"
	name                = var.ai_search_name
	resource_group_name = module.resource_group.name
	location            = var.location
	sku                 = var.ai_search_sku
	key_vault_id        = module.key_vault.id
	tags                = var.tags
	depends_on          = [module.key_vault]
}
