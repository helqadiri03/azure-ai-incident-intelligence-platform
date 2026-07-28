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

variable "log_analytics_workspace_name" {
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
  type        = map(string)
  description = "Map of identifiers to object IDs of identities granted Key Vault access"
  default     = {}
}

# ── Phase 2: Synapse Serverless SQL Pool ─────────────────────────────────────
variable "synapse_workspace_name" {
  type        = string
  description = "Synapse workspace name (e.g. syn-aiip-dev-frc-001)"
}

variable "synapse_sql_admin_login" {
  type        = string
  description = "Synapse SQL administrator login"
  default     = "sqladmin"
}

variable "synapse_sql_admin_password" {
  type        = string
  description = "Synapse SQL administrator password — set via TF_VAR_synapse_sql_admin_password env var, never commit to git"
  sensitive   = true
}

variable "my_ip_address" {
  type        = string
  description = "Your local public IP (curl -s https://checkip.amazonaws.com) — added to Synapse firewall"
  default     = "0.0.0.0"
}

# ── Phase 4: Azure AI Search ─────────────────────────────────────────────────
variable "ai_search_name" {
  type        = string
  description = "Globally unique name for the Azure AI Search service (e.g. srch-aiip-dev-frc-001)"
}

variable "ai_search_sku" {
  type        = string
  description = "Pricing tier for AI Search: free | basic | standard"
  default     = "basic"
}
