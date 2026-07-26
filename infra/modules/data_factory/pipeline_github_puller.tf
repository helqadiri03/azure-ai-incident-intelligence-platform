# ──────────────────────────────────────────────────────────────────────────────
# infra/modules/data_factory/pipeline_github_puller.tf
#
# Step 1.5 – ADF batch pipeline for the GitHub Actions puller
#
# Architecture:
#   Trigger (tumbling-window, 1 h)
#     └─ Pipeline: aiip-github-puller
#           └─ Activity: WebActivity → calls github_puller_function (Container App / Function)
#                  OR
#           └─ Activity: ExecutePipeline → custom script in ADF Self-hosted IR
#
# For Phase 1 (no Container App yet) we use a WebActivity that calls:
#   POST https://<container_app_fqdn>/run
# The URL is stored as an ADF parameter so it can be overridden without
# re-deploying Terraform.
#
# When Event Hub is wired the same pipeline just runs — the puller already
# has send_to_event_hub() ready to call.
# ──────────────────────────────────────────────────────────────────────────────

# ── Linked Service: Azure Key Vault (for secret retrieval inside ADF) ────────
resource "azurerm_data_factory_linked_service_key_vault" "kv" {
  name            = "ls-keyvault-aiip"
  data_factory_id = azurerm_data_factory.this.id
  key_vault_id    = var.key_vault_id
}

# ── Linked Service: Event Hub (for future sink activities) ───────────────────
resource "azurerm_data_factory_linked_service_azure_blob_storage" "output_storage" {
  name              = "ls-blob-aiip-output"
  data_factory_id   = azurerm_data_factory.this.id
  connection_string = var.storage_connection_string
}

# ── Pipeline: GitHub Actions puller ──────────────────────────────────────────
resource "azurerm_data_factory_pipeline" "github_puller" {
  name            = "aiip-github-puller"
  data_factory_id = azurerm_data_factory.this.id
  description     = "Pulls GitHub Actions workflow runs, normalises them into the AIIP deployment-event schema, and publishes to Event Hub (or writes local JSON in Phase 1)."

  parameters = {
    # Override at trigger or manual-run time without touching Terraform
    github_repo     = "helqadiri03/azure-ai-incident-intelligence-platform"
    runner_endpoint = var.github_puller_endpoint   # e.g. Container App URL
    runs_per_page   = "30"
  }

  activities_json = jsonencode([
    {
      name = "RunGitHubPuller"
      type = "WebActivity"
      typeProperties = {
        url    = "@pipeline().parameters.runner_endpoint"
        method = "POST"
        headers = {
          "Content-Type" = "application/json"
        }
        body = jsonencode({
          repo          = "@pipeline().parameters.github_repo"
          runs_per_page = "@pipeline().parameters.runs_per_page"
        })
        # ADF retrieves the PAT from Key Vault at runtime — never stored in plain text
        authentication = {
          type      = "MSI"
          resource  = "https://vault.azure.net"
        }
      }
      policy = {
        timeout                = "00:10:00"
        retry                  = 2
        retryIntervalInSeconds = 30
        secureOutput           = false
        secureInput            = false
      }
      dependsOn = []
    }
  ])
}

# ── Trigger: tumbling window — runs every hour ────────────────────────────────
resource "azurerm_data_factory_trigger_tumbling_window" "github_puller_hourly" {
  name            = "trg-github-puller-1h"
  data_factory_id = azurerm_data_factory.this.id

  # Start from a fixed, hardcoded time in the past to ensure idempotency
  start_time      = "2026-07-24T00:00:00Z"
  frequency       = "Hour"
  interval        = 1
  delay           = "00:02:00"   # 2-min delay to let the run finish landing

  retry {
    count    = 2
    interval = 30
  }

  annotations = ["github-puller", "phase-1.5"]

  pipeline {
    name = azurerm_data_factory_pipeline.github_puller.name
    parameters = {
      github_repo     = "helqadiri03/azure-ai-incident-intelligence-platform"
      runner_endpoint = var.github_puller_endpoint
      runs_per_page   = "30"
    }
  }
}
