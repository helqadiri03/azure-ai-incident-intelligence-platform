variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}


variable "sku_name" {
  type    = string
  default = "standard"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "access_principal_ids" {
  type    = map(string)
  default = {}
  description = "Map of principal identifiers to object IDs to grant secret read permissions on the key vault"
}

