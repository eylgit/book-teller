# Task 3: the cloud as a Terraform file, and deploy on merge

**State:** planned on 2026-11-18. The maintainer said yes to the plan on the same day, with the recommended answer to each of the five questions below. Done on 2026-11-20: the cloud is made, and the merge of pull request 3 was the first deploy. What was seen, and what the review changed, are at the end.

It is the third task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

The empty page of [task 1](../2026-11-16-app_skeleton/plan.md) is live on Azure. The cloud that runs it is written as one Terraform file, so it can be made again from this repository. From this task on, a merge to `main` deploys: the pipeline of [task 2](../2026-11-17-pipeline/plan.md) sends the image that it tested to the cloud, and nobody deploys by hand. The app gets its own login to Azure, a managed identity, and no password exists for it.

## What is built

**Terraform** is a tool that reads a description of the cloud and makes the cloud match it. Three words:

- **plan:** Terraform compares the file with the cloud and lists what it would add, change or delete. Nothing is changed yet.
- **apply:** Terraform makes the changes of the plan.
- **state file:** Terraform's own record of what it made, and of the address of each thing in Azure. It can hold secrets, so it never goes into this repository: `.gitignore` already leaves it out.

| File or setting | What it holds |
|---|---|
| `infra/main.tf` | The cloud, in one file. The list is below |
| `infra/.terraform.lock.hcl` | The lockfile of Terraform: the exact version of the Azure provider (the plug-in that talks to Azure), with its checksums. Like `backend/uv.lock` |
| `infra/tests/cloud.tftest.hcl` | Tests of the file, run by `terraform test`. They use a mock provider (a stand-in for Azure that gives made-up answers), so they need no login and make nothing |
| `azure-pipelines.yml` | Five new steps on every pull request: install Terraform, the format check, install the provider from the lockfile, the validation and the tests of the Terraform file. Three new steps on `main` after a merge only: push the image, deploy it, ask the live app if it answers |
| `README.md` | How the cloud is made, and how a merge deploys |
| A service connection in Azure DevOps | The pipeline's login to Azure. Made by hand, once |

**What `infra/main.tf` makes,** all in UK South, the region of the model from day 0:

| Thing | What it is | The settings that matter |
|---|---|---|
| A resource group | A folder in Azure that holds the rest. Delete it, and all of this is gone | One for the product, apart from the one of day 0 |
| A container registry | Azure Container Registry: the private store for images | The smallest size (Basic). **The admin user is off,** so the registry has no password |
| A log workspace | Log Analytics: where the cloud keeps what the app writes, also when it fails to start | A daily cap of 0.1 GB, so at most about 3 GB a month |
| A managed identity for the app | A login that Azure gives the app. No key exists, so no key can leak | A user-assigned identity: it is made before the app, so its rights exist before the app's first start |
| A role assignment | One line that says "this identity may use that thing" | The app's identity may pull images from the registry (the role `AcrPull`), and nothing else |
| A Container Apps environment | The space where Azure runs the app, with its network and its logs | Consumption only, no private network: a private network starts a monthly fee |
| The container app | Azure runs the image and gives it a public address | HTTPS only, on the app's port 8000 · 0.25 CPU and 0.5 GB of memory · **zero copies when nobody visits, at most one** |

**Who runs Terraform.** The maintainer, from their own machine, with their own login to Azure. The pipeline does not run Terraform in this milestone; it only checks the file. So the state file lives on the maintainer's machine for now (question 1 below).

**Who changes the image.** The pipeline, after each merge. So Terraform is told to leave the image of the app alone (`ignore_changes`); otherwise every `terraform plan` would want to put the old image back. On the very first apply no image of ours exists yet, so the app starts with Microsoft's small "quickstart" image as a stand-in. The first merge replaces it.

**The steps of the pipeline,** in this order. Steps 1 to 8 run on every pull request and on `main`; steps 9 to 11 run on `main` after a merge only.

