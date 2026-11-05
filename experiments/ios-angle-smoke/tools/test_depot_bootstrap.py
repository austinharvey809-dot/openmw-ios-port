"""Offline regressions for the pinned depot_tools gclient/gn Python split."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_angle


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.depot = self.root / "depot_tools"
        self.depot.mkdir()
        self.pin = build_angle.lock()["depot_tools_revision"]
        self.calls = []

    def runner(self, *, creates_metadata=True, after_revision=None, bootstrap_error=False):
        revisions = iter((self.pin, after_revision or self.pin))

        def run(command, cwd=None, capture=False):
            args = [str(item) for item in command]
            self.calls.append((args, cwd, capture))
            if args[:3] == ["git", "rev-parse", "HEAD"]:
                return next(revisions) + "\n"
            if args[0] == "bash":
                if bootstrap_error:
                    raise subprocess.CalledProcessError(1, args)
                if creates_metadata:
                    folder = self.depot / "bootstrap-fixture_bin/python3/bin"
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / "python3").write_bytes(b"test fixture, never executed")
                    (self.depot / "python3_bin_reldir.txt").write_text(
                        "bootstrap-fixture_bin/python3/bin", encoding="utf-8")
                return ""
            if args == [str(self.depot / "python-bin/python3"), "--version"]:
                return "Python 3.11.8\n"
            self.fail(f"Unexpected command: {args}")
        return run

    def test_explicit_pinned_bootstrap_creates_metadata_without_self_update(self):
        with contextlib.redirect_stdout(io.StringIO()):
            info = build_angle.initialize_depot_tools(self.depot, self.pin, self.runner())
        self.assertEqual(info["revision"], self.pin)
        self.assertEqual(info["python_version"], "Python 3.11.8")
        command = self.calls[1][0]
        self.assertEqual(command[:5], ["bash", "-e", "-o", "pipefail", "-c"])
        self.assertEqual(command[5], 'source "$1/bootstrap_python3"\nbootstrap_python3')
        self.assertEqual(command[6:], ["angle-depot-bootstrap", str(self.depot)])
        self.assertEqual(self.calls[1][1], self.depot)
        self.assertEqual(self.calls[-1][0], [str(self.depot / "python-bin/python3"), "--version"])
        self.assertFalse(any("update_depot_tools" in str(call) for call in self.calls))

    def test_successful_sync_is_not_assumed_to_supply_python_metadata(self):
        # Original failure state: gclient/vpython can succeed without this file.
        self.assertFalse((self.depot / "python3_bin_reldir.txt").exists())
        with self.assertRaisesRegex(RuntimeError, "did not create python3_bin_reldir.txt"):
            build_angle.initialize_depot_tools(self.depot, self.pin, self.runner(creates_metadata=False))
        self.assertFalse(any("python-bin/python3" in str(call) for call in self.calls))

    def test_bootstrap_error_propagates_before_wrapper_or_sync(self):
        with self.assertRaises(subprocess.CalledProcessError):
            build_angle.initialize_depot_tools(self.depot, self.pin, self.runner(bootstrap_error=True))
        self.assertEqual(len(self.calls), 2)

    def test_revision_cannot_change_during_bootstrap(self):
        with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
            build_angle.initialize_depot_tools(self.depot, self.pin, self.runner(after_revision="unexpected"))
        self.assertFalse(any("python-bin/python3" in str(call) for call in self.calls))

    def test_wrong_initial_revision_does_not_run_bootstrap(self):
        with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
            build_angle.initialize_depot_tools(self.depot, "wrong-revision", self.runner())
        self.assertEqual(len(self.calls), 1)

    def test_missing_or_outside_interpreter_is_rejected(self):
        for value in ("", "missing/bin", "../outside/bin", str(self.root / "absolute/bin")):
            with self.subTest(value=value):
                (self.depot / "python3_bin_reldir.txt").write_text(value, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "installed local Python"):
                    build_angle.initialize_depot_tools(self.depot, self.pin, self.runner(creates_metadata=False))

    def test_environment_preserves_pin_and_prevents_interpreter_tool_overrides(self):
        inherited = {"PATH": "original-system-path", "DEPOT_TOOLS_UPDATE": "1",
                     "DEPOT_TOOLS_DIR": "other-checkout", "DEPOT_TOOLS_BOOTSTRAP_PYTHON3": "0",
                     "VPYTHON_BYPASS": "manually managed python not supported by chrome operations",
                     "CUSTOM_CIPD_CLIENT": "unpinned-client", "CHROMIUM_BUILDTOOLS_PATH": "other-gn"}
        with patch.dict(os.environ, inherited, clear=True):
            env = build_angle.build_environment(self.depot)
            self.assertEqual(dict(os.environ), inherited)  # Only the child environment changes.
        self.assertEqual(env["DEPOT_TOOLS_UPDATE"], "0")
        self.assertEqual(env["DEPOT_TOOLS_BOOTSTRAP_PYTHON3"], "1")
        self.assertEqual(env["DEPOT_TOOLS_DIR"], str(self.depot))
        self.assertEqual(env["PATH"], str(self.depot) + os.pathsep + inherited["PATH"])
        for name in ("VPYTHON_BYPASS", "CUSTOM_CIPD_CLIENT", "CHROMIUM_BUILDTOOLS_PATH"):
            self.assertNotIn(name, env)

    def test_pinned_tool_preflight_fails_before_using_path_fallbacks(self):
        source = self.root / "angle"
        paths = ["buildtools/mac/gn", "third_party/ninja/ninja", "third_party/cpython3/host/bin/python3",
                 "third_party/llvm-build/Release+Asserts/bin/clang"]
        for name in paths:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"test fixture, never executed")
        for name in paths:
            with self.subTest(name=name):
                path = source / name
                path.unlink()
                with patch("subprocess.run", side_effect=AssertionError("fallback attempted")):
                    with self.assertRaisesRegex(RuntimeError, "no system fallback"):
                        build_angle.check_build_tools(source, self.depot, subprocess.run)
                path.write_bytes(b"fixture")

    def test_preflight_uses_existing_gn_wrapper_and_pinned_ninja_and_angle_python(self):
        source = self.root / "angle"
        for name in ("buildtools/mac/gn", "third_party/ninja/ninja", "third_party/cpython3/host/bin/python3",
                     "third_party/llvm-build/Release+Asserts/bin/clang"):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        calls = []

        def run(command, cwd, capture):
            calls.append([str(item) for item in command])
            self.assertEqual(cwd, source)
            self.assertTrue(capture)
            return "fixture version\n"

        with contextlib.redirect_stdout(io.StringIO()):
            versions = build_angle.check_build_tools(source, self.depot, run)
        self.assertEqual(calls, [[str(self.depot / "gn"), "--version"],
                                [str(source / "third_party/ninja/ninja"), "--version"],
                                [str(source / "third_party/cpython3/host/bin/python3"), "--version"]])
        self.assertEqual(set(versions), {"gn", "ninja", "angle_python"})

    def test_main_bootstraps_before_sync_with_self_update_still_disabled(self):
        class StopAtSync(Exception):
            pass

        workspace, output = self.root / "work", self.root / "package"
        calls = []

        def fake_process(command, *, cwd, env, **kwargs):
            calls.append(command)
            self.assertTrue(kwargs["check"])
            self.assertEqual(env["DEPOT_TOOLS_UPDATE"], "0")
            depot = workspace / "depot_tools"
            if command[:2] == ["git", "init"]:
                depot.mkdir()
            if command[0] == "bash":
                interpreter = depot / "bootstrap-fixture_bin/python3/bin/python3"
                interpreter.parent.mkdir(parents=True)
                interpreter.write_bytes(b"fixture")
                (depot / "python3_bin_reldir.txt").write_text("bootstrap-fixture_bin/python3/bin", encoding="utf-8")
            if command[0] == str(depot / "gclient"):
                self.assertEqual(command[1], "sync")
                self.assertIn("--nohooks", command)
                raise StopAtSync()
            value = self.pin if command[:3] == ["git", "rev-parse", "HEAD"] else "Python 3.11.8"
            return subprocess.CompletedProcess(command, 0, stdout=value + "\n")

        with patch("platform.system", return_value="Darwin"), \
                patch("shutil.disk_usage", return_value=SimpleNamespace(free=30 * 1024**3)), \
                patch("subprocess.run", side_effect=fake_process), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopAtSync):
                build_angle.main(["--workspace", str(workspace), "--output", str(output), "--allow-downloads"])
        bootstrap_index = next(i for i, command in enumerate(calls) if command[0] == "bash")
        probe_index = next(i for i, command in enumerate(calls) if Path(command[0]).parts[-2:] == ("python-bin", "python3"))
        self.assertLess(bootstrap_index, probe_index)
        self.assertLess(probe_index, len(calls) - 1)
        self.assertTrue(calls[-1][0].endswith("gclient"))


if __name__ == "__main__":
    unittest.main()
