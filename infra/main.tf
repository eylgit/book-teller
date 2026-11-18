# The cloud of Book Teller, in one file.
#
# Terraform reads this file and makes the cloud match it:
#   terraform plan   lists what it would add, change or delete
#   terraform apply  makes those changes
# Its record of what it made, the state file, stays on the maintainer's
# machine and never goes into git: see .gitignore.

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
}
