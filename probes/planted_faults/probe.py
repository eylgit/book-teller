"""Probe: can the model find planted faults?

The probe plants 12 faults in a script, asks the model to check the script
against the chapter, and counts how many of the 12 the model finds.

Run from the top folder of the repository:

    python3 probes/planted_faults/probe.py --resource NAME --resource-group NAME --deployment NAME

It uses only what Python brings with it. It asks the Azure CLI for the key
each time, and never saves or prints the key.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

KINDS = {
    1: "a wrong fact",
    2: "a concept explained wrongly",
    3: "an example that does not match the idea",
    4: "a conclusion the author did not draw",
    5: "a word that is too strong or too weak",
    6: "an important point of the author left out",
}

INSTRUCTIONS = """You check the script of a podcast episode against the chapter of the book that it tells.
The script must say what the author said. It is a short telling, so it may leave out details.

Find every fault in the script. There are six kinds of fault:
1. a wrong fact;
2. a concept explained wrongly;
3. an example that does not match the idea;
4. a conclusion the author did not draw;
5. a word that is too strong or too weak, such as "may" turned into "will";
6. an important point of the author left out.

Every sentence of the script starts with its number, such as [S7].
Every paragraph of the chapter starts with its number, such as [P3].

For each fault, give:
- sentence: the number of the sentence of the script. Give 0 for a fault of kind 6.
- kind: the number of the kind, 1 to 6.
- paragraph: the number of the paragraph of the chapter that proves the fault.
- quote: the words of that paragraph that prove the fault, copied word for word.
- reason: one short sentence that says what is wrong.

