provider "azurerm" {
	features {}
}

terraform {
	required_providers {
		azurerm = {
			source  = "hashicorp/azurerm"
		}
		databricks = {
			source = "databricks/databricks"
		}
	}
}

provider "databricks" {
	host = module.databricks.workspace_url
}

