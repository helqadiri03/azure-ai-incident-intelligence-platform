module "resource_group" {
	source = "../../modules/resource_group"
	name   = "rg-aiip-dev-frc-001"
	location = var.location
	tags   = var.tags
}

module "storage_account" {
	source              = "../../modules/storage_account"
	name                = "staiipdevfrc001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "event_hub_namespace" {
	source              = "../../modules/event_hub"
	name                = "evhns-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "key_vault" {
	source              = "../../modules/key_vault"
	name                = "kv-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "data_factory" {
	source              = "../../modules/data_factory"
	name                = "adf-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "databricks" {
	source              = "../../modules/databricks"
	name                = "dbw-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "log_analytics" {
	source              = "../../modules/log_analytics"
	name                = "law-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	tags                = var.tags
}

module "container_apps_env" {
	source              = "../../modules/container_apps"
	name                = "cae-aiip-dev-frc-001"
	resource_group_name = module.resource_group.name
	location            = var.location
	log_analytics_workspace_id = module.log_analytics.workspace_id
}