1. to 5. As in task 2: install `uv`, install from the lockfile, the tests, the three checks, the smoke test.
6. Install Terraform 1.17.2, the version on the maintainer's machine, and check its checksum. The build machine has no Terraform of its own.
7. `terraform fmt -check` and `terraform validate`: is the file in the standard layout, and does it make sense to the provider?
8. `terraform test`: the tests of the file.
9. Push the image that the smoke test checked to the registry, named by the id of the merge commit. Not `latest`: so each running app can be traced to one commit.
10. Tell the container app to run that image. Azure starts a new revision (a numbered version of the app).
11. Ask the live address `/health`, for up to three minutes: a copy must first start from zero. The run fails if the answer is not `{"status":"ok"}`.

**The pipeline's login.** A service connection with workload identity federation: for each run, Azure DevOps signs a short-lived token, and Azure trusts it. No secret is stored in the pipeline or in this repository. Its rights reach only the resource group above (question 2 below).

## Decided by the maintainer

| # | Question | Options | Chosen |
|---|---|---|---|
| 1 | Where does the state file live? | **A.** On the maintainer's machine, ignored by git. Free, no setup. If the machine is lost, the state is rebuilt with `terraform import`. Enough while one person runs Terraform from one machine · **B.** In Azure Blob Storage, locked while a run uses it. Pennies a month. One more storage account, made by hand before Terraform, with its own permission traps. It is needed when the pipeline runs Terraform | **A.** It moves to B in the milestone where the pipeline runs Terraform: one `terraform init -migrate-state` |
| 2 | How does the pipeline log in to Azure? | **A.** Azure DevOps makes the service connection by itself, with workload identity federation, as Contributor on the resource group only. A few clicks · **B.** The pipeline's identity is made in Terraform too, with two narrow roles: push to the registry, update the app. Least privilege, and in code. Two rounds between Azure DevOps and Terraform, and more permission traps · **C.** A login with a secret. Not offered: it is a key | **A.** B belongs to the milestone on cloud permissions |
| 3 | The cost starts | The registry, Basic: about £3.81 a month (an older price, not read again). The app: about £0 when asleep, inside the free monthly amount of Container Apps. The logs: free up to 5 GB a month, and capped at about 3 GB | Yes |
| 4 | Versions | Terraform 1.17.2, the newest, already on the maintainer's machine · the Azure provider `hashicorp/azurerm` 5.13.0, one below the newest (5.14.0 came out on 2026-11-13). It is a new dependency | Yes to both |
| 5 | The finder of images in `backend/tests/test_build_files.py` does not know the names of build stages. Left from task 2 for this task | **A.** Teach it now. Nothing in this task needs it: the Dockerfile keeps one stage · **B.** Leave it for the task that gives the Dockerfile a second stage | **B** |

## New tools and dependencies

- **Terraform 1.17.2,** on the maintainer's machine (there since day 0) and on the build machine (installed by the pipeline).
- **The Azure provider for Terraform, `hashicorp/azurerm`, 5.13.0.** `terraform init`, run by the maintainer, downloads it and writes the lockfile.
- No new library in the Python project.

## Exit criteria

1. `infra/main.tf` makes the seven things of the table above, with the settings named there.
2. Before the first apply, `terraform plan` shows only additions. After `terraform apply`, a second `terraform plan` says "No changes".
3. `terraform test` passes with no login to Azure. It was seen to fail once: with the lowest number of copies set to 1, it must say no.
4. Every pull request runs steps 6 to 8. The history of this pull request holds a failed run: the tests of the file are pushed before the file.
5. A run on a pull request pushes nothing and deploys nothing: steps 9 to 11 show as skipped.
6. A run on `main` after a merge pushes the tested image, named by the merge commit, and the live app runs it. Step 11 passes.
7. The live address shows the Book Teller page.
8. No password exists for the image: the registry has no admin user, the app holds no secret, and it pulls with its managed identity. A `docker pull` of the image without a login is refused.
9. The pipeline holds no secret. Its rights reach only the resource group.
10. After the first deploy, `terraform plan` still says "No changes".
11. No state file is in git. `git status` on the maintainer's machine does not show it.
12. The README says how the cloud is made and how a merge deploys.

