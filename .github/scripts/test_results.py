"""Summarize `flutter test --reporter json` output and gate head against a baseline.

Usage:
  test_results.py summarize <results.jsonl> <summary.json>
  test_results.py gate <summary-base.json> <summary-head.json>

Gate passes when head introduces no new failing test and passes at least as many tests.
"""

import json
import os
import sys


def summarize(results_path, summary_path):
    names = {}
    suites = {}
    passed, failed, skipped = [], [], []
    load_errors = []
    with open(results_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "suite":
                suite = event["suite"]
                suites[suite["id"]] = os.path.basename(suite.get("path") or "")
            elif kind == "testStart":
                test = event["test"]
                suite_name = suites.get(test.get("suiteID"), "")
                names[test["id"]] = f"{suite_name}: {test['name']}"
            elif kind == "testDone":
                if event.get("hidden"):
                    continue
                name = names.get(event["testID"], str(event["testID"]))
                if event.get("skipped"):
                    skipped.append(name)
                elif event.get("result") == "success":
                    passed.append(name)
                else:
                    failed.append(name)
    summary = {
        "passed": sorted(passed),
        "failed": sorted(failed),
        "skipped": sorted(skipped),
    }
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(f"passed={len(passed)} failed={len(failed)} skipped={len(skipped)}")
    for name in summary["failed"]:
        print(f"  FAIL {name}")
    if not passed and not failed:
        print("::error::no test results parsed")
        sys.exit(1)


def gate(base_path, head_path):
    with open(base_path, encoding="utf-8") as fh:
        base = json.load(fh)
    with open(head_path, encoding="utf-8") as fh:
        head = json.load(fh)
    base_failed = set(base["failed"])
    head_failed = set(head["failed"])
    new_failures = sorted(head_failed - base_failed)
    fixed = sorted(base_failed - head_failed)
    lines = [
        "| | passed | failed | skipped |",
        "|---|---|---|---|",
        f"| base | {len(base['passed'])} | {len(base['failed'])} | {len(base['skipped'])} |",
        f"| head | {len(head['passed'])} | {len(head['failed'])} | {len(head['skipped'])} |",
        "",
        f"new failures: {len(new_failures)}",
        *[f"- {n}" for n in new_failures],
        f"fixed vs base: {len(fixed)}",
        *[f"- {n}" for n in fixed],
    ]
    report = "\n".join(lines)
    print(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    ok = True
    if new_failures:
        print("::error::head introduces failing tests not failing on base")
        ok = False
    if len(head["passed"]) < len(base["passed"]):
        print("::error::head passes fewer tests than base")
        ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("summarize", "gate"):
        print(__doc__)
        sys.exit(2)
    {"summarize": summarize, "gate": gate}[sys.argv[1]](sys.argv[2], sys.argv[3])
