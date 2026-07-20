Bootstrap Terraform state backend (one-time)

Option A — Recommended (manual, one-time via Azure CLI)

This creates a separate resource group and storage account to hold your Terraform state. Run these commands once from a machine with `az` logged in.

```bash
az group create --name rg-aiip-tfstate --location francecentral

az storage account create \
  --name staiiptfstate001 \
  --resource-group rg-aiip-tfstate \
  --location francecentral \
  --sku Standard_LRS \
  --encryption-services blob

az storage container create \
  --name tfstate \
  --account-name staiiptfstate001
```

After running these, your existing `infra/environments/dev/backend.tf` which references `staiiptfstate001` will be usable by `terraform init`.

Option B — Terraform bootstrap folder (pure IaC)

Create a separate folder `infra/bootstrap/` with its own Terraform configuration and local backend. Apply that once to create the backend resources, then switch `environments/dev` to the remote backend. This is more "pure" but more work for a one-time step.

Why manual bootstrap?

Terraform cannot create a backend and use it for the same run. Creating the backend storage account/container once by hand avoids the chicken-and-egg problem and is standard practice.
