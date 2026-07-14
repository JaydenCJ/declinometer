"""Shared fixtures: canned outputs and JSONL builders for the test suite."""

import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")

# Canned model outputs, one archetype per failure mode. Used across the
# detector, aggregate, and CLI tests so expectations stay consistent.
HARD_REFUSAL = (
    "I'm sorry, but I can't help with that request. "
    "It goes against my guidelines."
)
POLITE_ANSWER = (
    "To make a basic tomato sauce, saute minced garlic in olive oil, add "
    "crushed tomatoes, season with salt and basil, and simmer for twenty "
    "minutes before tossing with pasta."
)
HEDGED_ANSWER = (
    "I'm not sure, but perhaps it was 1997. Don't quote me on that."
)
PARTIAL_ANSWER = (
    "I can't help with writing the exploit itself, but here is how buffer "
    "overflows work in general:\n"
    "- stack frames grow downward\n"
    "- the return address sits above local buffers\n"
    "- canaries detect overwrites before the return\n"
    "And a safe, contained demo:\n"
    "```c\nint main(void) { return 0; }\n```"
)


@pytest.fixture
def jsonl_file(tmp_path):
    """Factory: write a list of record dicts (or strings) to a JSONL file."""

    def _write(records, name="outputs.jsonl"):
        path = tmp_path / name
        lines = []
        for rec in records:
            lines.append(json.dumps(rec, ensure_ascii=False))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    return _write


def make_record(id_, output, model="demo-model", prompt_version="v1"):
    """A JSONL record dict with the fields declinometer tracks."""
    return {
        "id": id_,
        "model": model,
        "prompt_version": prompt_version,
        "output": output,
    }