## Test cases

In `infra/tests/cloud.tftest.hcl`, run by `terraform test`, with the mock provider:

1. The app has at least 0 and at most 1 copy.
2. The app takes requests from the internet, on port 8000, over HTTPS only.
3. The registry has no admin user.
4. The app runs as the user-assigned identity, and pulls from the registry as that identity.
5. A role assignment gives that identity the role `AcrPull`, on the registry. Not tested: that the file holds no other role assignment. `terraform test` finds a thing by its name and cannot count the things of one kind.
6. The app holds no secret.
7. Every thing is in UK South.
8. The log workspace has a daily cap.

In `azure-pipelines.yml`:

9. `terraform fmt -check` and `terraform validate` pass.
10. After a deploy, the live `/health` answers `{"status":"ok"}` within three minutes.

Seen once by the maintainer:

11. On the page of the pull request, steps 9 to 11 are skipped.
12. `terraform plan` says "No changes" after the first apply, and again after the first deploy.
13. After the merge, the live address shows the Book Teller page in place of the stand-in.
14. A `docker pull` of the image without a login is refused.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The tests of the file, and steps 6 to 8 in the pipeline. The maintainer runs `terraform init`: it downloads the provider and writes the lockfile. The tests fail. Push, and open the pull request: the run fails at the tests of the file.
3. `infra/main.tf`. The tests pass.
4. The maintainer runs `terraform plan`, reads it, and runs `terraform apply`. The stand-in page is live. A second plan: "No changes".
5. The maintainer makes the service connection in Azure DevOps, for the new resource group.
6. Steps 9 to 11 in the pipeline. The run on the pull request skips them.
7. The review by a second agent, the fixes, the README.
8. The merge. The pipeline deploys, and the Book Teller page is live. A third plan: "No changes".

## What could go wrong

- **A permission.** The maintainer's login must be allowed to make role assignments (the role Owner on the subscription). The app's first start fails if `AcrPull` is not in place yet; a user-assigned identity is made first to avoid this.
- **The stand-in listens on another port.** Microsoft's quickstart image answers on port 80, and the app is set to 8000. Not verified: whether Azure finishes making the app while the stand-in cannot answer on 8000. If it does not, the first apply sets port 80, and the pipeline's first deploy sets 8000.
- **A first visit is slow.** With zero copies, the first request waits while a copy starts. Step 11 waits up to three minutes for this reason.
- **Two kinds of processor.** The maintainer's machine is ARM; Azure runs the image on x86. Only the build machine, which is x86, pushes images, so the right form reaches Azure.
- **Provider version 5.** The agent knows version 4 of the provider best. `terraform validate` reads the real provider, so a wrong name fails in step 7, before anything is made.
- **A Microsoft service is switched off for the subscription.** Azure must switch each family of services on before its first use. The provider asks for the common ones by itself; one may still be missing.
- **A pull request must never reach the cloud.** Steps 9 to 11 run only for `main`, and only after a merge. But a run on a pull request uses the pipeline file of its own branch, and a branch can delete those conditions. So the real wall is kept in Azure DevOps, on the service connection: a check "Branch control" lets only runs from `main` use it. Also, pull requests come only from collaborators, and Azure Pipelines builds none from a fork, as task 2 set.
- **If Terraform ever makes the app again,** the stand-in comes back until the next merge. `ignore_changes` keeps Terraform away from the image of the app that exists; but a change to a setting that cannot change on a running app, such as its name or its environment, makes Terraform delete the app and make a new one from this file. A plan says so with `-/+` and "must be replaced".
- **Images pile up in the registry,** one for each merge. Basic holds 10 GB (an older figure, not read again), and its plan has no rule that deletes old images. A later task adds a clean-up.
- **The Azure CLI may lack its commands for Container Apps one day.** Today they are built in. The deploy step then fails, rather than install a version that nobody chose.

