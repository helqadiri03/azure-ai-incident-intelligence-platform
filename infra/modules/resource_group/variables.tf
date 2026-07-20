variable "name" {
  type        = string
  description = "Name of the resource group"
}

variable "location" {
  type        = string
  description = "Azure location for the resource group"
}

variable "tags" {
  type    = map(string)
  default = {}
}
