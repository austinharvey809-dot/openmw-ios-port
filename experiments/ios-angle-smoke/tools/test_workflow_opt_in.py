"""Offline opt-in decisions and workflow wiring: ordinary pushes cannot build ANGLE."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from workflow_opt_in import decide, main

REF = "refs/heads/ios-port"
WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/ios-angle-smoke.yml"


class OptInTests(unittest.TestCase):
    def test_ordinary_pushes_and_missing_head_are_denied(self):
        for payload in ({}, {"head_commit": None}, {"head_commit": {}},
                        {"head_commit": {"message": "Update docs"}},
                        {"head_commit": {"message": "[RUN-ANGLE]"}},
                        {"head_commit": {"message": "run-angle"}},
                        {"head_commit": {"message": "[run-angle-ish]"}}):
            with self.subTest(payload=payload):
                self.assertEqual(decide("push", REF, payload),
                                 {"run_expensive": "false", "build_application": "false"})

    def test_only_head_message_token_opts_in_to_both_gates(self):
        event = {"head_commit": {"message": "Test device [run-angle]\n\nDeliberate resource opt-in"}}
        self.assertEqual(decide("push", REF, event),
                         {"run_expensive": "true", "build_application": "true"})
        event = {"head_commit": {"message": "ordinary HEAD"}, "commits": [{"message": "[run-angle]"}],
                 "inputs": {"build_dependencies": "true"}}
        self.assertEqual(decide("push", REF, event)["run_expensive"], "false")

    def test_other_branches_tags_events_and_deletion_cannot_build(self):
        event = {"head_commit": {"message": "[run-angle]"}, "inputs": {"build_dependencies": "true"}}
        for ref in ("refs/heads/main", "refs/heads/feature", "refs/tags/ios-port"):
            for name in ("push", "workflow_dispatch"):
                with self.subTest(name=name, ref=ref):
                    self.assertEqual(decide(name, ref, event)["run_expensive"], "false")
        for name in ("pull_request", "schedule", "repository_dispatch", ""):
            self.assertEqual(decide(name, REF, event)["run_expensive"], "false")
        self.assertEqual(decide("push", REF, dict(event, deleted=True))["run_expensive"], "false")

    def test_dispatch_defaults_and_false_strings_never_opt_in(self):
        for value in (False, "false", "", "True", "yes", 1, None):
            with self.subTest(value=value):
                self.assertEqual(decide("workflow_dispatch", REF, {"inputs": {
                    "build_dependencies": value, "build_application": "true"}})["run_expensive"], "false")
        self.assertEqual(decide("workflow_dispatch", REF, {})["run_expensive"], "false")
        # A dispatch commit message cannot bypass an unchecked dispatch input.
        self.assertEqual(decide("workflow_dispatch", REF, {"head_commit": {"message": "[run-angle]"}})["run_expensive"], "false")

    def test_dispatch_supports_dependency_only_and_full_build(self):
        for value in (True, "true"):
            for app in (True, "true", False, "false"):
                with self.subTest(value=value, app=app):
                    result = decide("workflow_dispatch", REF, {"inputs": {
                        "build_dependencies": value, "build_application": app}})
                    self.assertEqual(result["run_expensive"], "true")
                    self.assertEqual(result["build_application"], "true" if app in (True, "true") else "false")

    def test_event_json_outputs_are_bounded_and_message_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event, output, summary = (root / name for name in ("event.json", "output", "summary"))
            event.write_text(json.dumps({"head_commit": {
                "message": "[run-angle]\nrun_expensive=false\n$(touch forbidden) `exit 1`"}}), encoding="utf-8")
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output),
                     "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_EVENT_NAME": "push", "GITHUB_REF": REF}), \
                    contextlib.redirect_stdout(io.StringIO()):
                main()
            self.assertEqual(output.read_text(encoding="utf-8"), "run_expensive=true\nbuild_application=true\n")
            self.assertNotIn("touch", summary.read_text(encoding="utf-8"))


class WorkflowWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = {name: body for name, body in re.findall(
            r"^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)",
            cls.text.split("\njobs:\n", 1)[1], re.M | re.S)}

    def test_only_push_and_dispatch_triggers_and_dispatch_defaults_to_no_downloads(self):
        trigger = self.text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"^  ([a-z_]+):", trigger, re.M), ["push", "workflow_dispatch"])
        self.assertIn("branches: [ios-port]", trigger)
        self.assertIn("- experiments/ios-angle-smoke/**", trigger)
        self.assertIn("- .github/workflows/ios-angle-smoke.yml", trigger)
        setting = trigger.split("      build_dependencies:\n", 1)[1].split("      build_application:", 1)[0]
        self.assertIn("type: boolean", setting)
        self.assertIn("default: false", setting)

    def test_expensive_job_requires_successful_validation_and_explicit_output(self):
        self.assertEqual(set(self.jobs), {"lightweight-validation", "gate-0-dependency", "gate-1-application"})
        job = self.jobs["gate-0-dependency"]
        self.assertIn("    needs: lightweight-validation\n", job)
        self.assertIn("    if: github.ref == 'refs/heads/ios-port' && needs.lightweight-validation.outputs.run_expensive == 'true'\n", job)
        self.assertNotIn("always()", job.split("    steps:", 1)[0])
        self.assertEqual(self.text.count("--allow-downloads"), 1)
        self.assertIn("--allow-downloads", job)

    def test_lightweight_job_has_no_build_or_download_step_and_wires_script_outputs(self):
        job = self.jobs["lightweight-validation"]
        self.assertIn("runs-on: ubuntu-latest", job)
        self.assertIn('run: python3 "$EXPERIMENT/tools/workflow_opt_in.py"', job)
        self.assertIn("id: opt-in", job)
        self.assertIn("run_expensive: ${{ steps.opt-in.outputs.run_expensive }}", job)
        self.assertIn("build_application: ${{ steps.opt-in.outputs.build_application }}", job)
        self.assertIn("unittest discover", job)
        for forbidden in ("--allow-downloads", "cmake", "gclient", "build_angle.py", "curl ", "wget "):
            self.assertNotIn(forbidden, job)

    def test_application_requires_dependency_success_and_same_run_artifact(self):
        job = self.jobs["gate-1-application"]
        self.assertIn("needs: [lightweight-validation, gate-0-dependency]", job)
        self.assertIn("needs.gate-0-dependency.result == 'success'", job)
        self.assertIn("needs.lightweight-validation.outputs.build_application == 'true'", job)
        self.assertNotIn("always()", job.split("    steps:", 1)[0])
        artifact = "name: ios-angle-gate-0-${{ github.run_id }}"
        self.assertIn(artifact, self.jobs["gate-0-dependency"])
        self.assertIn(artifact, job)
        self.assertIn('tar -xzf dependency-artifact/angle-ios-arm64.tar.gz', job)
        self.assertIn('-DANGLE_ROOT="$RUNNER_TEMP/angle-ios-arm64"', job)

    def test_dependency_failure_evidence_and_no_ordinary_push_cancellation(self):
        job = self.jobs["gate-0-dependency"]
        self.assertIn('2>&1 | tee "$EXPERIMENT/artifacts/gate-0-build.log"', job)
        self.assertIn("if: failure()", job)
        self.assertIn("Preserve GN diagnostics even on dependency failure\n        if: always()", job)
        self.assertIn("uses: actions/upload-artifact@v6\n        if: always()", job)
        self.assertNotIn("cancel-in-progress: true", self.text)


if __name__ == "__main__":
    unittest.main()
