"""Pinned LOD-bias adaptations; host fixtures never substitute for the real fork."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_osg as osg


def selected(text, definitions):
    """Select only the simple #if-defined blocks in the audited anchor snippets."""
    enabled = [True]
    output = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.fullmatch(r'#if defined\((\w+)\)', stripped)
        if match:
            enabled.append(enabled[-1] and match.group(1) in definitions)
        elif stripped == '#else':
            enabled[-1] = enabled[-2] and not enabled[-1]
        elif stripped == '#endif':
            enabled.pop()
        elif stripped.startswith('#'):
            raise AssertionError('Unaudited fixture directive: ' + stripped)
        elif enabled[-1]:
            output.append(line)
    if len(enabled) != 1:
        raise AssertionError('Unbalanced audited snippet')
    return '\n'.join(output).strip()


def fixture_sources():
    # Minimal anchor fixtures, not vendored upstream source or pin evidence.
    return {
        'CMakeLists.txt': '\n'.join([
            'SET (IPHONE_SDKROOT "${IPHONE_DEVROOT}/SDKs/iPhoneOS${IPHONE_SDKVER}.sdk")',
            'SET(OPENGL_gl_LIBRARY "${IPHONE_SDKROOT}/System/Library/Frameworks/OpenGLES.framework")',
            'SET(OSG_WINDOWING_SYSTEM "IOS" CACHE STRING "Windowing system type for graphics window creation, options only IOS." FORCE)']),
        'src/osg/GLExtensions.cpp': '#if defined(__ANDROID__)\nlegacy_android();\n#endif\n' + osg.LOD_CAPABILITY,
        'src/osg/Texture.cpp': 'texture parameters before\n' + osg.TEXTURE_LOD_BIAS + '\ntexture parameters after\n',
        'src/osg/Sampler.cpp': 'sampler parameters before\n' + osg.SAMPLER_LOD_BIAS + '\nsampler parameters after\n',
    }


