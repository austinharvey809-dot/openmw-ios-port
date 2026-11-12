#pragma once
class Renderer {
public:
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context = EGL_NO_CONTEXT;
    std::unique_ptr<OSGScene> osgScene;
    GLDebugCapture debugCapture; // callback storage outlives explicit EGL teardown
    bool current = false, sceneAvailable = false;
    NSString *shaderError = @"";
    NSMutableDictionary *identity = [NSMutableDictionary dictionary];
    int width = 0, height = 0;
    unsigned errors = 0;

    void debugStatus(const std::string& message) {
        if (!message.empty()) Log(Text(message.c_str()));
    }
    void flushDebug(bool final = false) {
        debugCapture.drain([](const GLDebugCapture::Record& record, const char* bytes) {
            // Callback only copied bytes. All allocation, encoding and file I/O
            // happens here on the existing rendering thread, after GL returns.
            NSString *message = [[NSString alloc] initWithBytes:bytes length:record.length encoding:NSUTF8StringEncoding];
            const bool utf8 = message != nil;
            if (!message) message = [[NSString alloc] initWithBytes:bytes length:record.length encoding:NSISOLatin1StringEncoding];
            NSDictionary *entry = @{@"source": @(record.source), @"type": @(record.type),
                @"id": @(record.id), @"severity": @(record.severity), @"message": message ?: @"",
                @"message_encoding": utf8 ? @"utf-8" : @"iso-8859-1", @"message_bytes": @(record.length),
                @"phase": Text(GLDebugCapture::phaseName(record.phase)), @"osg_frame": @(record.frame)};
            NSData *json = [NSJSONSerialization dataWithJSONObject:entry options:NSJSONWritingSortedKeys error:nil];
            NSString *text = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
            Log([@"KHR_debug " stringByAppendingString:text ?: @"message serialization failed"]);
        }, [this](const std::string& message) { debugStatus(message); }, final);
    }
    void stopDebug(const char* reason) {
        const std::string status = debugCapture.detach(reason);
        flushDebug(true);
        debugStatus(status);
    }

