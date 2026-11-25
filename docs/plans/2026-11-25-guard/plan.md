# Task 6: the guard

**State:** planned on 2026-11-25. The maintainer said yes to the plan on the same day, with the five answers below. The code is built, and one real run is made: see "What was seen". A second agent has reviewed the change: see "What the review changed". The pull request is open and its run passes. The planted fault was left out (the maintainer). Still to come: the maintainer reads `guard.py` line by line, and the merge.

It is the sixth task of [milestone 1](../2026-11-14-milestone_1_the_whole_path_once/plan.md).

## The goal

The checker is a model, and a model can make things up. For every fault it must give a quote from the chapter as proof. Nothing has checked that quote so far: in [task 5](../2026-11-25-two_step_graph/plan.md) the maintainer checked one by hand, with a search.

The guard is plain code, with no model in it. It runs after the checker and looks at every flag (one fault that the checker reported). It answers one question: **is this flag proven?** The same input gives the same answer every time, and it costs nothing.

After this task the app still does not call the model for a visitor. The route that starts a run comes in task 9.

## The two checks, and where each one is

| Check | Its question | Who does it | Where |
|---|---|---|---|
| **The shape check** | Is the answer a list of flags, each with a number for the sentence, one of the six names for the kind, a number for the paragraph, a quote and a reason? | Pydantic: a Python library that checks data against a class. Our class is `Flag` | It is built already: `ask_model` in `model_call.py` runs it on every answer. An answer that fails it ends the run with the reason `wrong shape`. This task adds one test of it with the real class `Flags`, and changes no code there |
| **The check of each flag** | Do the numbers point at something that exists? Is the quote really in the chapter? | Plain code, written here | New: `guard.py` |

**Why two.** Pydantic can check what one field looks like by itself: "this is a whole number", "this is one of six names". It cannot know how many sentences this script has, or what this chapter says. That needs the script and the chapter beside the flag, so it is plain code.

## What the guard looks at, for each flag

1. **The sentence number.** It must be between 1 and the number of sentences of the script. 0 is right only for the kind `left_out`, where no sentence holds the fault.
2. **The quote.** It must be found in one paragraph of the chapter. Both texts are cleaned first, and then compared letter for letter: see question 2.

The guard does not trust the paragraph number of the checker. It looks first at the paragraph that the checker named, then at every other one, and keeps the number of the paragraph where the quote really is. The checker's own number stays beside it.

**The result** is one line for each flag, in the same order: the flag as the checker gave it, the paragraph where the quote was found (0 for none), and the list of problems. No problem means proven. The names of the problems: `no_such_sentence` and `quote_not_found`.

**The guard never changes a flag, never drops one and never raises an error.** A flag that is not proven stays in the list, with its problems as the mark (question 1). The checker's list stays in the state as it came.

## What is built

| File | What it holds |
|---|---|
| `backend/src/book_teller/guard.py` | New. The check of each flag, and the clean-up of a text before the comparison |
| `backend/src/book_teller/check_step.py` | The code that splits the chapter into paragraphs becomes a function of its own. The numbering and the guard both use it, so "P7" is the same paragraph for the checker and for the guard |
| `backend/src/book_teller/episode.py` | A third node, `guard`, after `check`: `START → write → check → guard → END`. A new key in the state, `checked`. The node has no retry rule: it asks nobody, so a second try would give the same result |
| `backend/src/book_teller/tell.py` | It prints the proven flags and the not proven ones apart, each with its problem |
| `backend/tests/test_guard.py`, and changes in `test_episode.py`, `test_check_step.py`, `test_tell.py` | The tests below |
| `README.md` | A section "The guard". The picture of the graph is printed again by the library; a test already compares the two |

No new library. Nothing in the cloud changes.

## Decided by the maintainer

On 2026-11-25. The agent had proposed A, B, A, A and yes. Questions 1, 2, 4 and 5 were answered as proposed. **Question 3 was answered with B:** both guards of the cost come in task 9, so this task holds only the guard on the checker's answer.