## How it is undone

`terraform destroy`, or delete the resource group: every thing of this task is in it. Then delete the service connection in Azure DevOps, and take the new files and lines back. The cost stops with the registry.

## What was seen

- **The first run of the pull request failed,** with "Reference to undeclared resource": the tests of the file were pushed before the file. The install of Terraform, with its checksum, and `terraform init` from the lockfile worked on the build machine.
- **The first `terraform test` against the new file failed,** for a reason in the test, not in the file: the mock provider made up ids such as `hoq2izpc`, and the provider refuses an id that is not in the shape of an Azure address. The mock now gives ids in the real shape; no assertion changed. Then the tests passed, and they said no once, with the lowest number of copies set to 1.
- **The first `terraform apply` stopped after 4 of the 7 things.** The subscription had not switched on the family of services of the registry, `Microsoft.ContainerRegistry`. Terraform did not undo the 4; the state file recorded them. The provider block now switches the family on, and the second apply made the other 3.
- **The stand-in on port 80 did not stop the apply.** The app was made with the quickstart image, while it sends requests to port 8000.
- **A plan after the apply was not "No changes".** Azure gives every new Container Apps environment a workload profile named "Consumption", and puts the app on it. The file did not name it, so every plan wanted to remove it, and Azure put it back. The file now names it, and a plan says "No changes".
- **The state file is on the maintainer's machine,** and `git status` does not show it.
- **The plan after the review fixes said "No changes"** again: the mode of the registry was already the legacy one, and switching on families of services changes no thing.
- **The first run that names the service connection** stopped once, for the maintainer to permit the pipeline to use it. Then the run on the pull request passed, with the deploy steps skipped.
- **The first deploy:** the merge of pull request 3 ran all 15 steps in 2 minutes 4 seconds. The live check passed in 40 seconds: the version taking the visits ran the new image, pulled from the private registry with the app's identity, and answered `{"status":"ok"}`. The Book Teller page is live.
- **The image in the registry** is named by the merge commit, and its platform is `linux/amd64`: built on the build machine, not on the maintainer's ARM machine.
- **A `docker pull` of that image without a login** was refused: "authentication required".
- **After the deploy, `terraform plan` said "No changes":** Terraform leaves the image to the pipeline.
- **The Azure CLI of the build machine (2.93.0) has the commands for Container Apps built in;** no extension was installed. The line that allowed an unpinned install is removed.
- **Not as expected:** the portal lists only the revision of our image, `--0000001`, and no inactive revision of the stand-in. Not verified why.

## What the review changed

A second agent reviewed the change in a fresh session, with 12 findings. The maintainer decided on each.

- **The live check could pass while the new image was not running.** If a new image fails to start, Azure keeps the old version taking the visits, and the old one also answers "ok". The check now also requires that the version taking the visits runs the new image.
- **The wait was up to nine minutes, not three:** 36 tries of up to 15 seconds each. It is now a clock of three minutes.
- **The conditions in the pipeline file were the only wall** between a pull request and the cloud, and a branch can change them. A check "Branch control" on the service connection now lets only runs from `main` use it.
- **The mode of the registry was left to Azure's default.** It is now written: `LegacyRegistryPermissions`, the mode in which `AcrPull` works.
- **Only one family of Azure services was switched on by the file.** All four that it uses are now.
- **How to set up the project from zero** was spread over the plans. It is now one guide: [docs/guides/setup-from-zero.md](../../guides/setup-from-zero.md).
- **Small fixes:** a simpler lookup of the registry; the text of test case 5 now says what is not tested; a comment says why test 7 leaves out the app; "What could go wrong" names a new app made by Terraform, the images that pile up, and the one tool that is not pinned.
- **Not taken:** a test that counts the role assignments in the file, since no such mistake has happened; one step in place of the deploy and the live check, since two names read better in the log.
