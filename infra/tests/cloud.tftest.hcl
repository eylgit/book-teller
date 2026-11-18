# Tests of the cloud file, main.tf. Run them in the folder infra:
#
#     terraform test
#
# The mock provider is a stand-in for Azure: it takes the file and gives
# made-up answers, such as a made-up id for each thing. So these tests need
# no login, make nothing, and cost nothing. They check what the file asks
# for, not what Azure does with it.

mock_provider "azurerm" {}

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

  # 6. The app holds no secret.
  assert {
    condition     = length(azurerm_container_app.app.secret) == 0
    error_message = "The app must hold no secret."
  }

  # 7. Every thing is in UK South, the region of the model.
  assert {
    condition = alltrue([
      azurerm_resource_group.product.location == "uksouth",
      azurerm_container_registry.images.location == "uksouth",
      azurerm_log_analytics_workspace.logs.location == "uksouth",
      azurerm_user_assigned_identity.app.location == "uksouth",
      azurerm_container_app_environment.apps.location == "uksouth",
    ])
    error_message = "Every thing must be in UK South (uksouth)."
  }

  # 8. The logs have a daily cap, so they cannot grow into a bill.
  assert {
    condition     = azurerm_log_analytics_workspace.logs.daily_quota_gb == 0.1
    error_message = "The log workspace must stop taking logs after 0.1 GB a day."
  }
}