Flag only real faults. If the script has no fault, give an empty list."""

ANSWER_SHAPE = {
    "type": "object",
    "properties": {
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "integer"},
                    "kind": {"type": "integer", "enum": [1, 2, 3, 4, 5, 6]},
                    "paragraph": {"type": "integer"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["sentence", "kind", "paragraph", "quote", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["flags"],
    "additionalProperties": False,
}

FLAG_FIELDS = {"sentence": int, "kind": int, "paragraph": int, "quote": str, "reason": str}


class ProbeError(Exception):
    """Something went wrong that the user must read. It is printed as one line."""


# ---------------------------------------------------------------- the files


def read_chapter(path):
    """The chapter as a list of paragraphs. A blank line ends a paragraph."""
    with open(path, encoding="utf-8") as handle:
        blocks = handle.read().split("\n\n")
    return [" ".join(block.split()) for block in blocks if block.strip()]


def read_script(path):
    """The script as a list of sentences. One sentence is on one line."""
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def read_faults(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------- the planting


def plant(script, faults):
    """Put the faults into the script.

    Returns the new list of sentences, and for each fault the number of its
    sentence in the new list. A fault that removes a sentence gets number 0.
    """
    by_sentence = dict((fault["original"], fault) for fault in faults)
    planted = []
    placed = {}
    for sentence in script:
        fault = by_sentence.get(sentence)
        if fault is None:
            planted.append(sentence)
        elif fault["planted"] is None:
            placed[fault["id"]] = 0
        else:
            planted.append(fault["planted"])
            placed[fault["id"]] = len(planted)
    missing = [fault["id"] for fault in faults if fault["id"] not in placed]
    if missing:
        raise ProbeError("These faults name a sentence that is not in the script: " + ", ".join(missing))
    return planted, placed


# -------------------------------------------------------------- the scoring


def normalise(text):
    """Make two texts easy to compare: small letters, plain quote marks,
    no underscores (the chapter marks italics with them), single spaces."""
    for curly, plain in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(curly, plain)
    return " ".join(text.replace("_", "").lower().split())


def find_paragraph(chapter, quote):
    """The number of the first paragraph that holds the quote word for word.
    Returns 0 when no paragraph holds it."""
    wanted = normalise(quote)
    if not wanted:
        return 0
    for number, paragraph in enumerate(chapter, start=1):
        if wanted in normalise(paragraph):
            return number
    return 0


def score(faults, placed, chapter, planted, flags):
    """Compare the model's flags with the answer key. No judgement is used.

    A fault that changed a sentence is caught when a flag names that sentence.
    A fault that removed a sentence is caught when a flag of kind 6 names the
    paragraph of the chapter that holds the point that was left out.
    A flag that catches nothing is a false alarm.
    """
    by_sentence = {}
    by_paragraph = {}
    for fault in faults:
        if placed[fault["id"]] > 0:
            by_sentence[placed[fault["id"]]] = fault["id"]
        else:
            by_paragraph[find_paragraph(chapter, fault["proof"])] = fault["id"]

    caught = set()
    checked = []
    for flag in flags:
        # A flag of kind 6 is matched by its paragraph first. The model may name
        # the sentence beside the gap, and that sentence can hold another fault.
        catches = by_paragraph.get(flag["paragraph"]) if flag["kind"] == 6 else None
        if catches is None:
            catches = by_sentence.get(flag["sentence"])
        if catches is not None:
            caught.add(catches)
        entry = dict(flag)
        entry["catches"] = catches
        entry["quote_found"] = find_paragraph(chapter, flag["quote"]) > 0
        entry["sentence_text"] = (
            planted[flag["sentence"] - 1] if 1 <= flag["sentence"] <= len(planted) else None
        )
        checked.append(entry)

    blunt = [fault["id"] for fault in faults if fault["level"] == "blunt"]
    return {
        "caught": sorted(caught),
        "missed": sorted(fault["id"] for fault in faults if fault["id"] not in caught),
        "blunt_caught": sorted(fault_id for fault_id in blunt if fault_id in caught),
        "false_alarms": [entry for entry in checked if entry["catches"] is None],
        "flags": checked,
    }


def verdict(caught, blunt_caught):
    """The rule of the plan, for 12 faults of which 6 are blunt."""
    if blunt_caught < 5:
        return "stop"
    if caught >= 11:
        return "too easy"
    return "go on"


# ----------------------------------------------------------- the model call


def build_request(deployment, chapter, planted):
    """The body of the request. It holds the two numbered texts and the fixed
    shape of the answer. It holds nothing from the answer key."""
    chapter_text = "\n\n".join("[P%d] %s" % (n, p) for n, p in enumerate(chapter, start=1))
    script_text = "\n".join("[S%d] %s" % (n, s) for n, s in enumerate(planted, start=1))
    return {
        "model": deployment,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": "THE CHAPTER\n\n" + chapter_text + "\n\nTHE SCRIPT\n\n" + script_text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "script_check", "strict": True, "schema": ANSWER_SHAPE},
        },
    }


def parse_answer(response):
    """Take the list of flags out of the answer of the model service.
    Raises ProbeError when the answer does not have the fixed shape."""
    try:
        choice = response["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise ProbeError("The answer of the model has no message.")
    if message.get("refusal"):
        raise ProbeError("The model refused to answer: %s" % message["refusal"])
    if choice.get("finish_reason") != "stop":
        raise ProbeError("The model did not finish its answer (finish_reason: %s)." % choice.get("finish_reason"))
    try:
        flags = json.loads(message.get("content") or "")["flags"]
    except (ValueError, KeyError, TypeError):
        raise ProbeError("The answer of the model does not have the fixed shape: no list of flags.")
    if not isinstance(flags, list):
        raise ProbeError("The answer of the model does not have the fixed shape: the flags are not a list.")
    for flag in flags:
        ok = isinstance(flag, dict) and set(flag) == set(FLAG_FIELDS)
        ok = ok and all(type(flag[name]) is kind for name, kind in FLAG_FIELDS.items())
        if not ok or flag["kind"] not in KINDS:
            raise ProbeError("The answer of the model does not have the fixed shape: %s" % json.dumps(flag))
    return flags


def get_key(resource, group):
    """Ask the Azure CLI for the key. The key stays in memory only."""
    command = [
        "az", "cognitiveservices", "account", "keys", "list",
        "--name", resource, "--resource-group", group,
        "--query", "key1", "--output", "tsv",
    ]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise ProbeError("The Azure CLI (az) is not installed.")
    except subprocess.TimeoutExpired:
        raise ProbeError("The Azure CLI did not answer in 120 seconds.")
    key = done.stdout.strip()
    if done.returncode != 0 or not key:
        raise ProbeError("The Azure CLI gave no key: %s" % " ".join(done.stderr.split()))
    return key


def call_model(url, key, body):
    """Send one request and return the answer as Python data."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = " ".join(error.read().decode("utf-8", "replace").split())
        raise ProbeError("The model service answered %d: %s" % (error.code, detail[:500]))
    except (urllib.error.URLError, OSError) as error:
        raise ProbeError("The model service could not be reached: %s" % error)
    except ValueError:
        raise ProbeError("The model service did not answer in JSON.")


