variable "name" {
  type        = string
  description = "Azure AI Search service name (must be globally unique, 2-60 chars, lowercase alphanumeric and hyphens)"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group to deploy the search service into"
}

variable "location" {
  type        = string
  description = "Azure region (e.g. francecentral)"
}

variable "sku" {
  type        = string
  description = "Pricing tier: free | basic | standard | standard2 | standard3 | storage_optimized_l1 | storage_optimized_l2"
  default     = "basic"
}

variable "replica_count" {
  type        = number
  description = "Number of replicas (1 for dev, 2+ for HA)"
  default     = 1
}

variable "partition_count" {
  type        = number
  description = "Number of partitions (1 for dev, scales storage & throughput)"
  default     = 1
}

variable "key_vault_id" {
  type        = string
  description = "Resource ID of the Key Vault where admin key and endpoint will be stored as secrets"
}

variable "tags" {
  type    = map(string)
  default = {}
}
