# Set up the project from zero

**This file owns: everything needed to make the project again from nothing, also what is made by hand.**
What each piece is for, and why it was chosen: the plans in `docs/plans/`.

**Last updated: 2026-11-20** — written from the plans of tasks 2 and 3.

---

Most of the project is in files. A few settings exist only in the web pages of GitHub, Azure and Azure DevOps. They are listed here, in the order in which they are made, so nothing is forgotten.

## What you need

- An Azure subscription, with the role **Owner** on it: Terraform makes a role assignment, and only an Owner (or a User Access Administrator) may.
- The Azure CLI, logged in: `az login`.
- Terraform 1.17.2. Docker and `uv` for the app: see the README.
- An organisation in Azure DevOps, with its billing joined to the subscription.

## 1. GitHub: the repository, made by hand

- **Secret scanning and push protection:** on. GitHub refuses a push that holds a key.
- **Pull requests:** "Collaborators only". Issues and the wiki: off.
- **A ruleset for `main`:**
  - a change needs a pull request;
  - the run of the pipeline must have passed, on a branch that holds the newest `main`;
  - no push by force, and the branch cannot be deleted;
  - nobody may pass the rules, also not the owner;
  - merges by merge commit only.

## 2. The cloud: in files

In the folder `infra`:

```
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
terraform init
terraform plan
terraform apply
```

- `terraform plan` should list 7 things to add. `terraform apply` asks for `yes`, so run it in a terminal where you can type.
- Terraform switches on the families of Azure services that the file uses.
- **The state file,** `infra/terraform.tfstate`, stays on this machine. `.gitignore` keeps it out of git: it can hold secrets. If it is lost, `terraform import` rebuilds it from what exists in Azure.
- The app starts with Microsoft's stand-in image. The first merge deploys ours.
- A second `terraform plan` must say "No changes".

## 3. Azure DevOps: the pipeline, made by hand

- **A project,** private: Microsoft no longer offers public ones.
- **A pipeline from `azure-pipelines.yml`,** joined to the GitHub repository. Its run is the check that the ruleset of step 1 requires.
- **Pull requests from forks:** in the settings of the pipeline, "Limit building pull requests from forked GitHub repositories" on, with "Disable building pull requests from forked repositories".
- **The service connection, after step 2:** Project settings → Service connections → new → Azure Resource Manager.
  - Identity: App registration (automatic). Credential: workload identity federation. No secret is stored.
  - Scope: the subscription, and the resource group **`rg-book-teller`** only. Its role there is Contributor.
  - Name: **`azure-book-teller`**, the name that `azure-pipelines.yml` uses.
  - "Grant access permission to all pipelines": off. The first run that names it waits until it is permitted.
- **Branch control on the service connection:** on the service connection, "Approvals and checks" → add "Branch control" → allowed branches `refs/heads/main`. A run on a pull request uses the pipeline file of its own branch, and a branch can delete the conditions in that file. This check is kept in Azure DevOps, where no branch can change it.

## 4. The first deploy

Merge a pull request. The run on `main` pushes the image, tells the app to run it, and waits until the live app runs the new image and answers `/health`. `terraform apply` prints the live address as `app_address`.
