# Tests of the cloud file, main.tf. Run them in the folder infra:
#
#     terraform test
#
# The mock provider is a stand-in for Azure: it takes the file and gives
# made-up answers, such as a made-up id for each thing. So these tests need
# no login, make nothing, and cost nothing. They check what the file asks
# for, not what Azure does with it.

mock_provider "azurerm" {
  # The provider checks that an id has the shape of an Azure address. A
  # made-up id like "hoq2izpc" fails that check, so the stand-in is given
  # ids in the real shape, under a subscription id of zeros.
  mock_resource "azurerm_resource_group" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller"
    }
  }
  mock_resource "azurerm_log_analytics_workspace" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.OperationalInsights/workspaces/log-book-teller"
    }
  }
  mock_resource "azurerm_container_registry" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.ContainerRegistry/registries/crbooktellertest"
      login_server = "crbooktellertest.azurecr.io"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-book-teller-app"
      principal_id = "11111111-1111-1111-1111-111111111111"
      client_id    = "44444444-4444-4444-4444-444444444444"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-book-teller-test"
      fqdn = "psql-book-teller-test.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server_database" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-book-teller-test/databases/book_teller"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server_firewall_rule" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-book-teller-test/firewallRules/azure-services"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server_active_directory_administrator" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-book-teller-test/administrators/11111111-1111-1111-1111-111111111111"
    }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.App/managedEnvironments/cae-book-teller"
    }
  }
  mock_resource "azurerm_container_app" {
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.App/containerApps/ca-book-teller"
    }
  }
  mock_resource "azurerm_key_vault" {
    defaults = {
      id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-book-teller/providers/Microsoft.KeyVault/vaults/kv-book-teller-test"
      vault_uri = "https://kv-book-teller-test.vault.azure.net/"
    }
  }
  # A secret has an address, not an id of the usual shape. With a version at
  # its end it names one value; without, always the newest.
  mock_resource "azurerm_key_vault_secret" {
    defaults = {
      id             = "https://kv-book-teller-test.vault.azure.net/secrets/owner-key/0123456789abcdef0123456789abcdef"
      versionless_id = "https://kv-book-teller-test.vault.azure.net/secrets/owner-key"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000000"
      tenant_id       = "22222222-2222-2222-2222-222222222222"
      object_id       = "33333333-3333-3333-3333-333333333333"
    }
  }
}

# The stand-in for the plug-in that makes random values. It gives a made-up
# text where the real one gives a random one.
mock_provider "random" {}

# What is the maintainer's own is not in main.tf: the subscription, the
# sign-in name, and the three facts of the model resource, which was made by
# hand. They come from a file that git does not see. The tests hand in
# made-up ones.
variables {
  subscription_id     = "00000000-0000-0000-0000-000000000000"
  database_admin_name = "maintainer@example.invalid"
  model_resource_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-model/providers/Microsoft.CognitiveServices/accounts/model-test"
  model_endpoint      = "https://model-test.example.invalid/openai/v1/"
  model_deployment    = "a-deployment"
}

