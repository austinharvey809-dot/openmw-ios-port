#!/usr/bin/env python3
"""Fail-closed ANGLE build opt-in; read event JSON, never shell commit messages."""
import json
import os
from pathlib import Path


def decide(event_name, ref, event):
    run = application = False
    if ref == "refs/heads/ios-port":
        if event_name == "push" and event.get("deleted") is not True:
            head = event.get("head_commit")
            message = head.get("message") if isinstance(head, dict) else None
            run = isinstance(message, str) and "[run-angle]" in message
            application = run
        elif event_name == "workflow_dispatch":
            inputs = event.get("inputs", {})
            # Dispatch event payload booleans are strings; typed inputs may be bools.
            # No generic truthiness: the string "false" must never opt in.
            if isinstance(inputs, dict):
                run = inputs.get("build_dependencies") is True or inputs.get("build_dependencies") == "true"
                value = inputs.get("build_application", True)
                application = run and (value is True or value == "true")
    return {"run_expensive": str(run).lower(), "build_application": str(application).lower()}


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    result = decide(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"], event)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for name, value in result.items():
            output.write(f"{name}={value}\n")
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"ANGLE dependency build opted in: **{result['run_expensive']}**; "
                         f"application requested: **{result['build_application']}**.\n")


if __name__ == "__main__":
    main()
