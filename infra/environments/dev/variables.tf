variable "resource_group_name" {
	type = string
}

variable "storage_account_name" {
	type = string
}

variable "event_hub_namespace_name" {
	type = string
}

variable "key_vault_name" {
	type = string
}

variable "data_factory_name" {
	type = string
}

variable "databricks_workspace_name" {
	type = string
}

variable "container_apps_env_name" {
	type = string
}

variable "location" {
	type        = string
	description = "Azure location for this environment"
}

variable "tags" {
	type    = map(string)
	default = {}
}

variable "access_principal_ids" {
  type        = list(string)
  description = "Object IDs of identities granted Key Vault access"
  default     = []
}