    void checkGL(const char *where) {
        GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            ++errors;
            char message[180];
            snprintf(message, sizeof(message), "%s: GL error 0x%04x", where, error);
            throw std::runtime_error(message);
        }
    }
    void start(CAMetalLayer *layer) {
        const char *extensions = eglQueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);
        identity[@"egl_client_extensions"] = Text(extensions);
        if (!HasExtension(extensions, "EGL_EXT_platform_base") ||
            !HasExtension(extensions, "EGL_ANGLE_platform_angle") ||
            !HasExtension(extensions, "EGL_ANGLE_platform_angle_metal"))
            throw std::runtime_error("Required ANGLE Metal EGL client extensions unavailable");
        auto getDisplay = reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(eglGetProcAddress("eglGetPlatformDisplayEXT"));
        if (!getDisplay) throw std::runtime_error("eglGetPlatformDisplayEXT unavailable");
        const EGLint attributes[] = { EGL_PLATFORM_ANGLE_TYPE_ANGLE, EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE, EGL_NONE };
        // EXT platform API takes void*, while Apple's EGL_DEFAULT_DISPLAY is int.
        display = getDisplay(EGL_PLATFORM_ANGLE_ANGLE, nullptr, attributes);
        if (display == EGL_NO_DISPLAY) throw std::runtime_error("Metal platform display unavailable; no fallback permitted");
        EGLint major = 0, minor = 0;
        CheckEGL(eglInitialize(display, &major, &minor), "eglInitialize");
        CheckEGL(eglBindAPI(EGL_OPENGL_ES_API), "eglBindAPI");
        const EGLint configAttributes[] = { EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT_KHR,
            EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 0, EGL_NONE };
        EGLConfig config = nullptr; EGLint count = 0;
        CheckEGL(eglChooseConfig(display, configAttributes, &config, 1, &count), "eglChooseConfig");
        if (!count) throw std::runtime_error("No ES3 window config");
        const EGLint contextAttributes[] = { EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE };
        context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes);
        if (context == EGL_NO_CONTEXT) CheckEGL(EGL_FALSE, "eglCreateContext ES3");
        surface = eglCreateWindowSurface(display, config, (__bridge EGLNativeWindowType)layer, nullptr);
        if (surface == EGL_NO_SURFACE) CheckEGL(EGL_FALSE, "eglCreateWindowSurface CAMetalLayer");
        resume();
        CheckEGL(eglSwapInterval(display, 1), "eglSwapInterval");
        GLint glMajor = 0; glGetIntegerv(GL_MAJOR_VERSION, &glMajor);
        NSString *renderer = Text(reinterpret_cast<const char *>(glGetString(GL_RENDERER)));
        if (glMajor < 3 || ![renderer containsString:@"ANGLE"] || ![renderer containsString:@"Metal"])
            throw std::runtime_error("Runtime identity is not ANGLE/Metal OpenGL ES3; refusing fallback");
        identity[@"egl_version"] = Text(eglQueryString(display, EGL_VERSION));
        identity[@"egl_vendor"] = Text(eglQueryString(display, EGL_VENDOR));
        identity[@"egl_display_extensions"] = Text(eglQueryString(display, EGL_EXTENSIONS));
        identity[@"gl_renderer"] = renderer;
        identity[@"gl_vendor"] = Text(reinterpret_cast<const char *>(glGetString(GL_VENDOR)));
        identity[@"gl_version"] = Text(reinterpret_cast<const char *>(glGetString(GL_VERSION)));
        identity[@"glsl_version"] = Text(reinterpret_cast<const char *>(glGetString(GL_SHADING_LANGUAGE_VERSION)));
        NSMutableArray *glExtensions = [NSMutableArray array];
        GLint extensionCount = 0; glGetIntegerv(GL_NUM_EXTENSIONS, &extensionCount);
        for (GLint i = 0; i < extensionCount; ++i)
            [glExtensions addObject:Text(reinterpret_cast<const char *>(glGetStringi(GL_EXTENSIONS, i)))];
        identity[@"gl_extensions"] = glExtensions;
        NSMutableDictionary *configuration = [NSMutableDictionary dictionary];
        for (EGLint key : {EGL_CONFIG_ID, EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE, EGL_ALPHA_SIZE,
                          EGL_DEPTH_SIZE, EGL_STENCIL_SIZE, EGL_SAMPLES, EGL_RENDERABLE_TYPE, EGL_SURFACE_TYPE}) {
            EGLint value = 0; CheckEGL(eglGetConfigAttrib(display, config, key, &value), "eglGetConfigAttrib");
            configuration[[NSString stringWithFormat:@"0x%x", key]] = @(value);
        }
        identity[@"egl_config"] = configuration;
        Log([NSString stringWithFormat:@"Identity: %@", identity]);
        checkGL("identity queries");
        try {
            debugCapture.setPhase(GLDebugCapture::Phase::BeforeOSG);
            debugStatus(debugCapture.configure([glExtensions containsObject:@"GL_KHR_debug"], display, context));
            flushDebug();
            debugCapture.setPhase(GLDebugCapture::Phase::Initialization);
            osgScene = std::make_unique<OSGScene>([](const std::string& message) { Log(Text(message.c_str())); });
            identity[@"osg_version"] = Text(osgGetVersion());
            identity[@"osg_context_id"] = @(osgScene->contextID());
            sceneAvailable = true;
        }
        catch (const std::exception &error) {
            stopDebug("OSG initialization failure");
            shaderError = Text(error.what()); Log(shaderError);
        }
        catch (...) { stopDebug("OSG initialization failure"); throw; }
        flushDebug();
    }
    void resume() {
        if (display != EGL_NO_DISPLAY && context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE) {
            CheckEGL(eglMakeCurrent(display, surface, surface, context), "eglMakeCurrent resume"); current = true;
            if (sceneAvailable && osgScene && osgScene->frames < 5) {
                debugCapture.setPhase(GLDebugCapture::Phase::Frame, osgScene->frames + 1);
                debugStatus(debugCapture.attach());
            }
        }
    }
    void pause() {
        if (current) {
            stopDebug("suspension (remaining diagnostic frames resume on foreground)");
            // One lifecycle drain before iOS suspends us, never in the draw loop.
            glFinish();
            // Unbind even if the drain reports a lost context. Stop visibly on
            // that error; do not keep submitting Metal work while inactive.
            GLenum drainError = glGetError();
            EGLBoolean unbound = eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
            current = false;
            CheckEGL(unbound, "eglMakeCurrent suspend");
            if (drainError != GL_NO_ERROR) {
                ++errors;
                throw std::runtime_error("GL error during lifecycle drain; relaunch required");
            }
        }
    }
    bool draw(double seconds, bool clearOnly) {
        if (!current) return false;
        if (eglGetCurrentContext() != context || eglGetCurrentDisplay() != display)
            throw std::runtime_error("External ANGLE context is not current before OSG frame");
        CheckEGL(eglQuerySurface(display, surface, EGL_WIDTH, &width), "eglQuerySurface width");
        CheckEGL(eglQuerySurface(display, surface, EGL_HEIGHT, &height), "eglQuerySurface height");
        if (width <= 0 || height <= 0) return false;
        if (debugCapture.active())
            debugCapture.setPhase(clearOnly || !sceneAvailable ? GLDebugCapture::Phase::ClearOnly : GLDebugCapture::Phase::Frame,
                                  osgScene ? osgScene->frames + (clearOnly || !sceneAvailable ? 0 : 1) : 0);
        glViewport(0, 0, width, height);
        glClearColor(0.15f + 0.1f * std::sin(seconds), 0.12f, 0.2f + 0.1f * std::cos(seconds), 1.0f);
        if (clearOnly || !sceneAvailable) {
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        } else {
            try { osgScene->frame(seconds, width, height); }
            catch (...) { stopDebug("OSG traversal failure"); throw; }
            if (osgScene->frames >= 5 && debugCapture.active()) stopDebug("five completed OSG-rendered frames");
        }
        if (debugCapture.active()) flushDebug();
        if (eglGetCurrentContext() != context || eglGetCurrentDisplay() != display)
            throw std::runtime_error("OSG changed/released the application-owned EGL context");
        checkGL("frame commands");
        CheckEGL(eglSwapBuffers(display, surface), "eglSwapBuffers");
        return true;
    }
    ~Renderer() {
        if (display == EGL_NO_DISPLAY) return;
        // Cleanup GL calls must use our own context, including after suspension.
        // On rebind failure userdata stays alive through the EGL destruction below.
        if (context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE &&
            (eglGetCurrentContext() != context || eglGetCurrentDisplay() != display))
            current = eglMakeCurrent(display, surface, surface, context) == EGL_TRUE;
        try { stopDebug("renderer shutdown"); } catch (...) { /* context teardown still owns userdata */ }
        osgScene.reset();
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
        if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
        eglTerminate(display);
    }
};
