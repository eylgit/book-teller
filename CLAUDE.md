# Book Teller: instructions for the coding agent

Book Teller turns a book into a podcast series, and checks every script against the book.
This file says how a change is made here. It stays short: before a line is added, one is removed.

## A task

1. **Plan.** Write a short plan as a file in `docs/plans/`: the goal, the exit criteria (what must be true when the work is done), and the list of test cases. The plan is committed before the code.
2. **Plan check.** Stop. Show the maintainer the plan in about ten lines, and the test cases as a list. Wait for "go".
3. **Test first.** Write a test that fails, and see it fail. Then write the code.
4. **Review.** A second agent, in a fresh session, reviews the change. Its findings are hints, not a verdict.
5. **Code-review check.** Stop. Show the maintainer the findings, and what you want to do with each. Wait for "go".
6. **Then the change goes in.**

A very small change, such as a spelling mistake, skips both stops. Say so in one line.

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