# --------------------------------------------------------------- the report


def render(report, faults, out):
    by_id = dict((fault["id"], fault) for fault in faults)
    write = lambda line="": out.write(line + "\n")
    write("Probe: can the model find planted faults?")
    write("Model: %s (deployment: %s)" % (report["model"], report["deployment"]))
    write()
    for fault in faults:
        state = "caught" if fault["id"] in report["caught"] else "MISSED"
        write("%s  %-6s  kind %d, %-6s  %s" % (fault["id"], state, fault["kind"], fault["level"], KINDS[fault["kind"]]))
        for entry in report["flags"]:
            if entry["catches"] == fault["id"]:
                write("      the model: %s" % entry["reason"])
    write()
    write("Caught %d of %d. Blunt faults caught: %d of %d." % (
        len(report["caught"]), len(faults), len(report["blunt_caught"]),
        len([fault for fault in faults if fault["level"] == "blunt"]),
    ))
    write("False alarms: %d. A false alarm may be a real fault that nobody planted: read each one." % len(report["false_alarms"]))
    for entry in report["false_alarms"]:
        where = "S%d" % entry["sentence"] if entry["sentence"] else "left out"
        write("  - %s, kind %d, P%d: %s" % (where, entry["kind"], entry["paragraph"], entry["reason"]))
        if entry["sentence_text"]:
            write("      script: %s" % entry["sentence_text"])
        write("      book:   %s" % entry["quote"])
    not_found = [entry for entry in report["flags"] if not entry["quote_found"]]
    write("Flags with a quote that is not in the chapter word for word: %d of %d." % (len(not_found), len(report["flags"])))
    wrong_kind = [
        entry for entry in report["flags"]
        if entry["catches"] and by_id[entry["catches"]]["kind"] != entry["kind"]
    ]
    write("Catches where the model named another kind than the answer key: %d." % len(wrong_kind))
    usage = report["usage"]
    write("Tokens: %s in, %s out. Seconds: %.1f." % (
        usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"), report["seconds"],
    ))
    write()
    write("Verdict: %s" % report["verdict"].upper())


def main(argv=None, get_key=get_key, call_model=call_model, out=sys.stdout, results_folder=None):
    parser = argparse.ArgumentParser(description="Probe: can the model find planted faults?")
    parser.add_argument("--resource", required=True, help="the name of the Azure resource that holds the model")
    parser.add_argument("--resource-group", required=True, help="the resource group of that resource")
    parser.add_argument("--deployment", required=True, help="the name of the model deployment")
    args = parser.parse_args(argv)
    results_folder = results_folder or os.path.join(HERE, "results")

    try:
        chapter = read_chapter(os.path.join(HERE, "chapter.txt"))
        script = read_script(os.path.join(HERE, "script.txt"))
        faults = read_faults(os.path.join(HERE, "faults.json"))
        planted, placed = plant(script, faults)
        body = build_request(args.deployment, chapter, planted)
        key = get_key(args.resource, args.resource_group)
        url = "https://%s.openai.azure.com/openai/v1/chat/completions" % args.resource
        started = time.time()
        response = call_model(url, key, body)
        seconds = time.time() - started
        flags = parse_answer(response)
    except ProbeError as error:
        out.write("ERROR: %s\n" % error)
        return 1

    report = score(faults, placed, chapter, planted, flags)
    report["verdict"] = verdict(len(report["caught"]), len(report["blunt_caught"]))
    report["date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    report["deployment"] = args.deployment
    report["model"] = response.get("model", "?")
    report["usage"] = response.get("usage", {})
    report["seconds"] = round(seconds, 1)

    render(report, faults, out)
    os.makedirs(results_folder, exist_ok=True)
    path = os.path.join(results_folder, time.strftime("%Y-%m-%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    out.write("Saved: %s\n" % os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
