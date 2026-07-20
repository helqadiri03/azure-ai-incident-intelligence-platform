variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
  description = "Log Analytics Workspace ID required by container apps environment"
}

variable "tags" {
  type    = map(string)
  default = {}
}
