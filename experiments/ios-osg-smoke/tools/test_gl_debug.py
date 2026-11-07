"""Temporary KHR_debug scope/lifetime contracts; synthetic headers are not pin proof."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GLDebugTests(unittest.TestCase):
    def setUp(self):
        self.capture = (ROOT / 'src/GLDebugCapture.hpp').read_text(encoding='utf-8')
        self.main = (ROOT / 'src/main.mm').read_text(encoding='utf-8')

    def test_runtime_capability_and_khr_pointer_precede_registration(self):
        configure = self.capture.split('std::string configure(', 1)[1].split('std::string attach()', 1)[0]
        self.assertLess(configure.index('if (!advertised)'), configure.index('eglGetProcAddress('))
        self.assertIn('eglGetProcAddress("glDebugMessageCallbackKHR")', configure)
        self.assertIn('if (!callbackProc)', configure)
        self.assertIn('GL_MAX_DEBUG_MESSAGE_LENGTH_KHR', configure)
        self.assertIn('[glExtensions containsObject:@"GL_KHR_debug"]', self.main)
        register = self.main.index('debugCapture.configure(')
        self.assertLess(self.main.index('checkGL("identity queries");'), register)
        self.assertLess(register, self.main.index('std::make_unique<OSGScene>'))

    def test_callback_only_copies_bounded_records_and_cannot_unwind(self):
        callback = self.capture.split('static void GL_APIENTRY capture(', 1)[1].split('bool ownsCurrentContext()', 1)[0]
        self.assertIn('noexcept', callback)
        self.assertIn('catch (...)', callback)
        self.assertIn('std::memcpy(', callback)
        self.assertIn('self->count == RecordLimit', callback)
        self.assertIn('size_t(length) >= self->stride', callback)
        for name in ('glGetError(', 'glEnable(', 'glDisable(', 'eglGet', 'eglMakeCurrent(',
                     'Log(', 'NSLog(', 'write(', 'push_back(', 'resize('):
            self.assertNotIn(name, callback)
        for field in ('@"source"', '@"type"', '@"id"', '@"severity"', '@"message"', '@"phase"', '@"osg_frame"'):
            self.assertIn(field, self.main)
        self.assertIn('initWithBytes:bytes length:record.length', self.main)
        self.assertIn('@"message_encoding"', self.main)
        self.assertIn('@"message_bytes"', self.main)
        self.assertIn('messages dropped', self.capture)
        self.assertIn('(reportedDrops == 0 || final)', self.capture)
        self.assertIn('flushDebug(true);', self.main)

    def test_phase_tracking_and_five_osg_frame_window_are_preserved(self):
        for phase in ('BeforeOSG', 'Initialization', 'Frame', 'ClearOnly'):
            self.assertIn('GLDebugCapture::Phase::' + phase, self.main)
        self.assertLess(self.main.index('GLDebugCapture::Phase::BeforeOSG'), self.main.index('debugCapture.configure('))
        self.assertLess(self.main.index('GLDebugCapture::Phase::Initialization'), self.main.index('std::make_unique<OSGScene>'))
        self.assertIn('GLDebugCapture::Phase::Frame, osgScene->frames + 1', self.main)
        self.assertRegex(self.main, r'if \(osgScene->frames >= 5(?: && debugCapture.active\(\))?\) '
                         r'stopDebug\("five completed OSG-rendered frames"\);')
        draw = self.main.split('bool draw(', 1)[1].split('~Renderer()', 1)[0]
        self.assertLess(draw.index('debugCapture.setPhase('), draw.index('glViewport('))
        scene = (ROOT / 'src/OSGScene.hpp').read_text(encoding='utf-8')
        self.assertIn('setCheckForGLErrors(osg::State::ONCE_PER_ATTRIBUTE)', scene)
        self.assertIn('if (frames == 5)', scene)
        self.assertIn('setCheckForGLErrors(osg::State::ONCE_PER_FRAME)', scene)

    def test_cleanup_covers_pause_foreground_failures_and_context_teardown(self):
        self.assertIn('if (!ownsCurrentContext())', self.capture)
        self.assertIn('callbackProc(nullptr, nullptr);', self.capture)
        self.assertIn('priorSynchronous', self.capture)
        self.assertIn('priorOutput', self.capture)
        for reason in ('OSG initialization failure', 'OSG traversal failure', 'renderer shutdown'):
            self.assertIn('stopDebug("' + reason + '")', self.main)
        pause = self.main.split('void pause()', 1)[1].split('bool draw(', 1)[0]
        self.assertLess(pause.index('stopDebug('), pause.index('eglMakeCurrent('))
        resume = self.main.split('void resume()', 1)[1].split('void pause()', 1)[0]
        self.assertIn('osgScene->frames < 5', resume)
        self.assertLess(resume.index('eglMakeCurrent('), resume.index('debugCapture.attach()'))
        shutdown = self.main.split('~Renderer()', 1)[1]
        self.assertLess(shutdown.index('stopDebug("renderer shutdown")'), shutdown.index('eglDestroyContext('))

    def test_instrumentation_adds_no_error_poll_or_context_attribute_change(self):
        self.assertNotIn('glGetError', self.capture)
        self.assertEqual(len(re.findall(r'\bglGetError\s*\(', self.main)), 2)
        self.assertIn('const EGLint contextAttributes[] = { EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE };', self.main)
        self.assertEqual(self.main.count('eglSwapBuffers(display, surface)'), 1)
        self.assertNotIn('glReadPixels(', self.capture + self.main)
        self.assertNotIn('glTexParameter', self.capture + self.main)

    def test_native_probe_checks_khr_declarations_in_the_selected_artifact_headers(self):
        cmake = (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
        probe = cmake.split('function(check_angle_gl_header_types)', 1)[1].split('endfunction()', 1)[0]
        for declaration in ('${OPENGL_HEADER1}', '${OPENGL_HEADER2}', 'GLDEBUGPROCKHR',
                            'PFNGLDEBUGMESSAGECALLBACKKHRPROC', 'void GL_APIENTRY debugCallbackProbe',
                            'GL_DEBUG_OUTPUT_KHR == 0x92E0',
                            'GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR == 0x8242',
                            'GL_MAX_DEBUG_MESSAGE_LENGTH_KHR == 0x9143'):
            self.assertIn(declaration, probe)
        self.assertIn('unset(OSG_ANGLE_GLES3_HEADER_TYPES_OK CACHE)', probe)

    def test_actual_capture_class_with_synthetic_headers(self):
        compiler = next((path for name in ('clang++', 'g++', 'c++') if (path := shutil.which(name))), None)
        if compiler is None:
            self.skipTest('No local C++ compiler; synthetic fixture is not native ANGLE proof')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'EGL').mkdir()
            (root / 'GLES3').mkdir()
            (root / 'GLES2').mkdir()
            (root / 'EGL/egl.h').write_text('''#pragma once
using EGLDisplay=void*; using EGLContext=void*;
#define EGL_NO_DISPLAY nullptr
#define EGL_NO_CONTEXT nullptr
using Proc=void(*)();
EGLContext eglGetCurrentContext(); EGLDisplay eglGetCurrentDisplay();
Proc eglGetProcAddress(const char*);
''', encoding='utf-8')
            (root / 'GLES3/gl3.h').write_text('''#pragma once
using GLenum=unsigned; using GLuint=unsigned; using GLint=int;
using GLboolean=unsigned char; using GLsizei=int; using GLchar=char;
#define GL_APIENTRY
#define GL_FALSE 0
#define GL_TRUE 1
void glGetIntegerv(GLenum,GLint*); GLboolean glIsEnabled(GLenum);
void glEnable(GLenum); void glDisable(GLenum);
''', encoding='utf-8')
            (root / 'GLES2/gl2ext.h').write_text('''#pragma once
#define GL_DEBUG_OUTPUT_KHR 0x92E0
#define GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR 0x8242
#define GL_MAX_DEBUG_MESSAGE_LENGTH_KHR 0x9143
using GLDEBUGPROCKHR=void(*)(GLenum,GLenum,GLuint,GLenum,GLsizei,const GLchar*,const void*);
using PFNGLDEBUGMESSAGECALLBACKKHRPROC=void(*)(GLDEBUGPROCKHR,const void*);
''', encoding='utf-8')
            source = root / 'fixture.cpp'
            source.write_text('''#include "GLDebugCapture.hpp"
#include <cassert>
static EGLDisplay display=reinterpret_cast<void*>(1);
static EGLContext context=reinterpret_cast<void*>(2);
static bool available=true, output=true, synchronous=false;
static int calls=0, registrations=0, maximum=32;
static GLDEBUGPROCKHR callback=nullptr;
static const void* user=nullptr;
EGLContext eglGetCurrentContext(){return context;}
EGLDisplay eglGetCurrentDisplay(){return display;}
static void install(GLDEBUGPROCKHR cb,const void* data){++calls;++registrations;callback=cb;user=data;}
Proc eglGetProcAddress(const char* name){assert(std::string(name)=="glDebugMessageCallbackKHR");return available?reinterpret_cast<Proc>(&install):nullptr;}
void glGetIntegerv(GLenum p,GLint* v){++calls;assert(p==GL_MAX_DEBUG_MESSAGE_LENGTH_KHR);*v=maximum;}
GLboolean glIsEnabled(GLenum p){++calls;return p==GL_DEBUG_OUTPUT_KHR?output:synchronous;}
void glEnable(GLenum p){++calls;if(p==GL_DEBUG_OUTPUT_KHR)output=true;else{assert(p==GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);synchronous=true;}}
void glDisable(GLenum p){++calls;if(p==GL_DEBUG_OUTPUT_KHR)output=false;else{assert(p==GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);synchronous=false;}}
int main(){
  using Capture=GLDebugCapture;
  Capture missing;
  assert(missing.configure(false,display,context).find("not advertised")!=std::string::npos);
  assert(calls==0 && registrations==0 && !missing.active());
  available=false;
  assert(missing.configure(true,display,context).find("unavailable")!=std::string::npos);
  assert(calls==0 && registrations==0 && !missing.active());
  available=true;
  Capture capture;
  assert(!capture.configure(true,display,context).empty());
  assert(capture.active() && callback && output && synchronous);
  capture.setPhase(Capture::Phase::Initialization);
  const char message[]={'a',0,'b'};
  callback(11,22,33,44,3,message,user);
  unsigned seen=0, losses=0;
  auto write=[&](const Capture::Record& r,const char* bytes){
    assert(r.source==11 && r.type==22 && r.id==33 && r.severity==44);
    if(seen==0)assert(r.phase==Capture::Phase::Initialization && r.frame==0);
    else assert(r.phase==Capture::Phase::Frame && r.frame==3);
    assert(r.length==3 && std::string(bytes,r.length)==std::string(message,3));++seen;
  };
  auto status=[&](const std::string& text){assert(text.find("messages dropped")!=std::string::npos);++losses;};
  capture.drain(write,status);assert(seen==1 && losses==0);
  capture.setPhase(Capture::Phase::Frame,3);
  for(size_t i=0;i<Capture::RecordLimit+2;++i)callback(11,22,33,44,3,message,user);
  capture.drain(write,status);assert(seen==Capture::RecordLimit && losses==1);
  callback(11,22,33,44,3,message,user);
  capture.drain(write,status);assert(losses==1);
  capture.drain(write,status,true);assert(losses==2);
  int before=calls;
  context=reinterpret_cast<void*>(3);
  assert(capture.detach("wrong context").find("not current")!=std::string::npos);
  assert(capture.active() && callback && calls==before);
  context=reinterpret_cast<void*>(2);
  capture.detach("suspend");assert(!capture.active() && !callback && output && !synchronous);
  capture.attach();assert(capture.active() && callback && synchronous);
  capture.detach("five frames");assert(!capture.active() && !callback && output && !synchronous);
  Capture oversized;oversized.configure(true,display,context);
  callback(11,22,33,44,33,message,user);
  oversized.drain(write,status);assert(seen==Capture::RecordLimit && losses==3);
  oversized.detach("oversized fixture");
  Capture badMaximum;maximum=Capture::MessageLimit+1;before=registrations;
  assert(badMaximum.configure(true,display,context).find("budget")!=std::string::npos);
  assert(!badMaximum.active() && registrations==before);
}
''', encoding='utf-8')
            binary = root / 'fixture.exe'
            result = subprocess.run([compiler, '-std=c++17', '-pthread', '-I', str(root), '-I', str(ROOT / 'src'),
                                     str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