| # | Question | Options, and what each costs | Chosen |
|---|---|---|---|
| 1 | **What happens to a flag that is not proven?** | **A. It stays, with a mark.** The list holds it with its problem, and the page will show it apart from the proven ones. Costs: a reader sees faults that the checker may have made up; and task 11 must decide whether such a flag counts as "caught". · **B. It is dropped.** Costs: a true fault disappears without a word when the checker copied its quote a little wrong; and exit criterion 3 of the milestone says "marked", so that sentence must change. · **C. The checker is asked once more.** The graph gets an arrow with a condition (LangGraph's word: a conditional edge): after the guard, back to `check` when a flag is not proven. Costs: a second call of the checker in the bad case (in task 5 one call was about 6,600 tokens in and 8 seconds); the second answer can hold other flags, which can fail too, so A or B is still needed for what is left; a counter in the state must stop a loop; and more code in the file that is read line by line | **A.** It is what the milestone promises, and nothing is hidden |
| 2 | **How exact is "the quote is in the chapter"?** | **A. Letter for letter.** Costs: a true quote fails when the model changes something small. This chapter marks italics with underscores, in 10 of its 21 paragraphs, and a model may leave them out when it copies. A pasted text can also have a line break in the middle of a sentence. · **B. Clean both texts first, then letter for letter.** The clean-up: small letters, plain quote marks, no underscores, one space where there were several or a line break. It is what the [probe](../2026-11-13-probe_planted_faults/plan.md) did; all 12 of its quotes were found. Costs: a quote that differs only in capital letters passes; a quote with another kind of dash still fails. · **C. Nearly the same:** code gives two texts a score for how alike they are, and a quote passes above a line, such as 90%. Costs: a made-up quote that is close to a real sentence passes, and that is the case the guard exists for; nobody can say why the line is 90 and not 85; and "why did this one pass?" has no short answer | **B** |
| 3 | **The two other guards of the milestone: now or later?** They guard the cost, not the answer. **The limit on the pasted text:** a chapter that is too long is refused before any model is asked. **The daily money cap:** when the calls of one day have cost more than a fixed sum, no new run starts | **A. The limit now, the cap in task 9.** The limit is a few lines and needs nothing else: 5,000 words; the chapter of the probe has 3,190. The cap must add up what the day has cost so far, and nothing keeps that sum before the database of task 8. · **B. Both in task 9,** with the route that takes the pasted text. Costs: until then `tell.py` sends a text of any length to the model | **B** |
| 4 | **The wide reason `service error`: mend it in this task?** Found in the review of task 5: the model call gives this reason also to a request that the service does not accept, and the graph then tries such a request a second time, for nothing | **A. Not now.** It stays written down, as it is. Costs: the useless second try stays. · **B. Now:** a reason of its own in `model_call.py`. Costs: this pull request then changes the model call too, a second subject beside the guard, and one more file to read line by line | **A** |
| 5 | **May one real run be made?** `tell.py` with the chapter of the probe, to see the guard's lines on real flags | The two runs of task 5 each stayed far under 5 US cents | Yes |

**Taken by the agent, because they are small. Say so if one is wrong:**

- The quote is searched in every paragraph, not only in the one that the checker named. A wrong paragraph number alone is not a problem of the flag.
- A quote must lie inside one paragraph. One that starts in a paragraph and ends in the next is not found.
- An empty quote is not found.

## This pull request shows the whole loop

Two things are in this pull request and in no other of the milestone.

**1. Its page says how each changed file was checked,** with one of three labels: read line by line by the maintainer · reviewed by a second agent · tests only. `guard.py` is read line by line: the [merge rule](../../../CLAUDE.md) asks for that for the code that checks the model's answer.

**2. A fault planted on purpose, in public. Planned, and left out** (the maintainer, 2026-11-25). The steps below were not done. What this task has in their place: every new test of the guard was seen to fail before the guard was written. What it does not have: a proof that a test fails when the finished code is broken. The plan was:

A test is worth something only if it fails when the code is wrong. So, after the tests pass:

1. The maintainer breaks the guard by hand, in one commit, in two places: the quote check says "found" for every quote, and the class `Flag` takes any text as a kind.
2. The commit is pushed. The pipeline must fail, and its log names the tests that failed.
3. A second commit takes the first one back (`git revert`). The pipeline passes again.

Both commits stay in the history: a merge here is a merge commit, never a squash. If a planted fault makes no test fail, that is a finding: a test is missing, and it is written before the merge.

## Exit criteria

1. `uv run pytest` passes with no network, and the new tests were seen to fail first.
2. `ruff` and `mypy` pass, and a warning still fails the test run.
3. The maintainer saw one real run: every flag of the checker came out as proven or as not proven, with its problem.
4. ~~The history of the pull request holds one failed run of the pipeline, caused by the planted fault, and a passed run after the commit that takes it back.~~ Taken out with the planted fault.
5. The page of the pull request says how each changed file was checked.
6. The maintainer has read `guard.py` and the node `guard` line by line.
7. The picture of the graph in the README shows `write`, `check`, `guard`, as the library prints it.
8. The app starts without any setting of the model, and the pipeline builds the image and deploys as before.
9. No key, no address and no name of an Azure resource is in the repository.

## Test cases

Run by `pytest`, with no network.

In `backend/tests/test_guard.py`:

1. A quote that is in the chapter word for word: the flag is proven, and the result names the paragraph that holds it.
2. A quote that differs from the chapter only in capital letters, in the kind of quote marks, in underscores, or in spaces and line breaks: proven.
3. A quote with one word changed: not proven, `quote_not_found`.
4. An empty quote, or one of spaces only: `quote_not_found`.
5. A quote that is in another paragraph than the checker named: proven, with the real paragraph. The checker's number is kept beside it.
6. A quote that starts in one paragraph and ends in the next: `quote_not_found`.
7. A sentence number larger than the script, or below 0: `no_such_sentence`.
8. Sentence 0 with the kind `left_out`: no problem. Sentence 0 with another kind: `no_such_sentence`.
9. A flag with both problems names both.
10. No flags: an empty result, and no error.
11. The result has one line for each flag, in the checker's order, and each line holds the flag unchanged.

In `backend/tests/test_episode.py`:

12. One run still asks the model twice: the guard asks nobody.
13. The last state holds `checked`, with one line for each flag, and still holds `flags` as the checker gave them.
14. The guard gets the chapter of the run and the script of the writer: a quote of the fake checker that is in the fake chapter is proven.
15. A flag with a made-up quote does not end the run: it ends well, and the flag is marked.
16. The picture that the library prints shows `write`, then `check`, then `guard`. The picture in the README is the same: the test of task 5.

In `backend/tests/test_check_step.py`:

17. Through the fake model service of task 4: an answer whose kind is not one of the six names ends as `wrong shape`. So does an answer with no quote.
18. The function that splits the chapter gives the paragraphs that the numbering shows: the text of paragraph 3 is the text after `[P3]`.

In `backend/tests/test_tell.py`:

19. A run prints how many flags there are and how many of them are not proven; each not proven flag is printed with its problem.

Kept as they are: all other tests of tasks 1 to 5. The test of what `tell.py` prints for a flag changes with the new lines; it gets no weaker.

Seen once by the maintainer:

20. One real run of `tell.py` with the chapter of the probe.
21. ~~The planted fault: the failed run and the passed run of the pipeline.~~ Left out.

## The order of the work

1. A branch for this task. First commit: this plan.
2. The tests. They fail: `guard.py` does not exist.
3. `guard.py`, and the changes in `check_step.py`, `episode.py` and `tell.py`. The tests pass.
4. One real run; what was seen goes into this plan.
5. The review by a second agent, the fixes, the README.
6. The pull request. The planted fault was left out.
7. The maintainer reads `guard.py` line by line. The merge.

## What a check like this cannot catch

It is said here, and in the README, so that nobody reads "proven" as more than it is.

- **A real quote that proves nothing.** The guard knows that the words are in the chapter. It does not know whether they show that the script is wrong. A quote of one common word is "found".
- **A made-up quote that is built of pieces of real words.** The quote is compared by letters, not by words, so it may start or end in the middle of a word: "he is not" is found in "she is nothing". Found in the review, and left so by the maintainer: see "What the review changed".
- **A fault that the checker did not flag.** The guard sees only what the checker reports. Task 11 measures what the checker misses.
- **A wrong kind or a wrong reason.** Both are the model's words, and nothing checks them.
- **A true quote in other letters:** another kind of dash, a spelling that the model "mended", a quote that the model shortened with "..." in the middle, a letter with an accent that is stored in another way. It is marked as not found. This is the price of not passing a made-up quote.
- **A chapter of any length.** Nothing limits the pasted text yet, and nothing caps the cost of a day. Both come in task 9.

## What could go wrong

- **The guard and the checker count paragraphs differently.** Then every found paragraph number is off. One function splits the chapter for both, and test case 18 holds it.
- **The clean-up is too kind or too hard.** No number says yet how often a true quote fails. The real run shows a few cases; task 11 shows more.
- **A planted fault that no test notices.** See above: the missing test is written first.
- **The planted fault reaches `main`.** It cannot be merged while the pipeline fails, and the commit that takes it back comes before the merge. The last run before the merge must be the passed one.
- **The agent cannot reach Azure.** The maintainer makes the real run, and the agent reads the output.

## What was seen

**The real run** (2026-11-25), with the chapter of the probe:

| Step | Tokens in | Tokens out | Of them thinking | Seconds |
|---|---|---|---|---|
| `write` | 4,069 | 1,743 | 128 | 18.3 |
| `check` | 6,282 | 946 | 896 | 7.5 |

Both steps answered at the first try. The writer gave 100 sentences. **The checker flagged nothing,** so the guard had nothing to check.

- **What the run shows:** the graph runs with its third node and the real model, and a run with no flag ends well.
- **What it does not show:** the guard at work on a real flag. Exit criterion 3 is met only in an empty way: "every flag" was no flag. The maintainer chose to leave it so. The tests hold the guard, and task 11 runs it on a script with planted faults.

## What the review changed

A second agent reviewed the change in a fresh session. **It reviewed by reading only:** it ran no test, and it did not try small changes of the code to see which a test notices, as the reviews of tasks 4 and 5 did. The maintainer chose to leave that part out, and later the planted fault too. So nothing in this task broke the finished code to see whether a test fails; a later milestone does that with a tool (mutation testing). The maintainer decided on each finding.

- **The quote is compared by letters, not by words,** so a quote may start or end in the middle of a word. **Left so, and said** (the maintainer): in the code, in the README and above, under "What a check like this cannot catch". The other way, a match on whole words only, was the agent's proposal.
- **A flag with a real quote and a sentence number that does not exist** is printed by `tell.py` under "NOT PROVEN" with the checker's own paragraph number, though the guard knows the real one. **Left so** (the maintainer): the flag is marked as not proven, and that is what matters.
- **Tests added for what no test held:** a single curly quote mark against a plain apostrophe · a paragraph number of 0, below 0 and above the count · an empty chapter · an empty script. All passed at once: the code was right, and now a test holds it.
- **"The two steps" stood in five places** where there are three steps now. Corrected.
- **Three sentences promised too much:** that the clean-up never changes what the words say, that a close quote never passes, and that the guard "searches every paragraph" with no word on the one that it looks at first. Corrected.
- **Limits that were not said:** a quote shortened with "...", and letters stored in another way. Said above.
- **Not taken:** to drop the rule that the paragraph which the checker named is looked at first. Without it the guard could show another number than a checker that was right.

## How it is undone

Take `guard.py` and its tests out, take the node `guard` and the key `checked` out of `episode.py`, put the old lines of `tell.py` back, and print the picture of the README again. No library and nothing in the cloud changed.
