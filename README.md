# Book Teller

Book Teller turns a book into a podcast series: the book told well by one voice, about 30 minutes an episode, in English or Cantonese.

Every script will be checked against the book, and for each fault the checker will show the line of the book that proves it.

**Status:** day 0. The working method came first. The only code so far is a probe, a small early test: can the model find faults that were planted in a script? See [its plan](docs/plans/2026-11-13-probe_planted_faults/plan.md).

The project is built with a coding agent. How a change is made: [CLAUDE.md](CLAUDE.md). What the agent may do: [.claude/settings.json](.claude/settings.json).

Licence: [MIT](LICENSE).
