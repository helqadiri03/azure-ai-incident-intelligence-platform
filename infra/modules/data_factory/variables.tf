variable "name" {
  type = string
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

variable "key_vault_id" {
  type        = string
  description = "Resource ID of the Key Vault — used to create a Linked Service so ADF can retrieve secrets at runtime"
}

variable "storage_connection_string" {
  type        = string
  sensitive   = true
  description = "Primary connection string of the output Storage Account (for the ADF Blob linked service)"
}

variable "github_puller_endpoint" {
  type        = string
  description = "HTTP endpoint that runs the GitHub puller (Container App URL or Azure Function URL). Passed as a pipeline parameter so it can be overridden at runtime."
  default     = "https://placeholder.example.com/run"
}
