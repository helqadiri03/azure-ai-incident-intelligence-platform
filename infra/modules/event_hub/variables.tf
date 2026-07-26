variable "name" {
  type        = string
  description = "Name of the Event Hub Namespace"
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "sku" {
  type    = string
  default = "Standard"
}

variable "capacity" {
  type        = number
  default     = 1
  description = "Throughput units (1–20 for Standard tier)"
}

variable "key_vault_id" {
  type        = string
  description = "Resource ID of the Key Vault where the connection string secret will be stored"
}

variable "tags" {
  type    = map(string)
  default = {}
}
