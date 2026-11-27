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
    # The plug-in that makes random values. Terraform has no way of its own
    # to make a random secret. It makes the owner's key, below.
    random = {
      source  = "hashicorp/random"
      version = "3.9.1"
    }
  }
}

# What is the maintainer's own, and not in this repository: these variables
# get their values from the file terraform.tfvars, which Terraform reads by
# itself and git does not see. See docs/guides/setup-from-zero.md.

# The subscription in which everything is made.
variable "subscription_id" {
  type        = string
  description = "The id of the Azure subscription."
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id

  # A subscription must switch on each family of Azure services once,
  # before its first use. The first apply stopped here: the family of the
  # registry was off. Terraform now switches on every family that this file
  # uses, before it makes anything, so a fresh subscription works too.
  resource_providers_to_register = [
    "Microsoft.App",
    "Microsoft.ContainerRegistry",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.KeyVault",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
  ]
}

# Who is logged in, and to which subscription.
data "azurerm_client_config" "current" {}

# The sign-in name of the maintainer, who becomes an administrator of the
# database.
variable "database_admin_name" {
  type        = string
  description = "The sign-in name of the person who runs terraform, as Microsoft Entra knows it."
}

# The model resource was made by hand, before this file existed, and it is
# not made here. This file only gives the app a role on it, and tells the
# app where it is.
variable "model_resource_id" {
  type        = string
  description = "The Azure id of the model resource: /subscriptions/.../providers/Microsoft.CognitiveServices/accounts/NAME."
}

variable "model_endpoint" {
  type        = string
  description = "The address of the model service. It ends with /openai/v1/."
}

variable "model_deployment" {
  type        = string
  description = "The name that the model has in the model resource."
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

# "This identity may call the models of this model resource", and nothing
# more: it may not change the resource or read its keys. The code asks Azure
# for a token as the identity, so no key of the model exists.
resource "azurerm_role_assignment" "app_calls_the_model" {
  scope                = var.model_resource_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
}

# The vault: Azure's safe for secrets. It holds the one secret of the app,
# the owner's key. A secret is not written into this file or into the
# settings of the app: it rests here, and who may read it is a role.
resource "azurerm_key_vault" "secrets" {
  # The name must be unique in all of Azure, like the name of the registry.
  name                = "kv-book-teller-${local.unique}"
  location            = local.location
  resource_group_name = azurerm_resource_group.product.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  # The cheaper of the two kinds. The other keeps keys in special hardware.
  sku_name = "standard"

  # Rights are given by role assignments, as everywhere in this file, not
  # by the older lists of the vault itself.
  rbac_authorization_enabled = true

  # A deleted secret can be brought back for so many days: the shortest
  # time that Azure offers. A known limit: the vault has a public address,
  # like the database. The login is the wall.
  soft_delete_retention_days = 7
}

# "The person who runs terraform may write and read the secrets of this
# vault." Terraform puts the owner's key in as that person, and the owner
# reads it there.
resource "azurerm_role_assignment" "maintainer_writes_secrets" {
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# "The identity of the app may read this one secret", and nothing more.
# The scope is the secret, not the vault: a second secret in the same vault
# is closed to the app until a role of its own opens it. The role is the
# same in both cases; the scope decides how far it reaches.
resource "azurerm_role_assignment" "app_reads_secrets" {
  scope                = azurerm_key_vault_secret.owner_key.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
  principal_type       = "ServicePrincipal"
}

# The owner's key: 48 random letters and digits. Nobody types it. Only a
# request that sends it may start a run or read one.
# A known limit: Terraform also writes it into its state file, which stays
# on the maintainer's machine and never goes into git.
resource "random_password" "owner_key" {
  length = 48
  # Letters and digits only: the key travels in an HTTP header.
  special = false
}

# The key, kept in the vault. To read it:
#   az keyvault secret show --vault-name VAULT --name owner-key --query value --output tsv
resource "azurerm_key_vault_secret" "owner_key" {
  name         = "owner-key"
  value        = random_password.owner_key.result
  key_vault_id = azurerm_key_vault.secrets.id

  # Terraform writes the secret as the maintainer, so that role must exist
  # first. A new role can need some minutes to work: if this step stops
  # with "forbidden", run the apply again.
  depends_on = [azurerm_role_assignment.maintainer_writes_secrets]
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

  # The one secret of the app. It holds no value: only the address of the
  # owner's key in the vault (a Key Vault reference), and the identity that
  # fetches it. Azure fetches the value and hands it to the container. The
  # address has no version, so a new value in the vault reaches the app: Azure
  # looks for one within 30 minutes, and then starts the app again.
  secret {
    name                = "owner-key"
    key_vault_secret_id = azurerm_key_vault_secret.owner_key.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
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
      # Where the model is. Not secrets: the login is the identity.
      env {
        name  = "BOOK_TELLER_MODEL_ENDPOINT"
        value = var.model_endpoint
      }
      env {
        name  = "BOOK_TELLER_MODEL_DEPLOYMENT"
        value = var.model_deployment
      }
      # The owner's key: not a value, but the name of the secret above.
      env {
        name        = "BOOK_TELLER_OWNER_KEY"
        secret_name = "owner-key"
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
  # the migrations at its start. And its right to read the vault: Azure
  # fetches the owner's key when a new version of the app starts.
  depends_on = [
    azurerm_role_assignment.app_pulls_images,
    azurerm_role_assignment.app_reads_secrets,
    azurerm_postgresql_flexible_server_active_directory_administrator.app,
    azurerm_postgresql_flexible_server_firewall_rule.azure_services,
  ]
}

# The public address of the app, printed after "terraform apply".
output "app_address" {
  value = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}
