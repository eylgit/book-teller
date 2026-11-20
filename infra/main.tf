# The cloud of Book Teller, in one file.
#
# Terraform reads this file and makes the cloud match it:
#   terraform plan   lists what it would add, change or delete
#   terraform apply  makes those changes
# Its record of what it made, the state file, stays on the maintainer's
# machine and never goes into git: see .gitignore.
#
# The tests of this file: tests/cloud.tftest.hcl.

terraform {
  # The same version on the maintainer's machine and in the pipeline.
  required_version = "~> 1.17.2"

  required_providers {
    # The plug-in that talks to Azure. Its exact version and checksums
    # are in .terraform.lock.hcl, like backend/uv.lock for Python.
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "5.13.0"
    }
  }
}

# The subscription comes from the variable ARM_SUBSCRIPTION_ID of the
# shell, so its id is not written in this repository.
provider "azurerm" {
  features {}

  # A subscription must switch on each family of Azure services once,
  # before its first use. The first apply stopped here: the family of the
  # registry was off. Terraform now switches on every family that this file
  # uses, before it makes anything, so a fresh subscription works too.
  resource_providers_to_register = [
    "Microsoft.App",
    "Microsoft.ContainerRegistry",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
  ]
}

# Who is logged in, and to which subscription.
data "azurerm_client_config" "current" {}

locals {
  # UK South, the region of the model.
  location = "uksouth"

  # The name of a container registry must be unique in all of Azure.
  # Eight characters from a fingerprint of the subscription make it so,
  # and stay the same on every run. The subscription id itself is not shown.
  unique = substr(sha1(data.azurerm_client_config.current.subscription_id), 0, 8)
}

# A folder in Azure for everything of the product. Delete it, and all of
# this is gone.
resource "azurerm_resource_group" "product" {
  name     = "rg-book-teller"
  location = local.location
}

# Where the cloud keeps what the app writes, also when it fails to start.
# Paid by the amount taken in, so it stops taking logs after 0.1 GB a day.
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "log-book-teller"
  location            = local.location
  resource_group_name = azurerm_resource_group.product.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.1
}

# The private store for the images of the app.
resource "azurerm_container_registry" "images" {
  name                = "crbookteller${local.unique}"
  location            = local.location
  resource_group_name = azurerm_resource_group.product.name
  sku                 = "Basic"

  # The admin user is one name and password for the whole registry.
  # Off: no password exists. The app pulls with its identity instead.
  admin_enabled = false

  # Nobody pulls an image without a login.
  anonymous_pull_enabled = false

  # Rights are given by roles on the whole registry, so the role AcrPull
  # below works. In the newer mode, rights are given per repository, and
  # AcrPull alone gives nothing. Today's default, written down so that
  # Azure cannot change it for us.
  role_assignment_mode = "LegacyRegistryPermissions"
}

# The app's own login to Azure, with no password. It is made before the
# app, so its right to pull images exists before the app first starts.
resource "azurerm_user_assigned_identity" "app" {
  name                = "id-book-teller-app"
  location            = local.location
  resource_group_name = azurerm_resource_group.product.name
}

# "This identity may pull images from this registry", and nothing more.
resource "azurerm_role_assignment" "app_pulls_images" {
  scope                = azurerm_container_registry.images.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
}

# The space where Azure runs the app. No private network: that starts a
# monthly fee.
resource "azurerm_container_app_environment" "apps" {
  name                       = "cae-book-teller"
  location                   = local.location
  resource_group_name        = azurerm_resource_group.product.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
  # Without this line the logs are only streamed, not kept.
  logs_destination = "log-analytics"

  # Azure gives every new environment this profile: pay by the second,
  # zero copies when idle. Written here because Azure adds it anyway: without
  # it, every plan wanted to remove it, and Azure put it back.
  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }
}

# The app: Azure runs the image and gives it a public address.
resource "azurerm_container_app" "app" {
  name                         = "ca-book-teller"
  resource_group_name          = azurerm_resource_group.product.name
  container_app_environment_id = azurerm_container_app_environment.apps.id
  # One revision runs at a time: a new image replaces the old one.
  revision_mode = "Single"
  # The profile of the environment above, which Azure picks anyway.
  workload_profile_name = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  # Pull from our registry, logged in as the identity. No password.
  registry {
    server   = azurerm_container_registry.images.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  # The front door: HTTPS from the internet, passed on to port 8000 inside
  # the container, where uvicorn listens (backend/Dockerfile).
  ingress {
    external_enabled           = true
    target_port                = 8000
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # Zero copies when nobody visits: nothing is paid. The first visitor
    # waits while a copy starts. At most one copy.
    min_replicas = 0
    max_replicas = 1

    container {
      name = "app"
      # A stand-in from Microsoft for the first apply only: no image of
      # ours exists yet. The pipeline puts our image here after each merge.
      image  = "mcr.microsoft.com/k8se/quickstart:latest"
      cpu    = 0.25
      memory = "0.5Gi"
    }
  }

  lifecycle {
    # The pipeline changes the image, not Terraform. Without this line,
    # every plan would want to put the stand-in back.
    ignore_changes = [template[0].container[0].image]
  }

  # The right to pull must exist before the app first starts.
  depends_on = [azurerm_role_assignment.app_pulls_images]
}

# The public address of the app, printed after "terraform apply".
output "app_address" {
  value = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}
