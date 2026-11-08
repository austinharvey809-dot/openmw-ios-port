"""Host-only integration contracts. No dependency checkout, compiler or device required."""
import contextlib
import io
import json
from pathlib import Path
import plistlib
import re
import tempfile
import unittest
from unittest.mock import patch

import prepare_osg
from prepare_osg import LOCK, ROOT, overlay, replace_once
from package_ios import Entry, ValidationError, validate_bundle
from test_package_ios import bundle, REGULAR
from workflow_opt_in import decide


class IntegrationTests(unittest.TestCase):
    def test_osg_pin_matches_main_repository_and_angle_manifest_is_unchanged(self):
        repository = ROOT.parents[1]
        self.assertIn(LOCK["revision"], (repository / "extern/CMakeLists.txt").read_text(encoding="utf-8"))
        self.assertEqual((ROOT / "data/angle-lock.json").read_bytes(),
                         (ROOT.parent / "ios-angle-smoke/data/angle-lock.json").read_bytes())
        self.assertEqual(len(LOCK["source_sha256"]), 4)

    def test_cmake_overlay_is_limited_to_sdk_provider_and_window_ownership(self):
        original = '\n'.join([
            'SET (IPHONE_SDKROOT "${IPHONE_DEVROOT}/SDKs/iPhoneOS${IPHONE_SDKVER}.sdk")',
            'SET(OPENGL_gl_LIBRARY "${IPHONE_SDKROOT}/System/Library/Frameworks/OpenGLES.framework")',
            'SET(OSG_WINDOWING_SYSTEM "IOS" CACHE STRING "Windowing system type for graphics window creation, options only IOS." FORCE)'])
        changed = overlay("CMakeLists.txt", original)
        self.assertIn('${CMAKE_OSX_SYSROOT}', changed)
        self.assertIn('${OSG_ANGLE_GLES_LIBRARY}', changed)
        self.assertIn('OSG_WINDOWING_SYSTEM "None"', changed)
        self.assertNotIn('OpenGLES.framework', changed)
        with self.assertRaises(ValueError): overlay("CMakeLists.txt", changed)

    def test_extension_overlay_selects_egl_without_global_symbol_fallback(self):
        text = overlay("src/osg/GLExtensions.cpp", '#if defined(__ANDROID__)\nlegacy_android();\n#endif\n' + prepare_osg.LOD_CAPABILITY)
        self.assertIn('#include <EGL/egl.h>', text)
        self.assertIn('defined(OSG_IOS_ANGLE)', text)
        self.assertIn('eglGetProcAddress(funcName)', text)
        self.assertIn('#elif defined(__ANDROID__)', text)
        with self.assertRaises(ValueError): replace_once("x x", "x", "y")

    def test_source_checksum_failure_writes_no_partial_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CMakeLists.txt").write_bytes(b"wrong source")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"): prepare_osg.apply(root)
            self.assertEqual((root / "CMakeLists.txt").read_bytes(), b"wrong source")
            self.assertFalse((root / "ios-osg-overlay.json").exists())

    def test_osg_source_plan_does_not_run_git_or_download(self):
        with patch('sys.argv', ['prepare_osg', '--source', 'unused']), \
                patch('subprocess.run', side_effect=AssertionError('network attempted')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(prepare_osg.main(), 0)

    def test_scene_uses_real_osg_traversal_and_exactly_one_external_swap(self):
        main = (ROOT / "src/main.mm").read_text(encoding="utf-8")
        scene = (ROOT / "src/OSGScene.hpp").read_text(encoding="utf-8")
        self.assertEqual(main.count('eglSwapBuffers(display, surface)'), 1)
        self.assertNotIn('glDrawArrays(', main)
        self.assertNotIn('glDrawElements(', main)
        self.assertIn('viewer->frame(time)', scene)
        self.assertIn('viewer->setSceneData(model.get())', scene)
        self.assertIn('geometry->addPrimitiveSet', scene)
        self.assertIn('GraphicsWindowEmbedded', scene)
        self.assertIn('Viewer::SingleThreaded', scene)
        self.assertIn('osg_ModelViewProjectionMatrix', scene)
        self.assertEqual(scene.count('#version 300 es'), 4)
        self.assertNotIn('glReadPixels', main + scene)
        self.assertIn('EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE', main)
        self.assertIn('EGL_DEPTH_SIZE, 24', main)

    def test_osg_resources_profile_and_notices_are_mandatory(self):
        for key in ('osg-lock.json', 'osg-build.json', 'Licenses/osg-LICENSE.txt', 'Licenses/OpenThreads/Thread'):
            files = bundle()
            del files[key]
            with self.subTest(key=key), self.assertRaises(ValidationError): validate_bundle(files)
        files = bundle()
        build = json.loads(files['osg-build.json'].data)
        for override in ({'profile': 'GL2'}, {'windowing': 'IOS'}, {'static': False}, {'revision': 'other'}, {'overlay_version': 1}):
            files['osg-build.json'] = Entry(json.dumps(dict(build, **override)).encode(), REGULAR)
            with self.subTest(override=override), self.assertRaises(ValidationError): validate_bundle(files)

    def test_initial_error_checking_is_fine_grained_before_realization(self):
        scene = (ROOT / 'src/OSGScene.hpp').read_text(encoding='utf-8')
        self.assertIn('#include <osg/State>', scene)
        create = scene.index('window = new osgViewer::GraphicsWindowEmbedded(')
        enable = scene.index('window->getState()->setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE);')
        self.assertLess(create, enable)
        self.assertLess(enable, scene.index('window->getState()->setUseModelViewAndProjectionUniforms('))
        self.assertLess(enable, scene.index('viewer->realize();'))
        self.assertIn('log->write("OSG GL checking: ONCE_PER_ATTRIBUTE', scene[enable:])

    def test_fine_grained_checks_end_after_the_fifth_completed_osg_frame(self):
        scene = (ROOT / 'src/OSGScene.hpp').read_text(encoding='utf-8')
        frame = scene.split('void frame(double time, int w, int h) {', 1)[1].split('~OSGScene()', 1)[0]
        self.assertLess(frame.index('viewer->frame(time);'), frame.index('++frames;'))
        self.assertRegex(frame, r'\+\+frames;\s*(?://[^\n]*\n\s*)*if \(frames == 5\) \{\s*'
                         r'window->getState\(\)->setCheckForGLErrors\(osg::State::ONCE_PER_FRAME\);\s*'
                         r'log->write\("OSG GL checking: ONCE_PER_FRAME restored after 5 OSG-rendered frames"\);\s*\}')
        self.assertEqual(re.findall(r'setCheckForGLErrors\(osg::State::(\w+)\)', scene),
                         ['ONCE_PER_ATTRIBUTE', 'ONCE_PER_FRAME'])
        self.assertEqual(scene.count('++frames;'), 1)
        self.assertEqual(scene.count('frames = 0;'), 1)
        main = (ROOT / 'src/main.mm').read_text(encoding='utf-8')
        self.assertRegex(main, r'if \(clearOnly \|\| !sceneAvailable\) \{\s*glClear\(')
        self.assertIn('try { osgScene->frame(seconds, width, height); }', main)

    def test_diagnostics_keep_notification_and_gl_error_reporting_distinct(self):
        scene = (ROOT / 'src/OSGScene.hpp').read_text(encoding='utf-8')
        self.assertIn('if (level <= osg::WARN) ++warnings;', scene)
        self.assertIn('write("OSG[" + std::to_string(level) + "] " + message);', scene)
        self.assertIn('osg::setNotifyLevel(osg::INFO);', scene)
        self.assertNotIn('glGetError', scene)
        self.assertNotIn('glDebugMessageCallback', scene)
        main = (ROOT / 'src/main.mm').read_text(encoding='utf-8')
        self.assertIn('result[@"osg_warnings"]', main)
        self.assertIn('result[@"gl_errors"]', main)

    def test_controller_lifecycle_and_timing_labels_remain_in_the_isolated_app(self):
        main = (ROOT / 'src/main.mm').read_text(encoding='utf-8')
        for value in ('buttonY.isPressed', 'buttonX.isPressed', 'sceneWillResignActive:', 'sceneDidBecomeActive:',
                      'actual_display_fps', 'successful_egl_swaps', 'cpu_callback_mean_ms'):
            self.assertIn(value, main)
        info = plistlib.loads((ROOT / 'Info.plist.in').read_bytes())
        scenes = info['UIApplicationSceneManifest']['UISceneConfigurations']['UIWindowSceneSessionRoleApplication']
        self.assertEqual(scenes[0]['UISceneDelegateClassName'], 'OSGSceneDelegate')

    def test_expensive_build_requires_its_own_explicit_opt_in(self):
        ref = 'refs/heads/ios-port'
        for text in ('normal push', '[run-angle]'):
            self.assertEqual(decide('push', ref, {'head_commit': {'message': text}})['run_expensive'], 'false')
        self.assertEqual(decide('push', ref, {'head_commit': {'message': '[run-osg]'}})['run_expensive'], 'true')
        self.assertEqual(decide('workflow_dispatch', ref, {})['run_expensive'], 'false')
        workflow = (ROOT.parents[1] / '.github/workflows/ios-osg-smoke.yml').read_text(encoding='utf-8')
        self.assertIn("needs.lightweight-validation.outputs.run_expensive == 'true'", workflow)
        self.assertIn("needs.gate-0-dependency.result == 'success'", workflow)
        self.assertIn('experiments/ios-angle-smoke/tools/build_angle.py', workflow)
        self.assertIn('-DCMAKE_POLICY_VERSION_MINIMUM=3.5', workflow)


if __name__ == '__main__':
    unittest.main()