class LODBiasTests(unittest.TestCase):
    def test_original_version_comparison_misclassifies_gles3(self):
        self.assertTrue(3.0 >= 1.2)
        self.assertIn('isTextureLODBiasSupported  = (glVersion >= 1.2f)', osg.LOD_CAPABILITY)
        for emscripten in (False, True):
            definitions = {'OSG_GLES3_AVAILABLE'} | ({'__EMSCRIPTEN__'} if emscripten else set())
            patched = selected(osg.LOD_CAPABILITY_GLES3, definitions)
            self.assertTrue(patched.endswith('isTextureLODBiasSupported = false; // GLES3 does not accept GL_TEXTURE_LOD_BIAS.'))
            original = selected(osg.LOD_CAPABILITY, definitions)
            self.assertTrue(patched.startswith(original))
            self.assertEqual(patched.count('isTextureMaxLevelSupported ='), 1)

    def test_desktop_capability_and_parameter_calls_are_preserved_exactly(self):
        for definitions in (set(), {'OSG_GL3_AVAILABLE'}, {'__EMSCRIPTEN__'}):
            with self.subTest(definitions=definitions):
                self.assertEqual(selected(osg.LOD_CAPABILITY_GLES3, definitions),
                                 selected(osg.LOD_CAPABILITY, definitions))
                self.assertEqual(selected(osg.TEXTURE_LOD_BIAS_GLES3, definitions), osg.TEXTURE_LOD_BIAS.strip())
                self.assertEqual(selected(osg.SAMPLER_LOD_BIAS_GLES3, definitions), osg.SAMPLER_LOD_BIAS.strip())

    def test_gles3_zero_has_no_parameter_call_and_nonzero_is_explicitly_unsupported(self):
        for snippet, forbidden in ((osg.TEXTURE_LOD_BIAS_GLES3, 'glTexParameterf('),
                                   (osg.SAMPLER_LOD_BIAS_GLES3, 'glSamplerParameterf(')):
            active = selected(snippet, {'OSG_GLES3_AVAILABLE'})
            self.assertNotIn(forbidden, active)
            self.assertIn('if (_lodbias != 0.0f)', active)
            self.assertIn('OSG_WARN', active)
            self.assertIn('unsupported on GLES3; bias is not applied.', active)
            self.assertNotIn('GL_TEXTURE_MIN_LOD', active)
            self.assertNotIn('GL_TEXTURE_MAX_LOD', active)
            self.assertNotIn('SWIZZLE', active)

    def test_new_anchors_fail_closed_if_missing_or_duplicated(self):
        cases = (('src/osg/GLExtensions.cpp', osg.LOD_CAPABILITY),
                 ('src/osg/Texture.cpp', osg.TEXTURE_LOD_BIAS),
                 ('src/osg/Sampler.cpp', osg.SAMPLER_LOD_BIAS))
        for name, anchor in cases:
            prefix = '#if defined(__ANDROID__)\n#endif\n' if name.endswith('GLExtensions.cpp') else ''
            for value in ('not the expected anchor', anchor + '\n' + anchor):
                with self.subTest(name=name, duplicate=value != 'not the expected anchor'):
                    with self.assertRaisesRegex(ValueError, 'Expected one overlay anchor'):
                        osg.overlay(name, prefix + value)

    def test_wrong_full_file_hash_leaves_every_source_and_manifest_untouched(self):
        original = fixture_sources()
        fake_lock = dict(osg.LOCK, source_sha256={name: hashlib.sha256(text.encode()).hexdigest()
                                                for name, text in original.items()})
        for bad in original:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                for name, text in original.items():
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((text + ('\nwrong source' if name == bad else '')).encode())
                before = {name: (source / name).read_bytes() for name in original}
                with patch.object(osg, 'LOCK', fake_lock):
                    with self.assertRaisesRegex(ValueError, 'Pinned source checksum mismatch: ' + re.escape(bad)):
                        osg.apply(source)
                self.assertEqual(before, {name: (source / name).read_bytes() for name in original})
                self.assertFalse((source / 'ios-osg-overlay.json').exists())

    def test_manifest_records_exact_four_file_overlay_and_pins_remain_fixed(self):
        self.assertEqual(osg.LOCK['revision'], '9b384d5439977784e5cd250ff8ff7966928ddd27')
        self.assertEqual(osg.LOCK['overlay_version'], 2)
        self.assertEqual(set(osg.LOCK['source_sha256']), set(fixture_sources()))
        self.assertEqual((osg.ROOT / 'data/angle-lock.json').read_bytes(),
                         (osg.ROOT.parent / 'ios-angle-smoke/data/angle-lock.json').read_bytes())
        original = fixture_sources()
        fake_lock = dict(osg.LOCK, source_sha256={name: hashlib.sha256(text.encode()).hexdigest()
                                                for name, text in original.items()})
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name, text in original.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode())
            with patch.object(osg, 'LOCK', fake_lock):
                osg.apply(source)
            manifest = json.loads((source / 'ios-osg-overlay.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['revision'], osg.LOCK['revision'])
            self.assertEqual(manifest['overlay_version'], 2)
            self.assertEqual(manifest['files'], {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                                for name in original})
        for name in ('src/osg/Shader.cpp', 'src/osg/State.cpp', 'src/osg/Texture2D.cpp'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unaudited overlay file'):
                osg.overlay(name, '')

    def test_local_originals_match_hashes_defaults_and_exact_roundtrip(self):
        reference = Path(os.environ.get('OSG_PINNED_SOURCE_REFERENCE',
                         'C:/Users/austi/Downloads/OpenMW-OSG-pinned-source'))
        names = ('src/osg/GLExtensions.cpp', 'src/osg/Texture.cpp', 'src/osg/Sampler.cpp')
        if not all((reference / name).is_file() for name in names):
            self.skipTest('Optional original reference files absent; CI still validates fetched pinned source hashes')
        for name in names:
            with self.subTest(name=name):
                path = reference / name
                data = path.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), osg.LOCK['source_sha256'][name])
                text = data.decode('utf-8')
                changed = osg.overlay(name, text)
                if name.endswith('GLExtensions.cpp'):
                    restored = changed.removeprefix('#include <EGL/egl.h> // isolated ANGLE provider\n')
                    restored = restored.replace('#if defined(OSG_IOS_ANGLE)\n'
                        '        return reinterpret_cast<void*>(eglGetProcAddress(funcName));\n'
                        '    #elif defined(__ANDROID__)', '#if defined(__ANDROID__)', 1)
                    restored = restored.replace(osg.LOD_CAPABILITY_GLES3, osg.LOD_CAPABILITY, 1)
                elif name.endswith('Texture.cpp'):
                    self.assertIn('_lodbias(0.0f),', text)
                    restored = changed.replace(osg.TEXTURE_LOD_BIAS_GLES3, osg.TEXTURE_LOD_BIAS, 1)
                    self.assertEqual(changed.count('GL_TEXTURE_SWIZZLE_RGBA'), text.count('GL_TEXTURE_SWIZZLE_RGBA'))
                else:
                    self.assertIn('_lodbias(0.0f)', text)
                    restored = changed.replace(osg.SAMPLER_LOD_BIAS_GLES3, osg.SAMPLER_LOD_BIAS, 1)
                # Every other byte, including wrap/filter/border/min-max/swizzle
                # operations, remains exactly the supplied original source.
                self.assertEqual(restored.encode(), data)
                self.assertEqual(path.read_bytes(), data)

    def test_real_anchor_snippets_execute_correctly_in_cpp11(self):
        compiler = next((path for name in ('clang++', 'g++', 'c++') if (path := shutil.which(name))), None)
        if compiler is None:
            self.skipTest('No local C++ compiler; actual OSG/ANGLE build remains a separate gate')
        code = '''#include <cassert>
#include <initializer_list>
#include <sstream>
#include <string>
#if defined(TEST_EMSCRIPTEN)
#define __EMSCRIPTEN__
#endif
const unsigned GL_TEXTURE_LOD_BIAS = 0x8501;
int textureCalls=0, samplerCalls=0;
float textureValue=0, samplerValue=0;
bool fixtureExtension=false;
std::ostringstream messages;
#define OSG_WARN messages
bool isGLExtensionSupported(unsigned, const char*) { return fixtureExtension; }
void glTexParameterf(unsigned, unsigned pname, float value) {
  assert(pname==GL_TEXTURE_LOD_BIAS); ++textureCalls; textureValue=value;
}
struct Extensions {
  bool isTextureLODBiasSupported;
  void glSamplerParameterf(unsigned, unsigned pname, float value) {
    assert(pname==GL_TEXTURE_LOD_BIAS); ++samplerCalls; samplerValue=value;
  }
};
void texture(Extensions* extensions,float _lodbias) { unsigned target=1;
''' + osg.TEXTURE_LOD_BIAS_GLES3 + '''
}
void sampler(Extensions* extensions,float _lodbias) { unsigned samplerobject=2;
''' + osg.SAMPLER_LOD_BIAS_GLES3 + '''
}
int main() {
  for(float glVersion : {1.1f, 3.0f}) for(bool extension : {false,true}) {
    fixtureExtension=extension;
    unsigned contextID=0;
    bool isTextureMaxLevelSupported=false,isTextureLODBiasSupported=false;
''' + osg.LOD_CAPABILITY_GLES3 + '''
#if defined(TEST_EMSCRIPTEN)
    bool original=(glVersion>=3.0f)||extension;
    assert(isTextureMaxLevelSupported==(glVersion>=3.0f));
#else
    bool original=(glVersion>=1.2f)||extension;
    assert(isTextureMaxLevelSupported==(glVersion>=1.2f));
#endif
#if defined(OSG_GLES3_AVAILABLE)
    assert(!isTextureLODBiasSupported);
#else
    assert(isTextureLODBiasSupported==original);
#endif
    Extensions ext{isTextureLODBiasSupported};
    for(float bias : {0.0f,2.0f,-1.0f}) {
      textureCalls=samplerCalls=0; messages.str("");
      texture(&ext,bias); sampler(&ext,bias);
#if defined(OSG_GLES3_AVAILABLE)
      assert(textureCalls==0 && samplerCalls==0);
      if(bias==0) assert(messages.str().empty());
      else {
        assert(messages.str().find("Texture::applyTexParameters")!=std::string::npos);
        assert(messages.str().find("Sampler::compileGLObjects")!=std::string::npos);
        assert(messages.str().find("unsupported on GLES3; bias is not applied.")!=std::string::npos);
      }
#else
      assert(textureCalls==(original?1:0) && samplerCalls==1);
      if(original) assert(textureValue==bias);
      assert(samplerValue==bias && messages.str().empty());
#endif
    }
  }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'lod-fixture.cpp'
            source.write_text(code, encoding='utf-8')
            for definitions in ([], ['-DOSG_GLES3_AVAILABLE'], ['-DTEST_EMSCRIPTEN'],
                                ['-DOSG_GLES3_AVAILABLE', '-DTEST_EMSCRIPTEN']):
                with self.subTest(definitions=definitions):
                    binary = Path(directory) / 'lod-fixture.exe'
                    compiled = subprocess.run([compiler, '-std=c++11', *definitions,
                                               str(source), '-o', str(binary)], capture_output=True, text=True)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
