terraform {
  backend "azurerm" {
    resource_group_name  = "rg-aiip-tfstate"
    storage_account_name = "staiiptfstate001"
    container_name       = "tfstate"
    key                  = "dev.terraform.tfstate"
  }
}
