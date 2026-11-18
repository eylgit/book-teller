# Book Teller: instructions for the coding agent

Book Teller turns a book into a podcast series, and checks every script against the book.
This file says how a change is made here. It stays short: before a line is added, one is removed.

## A task

1. **Plan.** Each task gets its own folder, `docs/plans/YYYY-MM-DD-short_title/`. It holds `plan.md` and any file that supports the plan. The plan is short: the goal, the exit criteria (what must be true when the work is done), and the list of test cases. It is the first commit on the branch of the task, before the code.
2. **Plan check.** Stop. Show the maintainer the plan in about ten lines, and the test cases as a list. Wait for "go".
3. **Test first.** Write a test that fails, and see it fail. Then write the code.
4. **Review.** A second agent, in a fresh session, reviews the change. Its findings are hints, not a verdict.
5. **Code-review check.** Stop. Show the maintainer the findings, and what you want to do with each. Wait for "go".
6. **Then the change goes in, by a pull request.** The maintainer commits and merges; the agent never does. It proposes the commit message.

A very small change, such as a spelling mistake, skips both stops, but not the pull request. Say so in one line.

## The merge rule

- **Every change reaches `main` by a pull request,** and the pipeline must pass. GitHub refuses anything else.
- **A change to secrets, or to the code that checks the model's answer,** is read line by line by the maintainer before the merge.
- **A merge commit, never a squash.** The history keeps each step.

## Four questions, on every task

1. **Can a test say no?** A script that can fail, not an AI's opinion.
2. **Did the maintainer see it run?** "Done" is only a claim until the real thing ran. Show the real output.
3. **Can the maintainer explain it without looking at the screen?** If not, make it simpler.
4. **Can it be undone?**

## Ask first

- A new dependency.
- A change that makes a test weaker, skips it or deletes it.
- Anything that cannot be undone, costs money or touches a secret.

## Never

- A key, a password or a token in this repository.
- A book that is under copyright.

## Rules come from real mistakes

A rule or a check is added only after a real mistake, and the commit names the mistake.
