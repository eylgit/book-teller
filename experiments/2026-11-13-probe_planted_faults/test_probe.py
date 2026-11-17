"""Tests for the probe. They need no network and no key.

Run from the top folder of the repository:

    python3 -m unittest discover -s experiments/2026-11-13-probe_planted_faults
"""

import io
import json
import os
import tempfile
import unittest
from collections import Counter

import probe

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE_KEY = "fake-key-0123456789"


def load():
    chapter = probe.read_chapter(os.path.join(HERE, "chapter.txt"))
    script = probe.read_script(os.path.join(HERE, "script.txt"))
    faults = probe.read_faults(os.path.join(HERE, "faults.json"))
    return chapter, script, faults


def flag(sentence, kind=1, paragraph=1, quote="habit"):
    return {
        "sentence": sentence,
        "kind": kind,
        "paragraph": paragraph,
        "quote": quote,
        "reason": "a test flag",
    }


def answer(flags):
    """What the model service sends back, for a list of flags."""
    return {
        "model": "fake-model",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps({"flags": flags})},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TheAnswerKey(unittest.TestCase):
    def setUp(self):
        self.chapter, self.script, self.faults = load()

    def test_01_twelve_faults_two_of_each_kind(self):
        self.assertEqual(len(self.faults), 12)
        pairs = Counter((f["kind"], f["level"]) for f in self.faults)
        for kind in range(1, 7):
            self.assertEqual(pairs[(kind, "blunt")], 1, "kind %d, blunt" % kind)
            self.assertEqual(pairs[(kind, "subtle")], 1, "kind %d, subtle" % kind)
        self.assertEqual(len(set(f["id"] for f in self.faults)), 12)

    def test_02_each_changed_sentence_is_in_the_script_once(self):
        for f in self.faults:
            self.assertEqual(self.script.count(f["original"]), 1, f["id"])

    def test_03_planting_changes_exactly_the_twelve_places(self):
        planted, placed = probe.plant(self.script, self.faults)
        changed = [f for f in self.faults if f["planted"] is not None]
        removed = [f for f in self.faults if f["planted"] is None]
        self.assertEqual(len(planted), len(self.script) - len(removed))
        for f in changed:
            self.assertEqual(planted[placed[f["id"]] - 1], f["planted"], f["id"])
            self.assertNotIn(f["original"], planted, f["id"])
        for f in removed:
            self.assertEqual(placed[f["id"]], 0, f["id"])
            self.assertNotIn(f["original"], planted, f["id"])
        untouched = [s for s in self.script if s not in [f["original"] for f in self.faults]]
        self.assertEqual([s for s in planted if s in self.script], untouched)
        self.assertEqual(len(planted) - len(untouched), len(changed))

    def test_04_every_proof_line_is_in_the_chapter(self):
        for f in self.faults:
            self.assertGreater(probe.find_paragraph(self.chapter, f["proof"]), 0, f["id"])


class Scoring(unittest.TestCase):
    def setUp(self):
        self.chapter, self.script, self.faults = load()
        self.planted, self.placed = probe.plant(self.script, self.faults)

    def score(self, flags):
        return probe.score(self.faults, self.placed, self.chapter, self.planted, flags)

    def clean_sentence(self):
        taken = set(self.placed.values())
        return [n for n in range(1, len(self.planted) + 1) if n not in taken][0]

    def test_05_a_flag_on_a_planted_fault_is_a_catch(self):
        result = self.score([flag(self.placed["F01"])])
        self.assertEqual(result["caught"], ["F01"])
        self.assertEqual(len(result["missed"]), 11)
        self.assertEqual(result["false_alarms"], [])

    def test_06_two_flags_on_one_fault_count_once(self):
        result = self.score([flag(self.placed["F01"]), flag(self.placed["F01"], kind=5)])
        self.assertEqual(result["caught"], ["F01"])
        self.assertEqual(result["false_alarms"], [])

    def test_07_a_flag_on_a_clean_sentence_is_a_false_alarm(self):
        result = self.score([flag(self.clean_sentence())])
        self.assertEqual(result["caught"], [])
        self.assertEqual(len(result["false_alarms"]), 1)

    def test_08_a_left_out_fault_needs_kind_6_and_the_right_paragraph(self):
        f11 = [f for f in self.faults if f["id"] == "F11"][0]
        right = probe.find_paragraph(self.chapter, f11["proof"])
        wrong = right + 1 if right < len(self.chapter) else right - 1
        self.assertEqual(self.score([flag(0, kind=6, paragraph=right)])["caught"], ["F11"])
        self.assertEqual(self.score([flag(0, kind=6, paragraph=wrong)])["caught"], [])
        self.assertEqual(self.score([flag(0, kind=1, paragraph=right)])["caught"], [])

    def test_08b_a_left_out_flag_beside_the_gap_does_not_catch_its_neighbour(self):
        # The model may report a point that is left out by naming the sentence
        # beside the gap. That sentence holds another fault, F04, whose proof is
        # in the same paragraph. Only F11 is caught.
        f11 = [f for f in self.faults if f["id"] == "F11"][0]
        paragraph = probe.find_paragraph(self.chapter, f11["proof"])
        result = self.score([flag(self.placed["F04"], kind=6, paragraph=paragraph)])
        self.assertEqual(result["caught"], ["F11"])

    def test_09_a_quote_that_is_not_in_the_chapter_is_marked(self):
        real = "Education is for behavior, and habits are the stuff of which behavior consists."
        result = self.score(
            [
                flag(self.placed["F01"], quote=real),
                flag(self.placed["F02"], quote="James never wrote this sentence."),
            ]
        )
        found = dict((f["sentence"], f["quote_found"]) for f in result["flags"])
        self.assertTrue(found[self.placed["F01"]])
        self.assertFalse(found[self.placed["F02"]])

    def test_09b_a_quote_is_found_without_the_marks_for_italics(self):
        # The chapter marks italics with underscores. A quote without them still counts.
        quote = "make our nervous system our ally instead of our enemy"
        self.assertGreater(probe.find_paragraph(self.chapter, quote), 0)


