# Set up the project from zero

**This file owns: everything needed to make the project again from nothing, also what is made by hand.**
What each piece is for, and why it was chosen: the plans in `docs/plans/`.

**Last updated: 2026-11-27** — the model resource and the budget, which are made by hand; the vault with the owner's key; the file `terraform.tfvars`, which takes the place of every variable of the shell. Before that, 2026-11-26: the database server, and the sign-in name that Terraform needs for it.

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
  - a pull request is merged with a merge commit, never a squash: the merge rule in `CLAUDE.md`.

## 2. The budget and the model: made by hand

- **A budget on the subscription,** in the Azure portal under Cost Management: an amount for a month, and an email when it is reached. It stops nothing: it only sends a notice, and its numbers are up to a day late. The app has its own cap on the runs of a day.

The model resource is older than the Terraform file, and it is not in it.

- In the Azure portal, in Azure AI Foundry: a resource in UK South, and in it a deployment of the model `gpt-5-mini`.
- For a call from your own machine, your own login needs the role **Cognitive Services OpenAI User** on that resource. Being its owner is not enough.
- Three facts of it are needed below: its Azure id (`az cognitiveservices account list --query "[].id" --output tsv`), its address, which ends with `/openai/v1/`, and the name of the deployment.

## 3. The cloud: in files

In the folder `infra`, make a file `terraform.tfvars` with five lines: the id of your subscription (`az account show --query id --output tsv`), your own sign-in name (`az ad signed-in-user show --query userPrincipalName --output tsv`), and the three facts of the model. Terraform reads a file of this name by itself, so no variable of the shell is needed. Git does not see the file: it names your subscription and you.

```
subscription_id     = "..."
database_admin_name = "..."
model_resource_id   = "/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/..."
model_endpoint      = "https://.../openai/v1/"
model_deployment    = "..."
```

Then:

```
terraform init
terraform plan
terraform apply
```

- With your sign-in name, you become an administrator of the database. The name stays in `terraform.tfvars` and in the state file, not in git.
- `terraform plan` should list 18 things to add. The database server takes several minutes, and it is paid by the hour from then on. `terraform apply` asks for `yes`, so run it in a terminal where you can type.
- Terraform switches on the families of Azure services that the file uses.
- **The state file,** `infra/terraform.tfstate`, stays on this machine. `.gitignore` keeps it out of git: it can hold secrets. If it is lost, `terraform import` rebuilds it from what exists in Azure.
- The app starts with Microsoft's stand-in image. The first merge deploys ours.
- A second `terraform plan` must say "No changes".
- **If the apply stops with "forbidden" at the secret `owner-key`:** your new role on the vault is not at work yet. Wait a few minutes and run the apply again.
- **The owner's key** is made by Terraform and kept in the vault. To read it, with the name of the vault from the portal:

```
az keyvault secret show --vault-name VAULT --name owner-key --query value --output tsv
```

## 4. Azure DevOps: the pipeline, made by hand

- **A project,** private: Microsoft no longer offers public ones.
- **A pipeline from `azure-pipelines.yml`,** joined to the GitHub repository. Its run is the check that the ruleset of step 1 requires.
- **Pull requests from forks:** in the settings of the pipeline, "Limit building pull requests from forked GitHub repositories" on, with "Disable building pull requests from forked repositories".
- **The service connection, after step 3:** Project settings → Service connections → new → Azure Resource Manager.
  - Identity: App registration (automatic). Credential: workload identity federation. No secret is stored.
  - Scope: the subscription, and the resource group **`rg-book-teller`** only. Its role there is Contributor.
  - Name: **`azure-book-teller`**, the name that `azure-pipelines.yml` uses.
  - "Grant access permission to all pipelines": off. The first run that names it waits until it is permitted.
- **No check on the service connection.** A check "Branch control" was tried and removed: Azure DevOps runs it before a job starts, for every login that the job names, so it stopped every run on a pull request, tests included. So the conditions in `azure-pipelines.yml` are the only wall between a pull request and the cloud. A branch can change them; only collaborators can push a branch.

## 5. The first deploy

Merge a pull request. The run on `main` pushes the image, tells the app to run it, and waits until the live app runs the new image and answers `/health`. `terraform apply` prints the live address as `app_address`.
