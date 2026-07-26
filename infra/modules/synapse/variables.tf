variable "name" {
  type        = string
  description = "Synapse workspace name (e.g. syn-aiip-dev-frc-001)"
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ── ADLS Gen2 filesystem ID — links Synapse to the data lake ─────────────────
# Format: https://<account>.dfs.core.windows.net/<container>
variable "adls_filesystem_id" {
  type        = string
  description = "ADLS Gen2 filesystem resource ID (azurerm_storage_data_lake_gen2_filesystem.this.id)"
}

# ── Storage account resource ID (for RBAC assignment) ────────────────────────
variable "storage_account_id" {
  type        = string
  description = "Resource ID of the ADLS storage account"
}

# ── SQL serverless admin credentials ─────────────────────────────────────────
variable "sql_admin_login" {
  type        = string
  description = "SQL administrator login name"
  default     = "sqladmin"
}

variable "sql_admin_password" {
  type        = string
  description = "SQL administrator password — store in Key Vault, pass via TF_VAR_ or -var"
  sensitive   = true
}

# ── Key Vault to write the SQL endpoint secret into ──────────────────────────
variable "key_vault_id" {
  type        = string
  description = "Resource ID of the Key Vault where the SQL endpoint will be stored"
}

# ── Caller IP for firewall (run: curl -s https://checkip.amazonaws.com) ──────
variable "caller_ip_address" {
  type        = string
  description = "Public IP of the machine running Terraform — added to Synapse firewall"
  default     = "0.0.0.0"
}
