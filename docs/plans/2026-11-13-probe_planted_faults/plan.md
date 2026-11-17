# Probe: can the model find planted faults?

**State:** done on 2026-11-13. The verdict is "go on".

## The result

One run on `gpt-5-mini` (version 2025-08-07). The report: `experiments/2026-11-13-probe_planted_faults/results/2026-11-13-163056.json`.

| What | Result |
|---|---|
| Faults caught | 10 of 12 |
| Faults of kinds 1 to 5 (a changed sentence) | 10 of 10, the blunt and the subtle ones |
| Faults of kind 6 (a point left out) | 0 of 2 |
| False alarms | 2. Both are fair: one sentence of the clean script says "nobody" where the author is less absolute, and the script does leave out the point of the other flag |
| Quotes found word for word in the chapter | 12 of 12 |
| The fixed shape of the answer | Held |
| Tokens | 5,343 in and 5,913 out, of which 4,992 are the model's thinking |
| Time | 39 seconds |

What it means:

- **The model can find faults in a changed sentence.** It also proved each one with a real quote.
- **It did not find the two points that were left out.** It did flag another point that the script leaves out, so it looks for this kind, but it does not find every case. With the limit named in "The review" below, kind 6 is the open question for the real checker.
- **It is one run of 12 faults.** It says "can it find faults at all": yes. It does not say how many it finds on average.

A probe is a small early test with a yes-or-no answer. It runs before anything is built on the answer.

## The goal

Book Teller will check every script against the book. The checker is one model call. Before the checker is built, this probe asks one question: **can the model find faults at all?**

A planted fault is a mistake put into a script on purpose. The probe plants 12 of them, asks the model to check the script against the chapter, and counts how many it finds.

## What is built

Everything lives in `experiments/2026-11-13-probe_planted_faults/`. It was moved there from `probes/planted_faults/` on 2026-11-17, with no change to the code: an experiment's folder has the name of its plan folder.

| File | What it holds |
|---|---|
| `chapter.txt` | William James, "Talks to Teachers on Psychology" (1899), chapter 8, "The Laws of Habit". About 3,200 words, in the public domain. The title, the lines that only separate sections, and one footnote are removed |
| `script.txt` | A telling of the chapter of about 900 words, one sentence on a line. It has no faults |
| `faults.json` | The 12 planted faults: the answer key |
| `probe.py` | Plants the faults, calls the model once, scores the answer, prints a report |
| `test_probe.py` | The tests. They need no network and no key |
| `results/` | The report of each real run, with the model's full answer |

**The 12 faults.** Two for each of the six kinds that the checker will look for: one blunt (easy to see, such as a changed number) and one subtle (a small change of a word).

1. a wrong fact;
2. a concept explained wrongly;
3. an example that does not match the idea;
4. a conclusion the author did not draw;
5. a word that is too strong or too weak, such as "may" turned into "will";
6. an important point of the author left out.

Each fault names the sentence of the script that it changes, the new sentence, and the line of the chapter that proves it. A fault of kind 6 removes a sentence.

**Who writes what.** The coding agent writes the script and drafts the faults. It runs on a different model from the one that is tested: a model finds its own faults too easily. The maintainer reads every fault and drops any that is not truly a fault.

**How a fault is scored, with no judgement.** The request gives every sentence of the script a number and every paragraph of the chapter a number. The model must answer in a fixed shape (structured output): for each flag, the number of the sentence, the kind, the number of the paragraph, and a quote from the chapter.

- A planted fault is **caught** when a flag names its sentence.
- A fault of kind 6 has no sentence left. It is caught when a flag of kind 6 names its paragraph.
- A flag that catches nothing is a **false alarm**. The report prints each one, because a false alarm may be a real fault that nobody planted.
- For every flag, the code checks that the quote is found word for word in the chapter.

**Tools.** Only what Python brings with it: `urllib` for the request, `unittest` for the tests. No dependency.

**The key.** `probe.py` asks the Azure CLI for the key each time it runs, and keeps it in memory only. No key is saved, printed or written to a file. The names of the Azure resource and of the model deployment are arguments on the command line.

## Exit criteria

1. `python3 -m unittest discover -s experiments/2026-11-13-probe_planted_faults` passes, with no network and no key.
2. One real run on the deployed model prints, for each of the 12 faults, caught or missed; the false alarms; the tokens used; the seconds. Its report is in `results/`.
3. The report states one of three verdicts:
   - **Too easy:** 11 or 12 caught. Half of the faults are replaced with harder ones, and the probe runs again.
   - **Stop:** fewer than 5 of the 6 blunt faults caught. The maintainer chooses: another model, or another plan.
   - **Go on:** anything else.
4. No key is in the repository or in any report.

## Test cases

1. The answer key has 12 faults: two of each kind, one blunt and one subtle.
2. The sentence that a fault changes is in the script exactly once.
3. After planting, the script differs from the clean one in exactly the 12 planted places.
4. The proof line of every fault is found word for word in the chapter.
5. A flag on the sentence of a planted fault counts as caught.
6. Two flags on one fault count as one.
7. A flag on a sentence with no fault counts as a false alarm.
8. A fault of kind 6 is caught only by a flag of kind 6 on the right paragraph.
9. A flag whose quote is not in the chapter is marked "quote not found".
10. The verdict: 12 caught and 11 caught give "too easy"; 4 blunt caught gives "stop"; 8 caught with 5 blunt gives "go on".
11. An answer from the model that does not have the fixed shape gives one clear error line.
12. The request holds the numbered script, the numbered chapter and the fixed shape, and no fault from the answer key.
13. A report made with a fake key does not contain that key.

In the tests a fake function stands in for the model call.

## What could go wrong

- **One run is one sample.** A model does not give the same answer twice. The probe says "can it find faults at all", not "how many does it find".
- **The faults may flatter.** Faults drafted by a model are easier to find than real ones. The verdict "too easy" exists for this.
- **The model may not hold the fixed shape.** Then test case 11 shows it, and that is a finding too.
- **Cost.** One request of about 8,000 tokens: under 5 US cents at the list price.

## The review, and what was left as it is

A second agent reviewed the change and reported 14 findings. Three were fixed, each with a test:

- The script numbered its maxims, so the maxim that fault F11 removes could be found by counting. The numbering is gone.
- A flag for a point that is left out could be given to the fault in the sentence beside it. Such a flag is now matched by its paragraph first.
- No test would have failed if the program had sent the clean script to the model.

The rest are known limits. The probe only has to say "good enough to go on, yes or no", so they are written down here and not fixed:

- **A point that is left out cannot be marked well by code.** The script is short, so it leaves out many points, and a flag for any of them counts as a false alarm. Any flag of kind 6 on the right paragraph counts as a catch. The report prints the model's reason under each catch: the two catches of kind 6 are read by the maintainer.
- **Some planted sentences do not fit the sentence beside them** (F03, F05, F07, F08). A model may find these without the chapter.
- **The blunt and the subtle fault of kind 5 are about equally easy.**
- **When the model's answer has the wrong shape,** the answer is not saved.
- **A quote that the model copies with another kind of dash** is marked "not found".
- **A few sentences of the clean script are a little stronger than the chapter,** such as "leaves its scar" for "its never-so-little scar".

## How it is undone

The probe is one folder. Deleting the folder removes all of it. Nothing is made in the cloud.