run "the_cloud_as_written" {
  # "apply" against the mock: the made-up ids exist, so the tests can check
  # that one thing points to another, e.g. the role to the registry.
  command = apply

  # 1. Zero copies when nobody visits, and at most one.
  assert {
    condition     = azurerm_container_app.app.template[0].min_replicas == 0
    error_message = "The app must have zero copies when nobody visits."
  }
  assert {
    condition     = azurerm_container_app.app.template[0].max_replicas == 1
    error_message = "The app must have at most one copy."
  }

  # 2. Requests from the internet, to the port of the app, over HTTPS only.
  assert {
    condition     = azurerm_container_app.app.ingress[0].external_enabled == true
    error_message = "The app must take requests from the internet."
  }
  assert {
    condition     = azurerm_container_app.app.ingress[0].target_port == 8000
    error_message = "Requests must go to port 8000, where uvicorn listens (backend/Dockerfile)."
  }
  assert {
    condition     = azurerm_container_app.app.ingress[0].allow_insecure_connections == false
    error_message = "The app must take HTTPS only, no plain HTTP."
  }

  # 3. The registry has no password: no admin user, and no pull without a login.
  assert {
    condition     = azurerm_container_registry.images.admin_enabled == false
    error_message = "The admin user of the registry must be off: it is a password."
  }
  assert {
    condition     = azurerm_container_registry.images.anonymous_pull_enabled == false
    error_message = "Nobody may pull an image from the registry without a login."
  }

  # The label of the registry, as it is in Azure. Without it in the file,
  # every plan wants to remove it.
  assert {
    condition     = azurerm_container_registry.images.tags == tomap({ description = "the container registry of book teller" })
    error_message = "The registry must keep its label, the tag description."
  }

  # 4. The app runs as its own identity, and pulls images as that identity.
  assert {
    condition     = azurerm_container_app.app.identity[0].type == "UserAssigned"
    error_message = "The app must run as a user-assigned identity."
  }
  assert {
    condition     = azurerm_container_app.app.identity[0].identity_ids == toset([azurerm_user_assigned_identity.app.id])
    error_message = "The app must run as the identity of this file, and only as it."
  }
  assert {
    condition     = length(azurerm_container_app.app.registry) == 1
    error_message = "The app must know exactly one registry."
  }
  assert {
    condition     = azurerm_container_app.app.registry[0].server == azurerm_container_registry.images.login_server
    error_message = "The app must pull from the registry of this file."
  }
  assert {
    condition     = azurerm_container_app.app.registry[0].identity == azurerm_user_assigned_identity.app.id
    error_message = "The app must log in to the registry as its identity, not with a password."
  }

  # 5. The role: that identity may pull images from that registry.
  assert {
    condition     = azurerm_role_assignment.app_pulls_images.role_definition_name == "AcrPull"
    error_message = "The role must be AcrPull: pull images, nothing more."
  }
  assert {
    condition     = azurerm_role_assignment.app_pulls_images.scope == azurerm_container_registry.images.id
    error_message = "The role must be on the registry, not on more."
  }
  assert {
    condition     = azurerm_role_assignment.app_pulls_images.principal_id == azurerm_user_assigned_identity.app.principal_id
    error_message = "The role must be given to the identity of the app."
  }

  # 6. The app holds no value of a secret. It has one secret, the owner's
  # key, and that is only a pointer: the address of the secret in the vault,
  # and the identity that fetches it. (Before the owner's key existed, this
  # test said: the app has no secret at all.)
  assert {
    condition     = length(azurerm_container_app.app.secret) == 1
    error_message = "The app must have exactly one secret: the owner's key."
  }
  assert {
    condition     = one(azurerm_container_app.app.secret[*].name) == "owner-key"
    error_message = "The one secret of the app must be the owner's key."
  }
  assert {
    condition     = alltrue([for each in azurerm_container_app.app.secret : each.value == null || each.value == ""])
    error_message = "The secret of the app must hold no value: the value stays in the vault."
  }
  assert {
    # The address without a version: the app always gets the newest value.
    condition     = one(azurerm_container_app.app.secret[*].key_vault_secret_id) == azurerm_key_vault_secret.owner_key.versionless_id
    error_message = "The secret of the app must point to the owner's key in the vault of this file."
  }
  assert {
    condition     = one(azurerm_container_app.app.secret[*].identity) == azurerm_user_assigned_identity.app.id
    error_message = "The secret must be fetched as the identity of the app."
  }

  # 7. Every thing is in UK South, the region of the model.
  # The container app is not in the list: it has no region setting of its
  # own, and Azure puts it where its environment is.
  assert {
    condition = alltrue([
      azurerm_resource_group.product.location == "uksouth",
      azurerm_container_registry.images.location == "uksouth",
      azurerm_log_analytics_workspace.logs.location == "uksouth",
      azurerm_user_assigned_identity.app.location == "uksouth",
      azurerm_container_app_environment.apps.location == "uksouth",
      azurerm_postgresql_flexible_server.database.location == "uksouth",
    ])
    error_message = "Every thing must be in UK South (uksouth)."
  }

  # 8. The logs have a daily cap, so they cannot grow into a bill.
  assert {
    condition     = azurerm_log_analytics_workspace.logs.daily_quota_gb == 0.1
    error_message = "The log workspace must stop taking logs after 0.1 GB a day."
  }

  # 9. The database server has no password: only logins of Microsoft Entra.
  assert {
    condition     = azurerm_postgresql_flexible_server.database.authentication[0].password_auth_enabled == false
    error_message = "The login with a password must be off on the database server."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.database.authentication[0].active_directory_auth_enabled == true
    error_message = "The login with Microsoft Entra must be on."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.database.authentication[0].tenant_id == data.azurerm_client_config.current.tenant_id
    error_message = "The logins must come from the tenant of this subscription."
  }

  # 10. The smallest server: it is paid by the hour, used or not.
  assert {
    condition     = azurerm_postgresql_flexible_server.database.sku_name == "B_Standard_B1ms"
    error_message = "The database server must be the smallest size, B1ms."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.database.storage_mb == 32768
    error_message = "The database server must have 32 GB, the smallest disk."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.database.version == "18"
    error_message = "The database server must run PostgreSQL 18, as compose.yaml does."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.database.backup_retention_days == 7
    error_message = "Backups are kept for 7 days, the shortest time."
  }

  # 11. The one database of the app, on that server.
  assert {
    condition     = azurerm_postgresql_flexible_server_database.book_teller.name == "book_teller"
    error_message = "The database must have the name book_teller."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_database.book_teller.server_id == azurerm_postgresql_flexible_server.database.id
    error_message = "The database must be on the server of this file."
  }

  # 12. The firewall rule lets Azure's own services in, and names no other
  # address. In Azure, the range from 0.0.0.0 to 0.0.0.0 has this meaning.
  # (A test cannot count the rules: it can only look at the ones it names.)
  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.azure_services.start_ip_address == "0.0.0.0"
    error_message = "The firewall rule must start at 0.0.0.0: Azure's services."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.azure_services.end_ip_address == "0.0.0.0"
    error_message = "The firewall rule must end at 0.0.0.0: Azure's services, and no address of the internet."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_firewall_rule.azure_services.server_id == azurerm_postgresql_flexible_server.database.id
    error_message = "The firewall rule must be on the server of this file."
  }

  # 13. Two administrators: the identity of the app, and the maintainer.
  assert {
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.app.object_id == azurerm_user_assigned_identity.app.principal_id
    error_message = "The first administrator must be the identity of the app."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.app.principal_type == "ServicePrincipal"
    error_message = "The identity of the app is a service principal: the login of a program."
  }
  assert {
    # The name of the login in the database is this name, letter for letter.
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.app.principal_name == azurerm_user_assigned_identity.app.name
    error_message = "The login of the app must carry the name of its identity."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.maintainer.object_id == data.azurerm_client_config.current.object_id
    error_message = "The second administrator must be the person who runs terraform."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.maintainer.principal_type == "User"
    error_message = "The maintainer is a user: a person."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server_active_directory_administrator.maintainer.principal_name == "maintainer@example.invalid"
    error_message = "The name of the maintainer must come from the variable, not from the file."
  }
  assert {
    condition = alltrue([
      azurerm_postgresql_flexible_server_active_directory_administrator.app.server_name == azurerm_postgresql_flexible_server.database.name,
      azurerm_postgresql_flexible_server_active_directory_administrator.maintainer.server_name == azurerm_postgresql_flexible_server.database.name,
    ])
    error_message = "Both administrators must be on the server of this file."
  }

  # 14. The app is told where the database is, and to log in with a token;
  # and where the model is. These are settings, not secrets, so they are
  # plain values. The owner's key is not in this list: see 15.
  assert {
    condition = { for each in azurerm_container_app.app.template[0].container[0].env : each.name => each.value if each.name != "BOOK_TELLER_OWNER_KEY" } == {
      BOOK_TELLER_DATABASE_HOST  = azurerm_postgresql_flexible_server.database.fqdn
      BOOK_TELLER_DATABASE_NAME  = "book_teller"
      BOOK_TELLER_DATABASE_USER  = azurerm_user_assigned_identity.app.name
      BOOK_TELLER_DATABASE_LOGIN = "azure"
      # Which identity the code asks a token for.
      AZURE_CLIENT_ID = azurerm_user_assigned_identity.app.client_id
      # The model: its address and the name of its deployment, from the
      # variables.
      BOOK_TELLER_MODEL_ENDPOINT   = "https://model-test.example.invalid/openai/v1/"
      BOOK_TELLER_MODEL_DEPLOYMENT = "a-deployment"
    }
    error_message = "The app must get exactly these seven settings, as plain values."
  }

  # 15. The owner's key reaches the app by the name of its secret, never as
  # a plain value. No other setting comes from a secret.
  assert {
    condition     = { for each in azurerm_container_app.app.template[0].container[0].env : each.name => each.secret_name if each.secret_name != null && each.secret_name != "" } == { BOOK_TELLER_OWNER_KEY = "owner-key" }
    error_message = "Exactly one setting must come from a secret: BOOK_TELLER_OWNER_KEY, from owner-key."
  }
  assert {
    condition     = alltrue([for each in azurerm_container_app.app.template[0].container[0].env : each.value == null || each.value == "" if each.name == "BOOK_TELLER_OWNER_KEY"])
    error_message = "The owner's key must not be a plain value of the app."
  }

  # 16. The vault: rights are given by roles, as everywhere in this file.
  assert {
    condition     = azurerm_key_vault.secrets.rbac_authorization_enabled == true
    error_message = "The vault must give rights by role assignments."
  }
  assert {
    condition     = azurerm_key_vault.secrets.sku_name == "standard"
    error_message = "The vault must be the standard kind, the cheaper one."
  }
  assert {
    condition     = azurerm_key_vault.secrets.location == "uksouth"
    error_message = "The vault must be in UK South (uksouth)."
  }
  assert {
    condition     = azurerm_key_vault.secrets.tenant_id == data.azurerm_client_config.current.tenant_id
    error_message = "The logins of the vault must come from the tenant of this subscription."
  }

  # 17. The owner's key: 48 random characters, kept in the vault.
  assert {
    condition     = random_password.owner_key.length == 48
    error_message = "The owner's key must have 48 characters."
  }
  assert {
    condition     = azurerm_key_vault_secret.owner_key.name == "owner-key"
    error_message = "The secret must have the name owner-key."
  }
  assert {
    condition     = azurerm_key_vault_secret.owner_key.key_vault_id == azurerm_key_vault.secrets.id
    error_message = "The owner's key must be in the vault of this file."
  }

  # 18. Two roles on the vault. The app may only read secrets. The person
  # who runs terraform may write them: Terraform puts the key in as that
  # person.
  assert {
    condition = alltrue([
      azurerm_role_assignment.app_reads_secrets.role_definition_name == "Key Vault Secrets User",
      azurerm_role_assignment.app_reads_secrets.scope == azurerm_key_vault.secrets.id,
      azurerm_role_assignment.app_reads_secrets.principal_id == azurerm_user_assigned_identity.app.principal_id,
    ])
    error_message = "The identity of the app must have the role Key Vault Secrets User, on the vault and on nothing more."
  }
  assert {
    condition = alltrue([
      azurerm_role_assignment.maintainer_writes_secrets.role_definition_name == "Key Vault Secrets Officer",
      azurerm_role_assignment.maintainer_writes_secrets.scope == azurerm_key_vault.secrets.id,
      azurerm_role_assignment.maintainer_writes_secrets.principal_id == data.azurerm_client_config.current.object_id,
    ])
    error_message = "The person who runs terraform must have the role Key Vault Secrets Officer, on the vault and on nothing more."
  }

  # 19. The app may call the model: one role, on the model resource only.
  assert {
    condition = alltrue([
      azurerm_role_assignment.app_calls_the_model.role_definition_name == "Cognitive Services OpenAI User",
      azurerm_role_assignment.app_calls_the_model.scope == var.model_resource_id,
      azurerm_role_assignment.app_calls_the_model.principal_id == azurerm_user_assigned_identity.app.principal_id,
    ])
    error_message = "The identity of the app must have the role Cognitive Services OpenAI User, on the model resource and on nothing more."
  }
}
