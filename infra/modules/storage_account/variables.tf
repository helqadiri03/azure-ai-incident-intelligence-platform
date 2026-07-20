variable "name" {
  type        = string
  description = "Name of the storage account"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group name where the storage account will be created"
}

variable "location" {
  type        = string
  description = "Azure location for the storage account"
}

variable "account_tier" {
  type    = string
  default = "Standard"
}

variable "account_replication_type" {
  type    = string
  default = "LRS"
}

variable "is_hns_enabled" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
