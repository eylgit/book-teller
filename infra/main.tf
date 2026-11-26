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
    "Microsoft.DBforPostgreSQL",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
  ]
}

# Who is logged in, and to which subscription.
data "azurerm_client_config" "current" {}

# The sign-in name of the maintainer, who becomes an administrator of the
# database. It comes from the variable TF_VAR_database_admin_name of the
# shell, so the name of a person is not written in this repository.
variable "database_admin_name" {
  type        = string
  description = "The sign-in name of the person who runs terraform, as Microsoft Entra knows it."
}

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

  # A label, shown in the Azure portal. Nothing reads it. It was first added
  # by hand in the portal, and a plan then wanted to remove it: Terraform
  # removes what this file does not have. So it is written here.
  tags = {
    description = "the container registry of book teller"
  }

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

# The database server: PostgreSQL, run by Azure. Azure installs it, updates
# it and backs it up. It is paid by the hour, used or not, so it is the
# smallest size with the smallest disk.
resource "azurerm_postgresql_flexible_server" "database" {
  # The name must be unique in all of Azure, like the name of the registry.
  name                = "psql-book-teller-${local.unique}"
  location            = local.location
  resource_group_name = azurerm_resource_group.product.name

  # The same version as the database of compose.yaml.
  version = "18"
  # B: burstable, for a server that is idle most of the time. 1 CPU, 2 GB.
  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768
  # The shortest time that Azure offers.
  backup_retention_days = 7

  # No password exists. The server takes only logins of Microsoft Entra:
  # a token goes where a password would go.
  authentication {
    password_auth_enabled         = false
    active_directory_auth_enabled = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  # A public address, guarded by the firewall rule below and by the login.
  # A private network would start a monthly fee.
  public_network_access_enabled = true

  lifecycle {
    # Azure picks the zone, the building inside the region. Without this
    # line, a later plan would want to move the server to "no zone".
    ignore_changes = [zone]
  }
}

# The one database of the app, on that server. Deleting it deletes every row:
# Terraform does that only when this block is taken out of the file.
resource "azurerm_postgresql_flexible_server_database" "book_teller" {
  name      = "book_teller"
  server_id = azurerm_postgresql_flexible_server.database.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# The firewall: who may reach the server at all, before any login.
# In Azure, the range from 0.0.0.0 to 0.0.0.0 does not mean an address. It
# means "anything that runs inside Azure", also of other customers. The app
# has no fixed address of its own, so the rule cannot be narrower without a
# private network. The login is the wall.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "azure-services"
  server_id        = azurerm_postgresql_flexible_server.database.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# The login of the app in the database: its identity, as an administrator.
# The name of the login is the name of the identity, letter for letter.
# An administrator may do more than the app needs: it may also drop the
# database. The app runs its own migrations at its start, so it must be
# allowed to change tables. A later milestone gives it a smaller login.
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "app" {
  server_name         = azurerm_postgresql_flexible_server.database.name
  resource_group_name = azurerm_resource_group.product.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.app.principal_id
  principal_name      = azurerm_user_assigned_identity.app.name
  principal_type      = "ServicePrincipal"
}

# The login of the maintainer: the person who runs terraform.
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "maintainer" {
  server_name         = azurerm_postgresql_flexible_server.database.name
  resource_group_name = azurerm_resource_group.product.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = data.azurerm_client_config.current.object_id
  principal_name      = var.database_admin_name
  principal_type      = "User"

  # One administrator after the other: a server that is busy with one
  # change can refuse a second one.
  depends_on = [azurerm_postgresql_flexible_server_active_directory_administrator.app]
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

      # The settings of the database: environment variables of the
      # container. None is a secret. backend/src/book_teller/settings.py
      # reads them.
      env {
        name  = "BOOK_TELLER_DATABASE_HOST"
        value = azurerm_postgresql_flexible_server.database.fqdn
      }
      env {
        name  = "BOOK_TELLER_DATABASE_NAME"
        value = azurerm_postgresql_flexible_server_database.book_teller.name
      }
      env {
        name  = "BOOK_TELLER_DATABASE_USER"
        value = azurerm_user_assigned_identity.app.name
      }
      # "azure": log in with a token of Microsoft Entra, over an encrypted
      # connection.
      env {
        name  = "BOOK_TELLER_DATABASE_LOGIN"
        value = "azure"
      }
      # Azure's library reads this name by itself: for which identity it
      # asks a token. An id, not a secret.
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }
    }
  }

  lifecycle {
    # The pipeline changes the image, not Terraform. Without this line,
    # every plan would want to put the stand-in back.
    ignore_changes = [template[0].container[0].image]
  }

  # The right to pull must exist before the app first starts. So must its
  # login in the database, and the way through the firewall: the app runs
  # the migrations at its start.
  depends_on = [
    azurerm_role_assignment.app_pulls_images,
    azurerm_postgresql_flexible_server_active_directory_administrator.app,
    azurerm_postgresql_flexible_server_firewall_rule.azure_services,
  ]
}

# The public address of the app, printed after "terraform apply".
output "app_address" {
  value = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}