class Verdict(unittest.TestCase):
    def test_10_the_three_verdicts(self):
        self.assertEqual(probe.verdict(caught=12, blunt_caught=6), "too easy")
        self.assertEqual(probe.verdict(caught=11, blunt_caught=5), "too easy")
        self.assertEqual(probe.verdict(caught=8, blunt_caught=4), "stop")
        self.assertEqual(probe.verdict(caught=4, blunt_caught=4), "stop")
        self.assertEqual(probe.verdict(caught=8, blunt_caught=5), "go on")
        self.assertEqual(probe.verdict(caught=10, blunt_caught=6), "go on")


class TheModelCall(unittest.TestCase):
    def setUp(self):
        self.chapter, self.script, self.faults = load()
        self.planted, self.placed = probe.plant(self.script, self.faults)

    def test_11_an_answer_in_the_wrong_shape_is_one_clear_error(self):
        wrong = [
            {"choices": []},
            {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"other": 1}'}}]},
            {"choices": [{"finish_reason": "length", "message": {"content": '{"flags": ['}}]},
            {"choices": [{"finish_reason": "stop", "message": {"content": None, "refusal": "no"}}]},
            answer([{"sentence": "three", "kind": 1, "paragraph": 1, "quote": "", "reason": ""}]),
            answer([{"sentence": 3, "kind": 9, "paragraph": 1, "quote": "", "reason": ""}]),
        ]
        for response in wrong:
            with self.assertRaises(probe.ProbeError):
                probe.parse_answer(response)
        self.assertEqual(probe.parse_answer(answer([flag(3)])), [flag(3)])

    def test_11b_the_program_prints_the_error_as_one_line(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            code = probe.main(
                ["--resource", "r", "--resource-group", "g", "--deployment", "d"],
                get_key=lambda resource, group: FAKE_KEY,
                call_model=lambda url, key, body: {"choices": []},
                out=out,
                results_folder=folder,
            )
            self.assertEqual(os.listdir(folder), [])
        self.assertEqual(code, 1)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("ERROR: "))

    def test_12_the_request_holds_the_numbered_texts_and_no_answer_key(self):
        body = probe.build_request("my-deployment", self.chapter, self.planted)
        text = json.dumps(body)
        self.assertEqual(body["model"], "my-deployment")
        self.assertIn("[S1] ", text)
        self.assertIn("[S%d] " % len(self.planted), text)
        self.assertIn("[P1] ", text)
        self.assertIn("[P%d] " % len(self.chapter), text)
        shape = body["response_format"]
        self.assertEqual(shape["type"], "json_schema")
        self.assertTrue(shape["json_schema"]["strict"])
        for f in self.faults:
            self.assertNotIn(f["id"], text)
            self.assertNotIn(json.dumps(f["original"])[1:-1], text, f["id"])
        for word in ("planted", "blunt", "subtle", "twelve", "12 "):
            self.assertNotIn(word, text)

    def test_13_a_report_does_not_contain_the_key(self):
        seen = {}

        def fake_call(url, key, body):
            seen["key"] = key
            seen["url"] = url
            seen["body"] = json.dumps(body)
            return answer([flag(self.placed["F01"]), flag(self.placed["F03"])])

        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            code = probe.main(
                ["--resource", "my-resource", "--resource-group", "g", "--deployment", "d"],
                get_key=lambda resource, group: FAKE_KEY,
                call_model=fake_call,
                out=out,
                results_folder=folder,
            )
            files = os.listdir(folder)
            self.assertEqual(len(files), 1)
            with open(os.path.join(folder, files[0]), encoding="utf-8") as handle:
                saved = handle.read()
        self.assertEqual(code, 0)
        self.assertEqual(seen["key"], FAKE_KEY)
        self.assertEqual(seen["url"], "https://my-resource.openai.azure.com/openai/v1/chat/completions")
        # The model must get the script with the faults in it, not the clean one.
        for f in self.faults:
            self.assertNotIn(json.dumps(f["original"])[1:-1], seen["body"], f["id"])
            if f["planted"] is not None:
                self.assertIn(json.dumps(f["planted"])[1:-1], seen["body"], f["id"])
        self.assertNotIn(FAKE_KEY, saved)
        self.assertNotIn(FAKE_KEY, out.getvalue())
        report = json.loads(saved)
        self.assertEqual(report["caught"], ["F01", "F03"])
        self.assertEqual(report["verdict"], "stop")
        self.assertIn("Caught 2 of 12", out.getvalue())


if __name__ == "__main__":
    unittest.main()
