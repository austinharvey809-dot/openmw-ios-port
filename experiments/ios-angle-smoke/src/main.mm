// Standalone Gate 1. No Apple OpenGLES headers, SDL, Vulkan, OSG or GL4ES.
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <GameController/GameController.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <chrono>
#include <cstdio>
#include <cmath>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static NSString *Text(const char *value) { return value ? [NSString stringWithUTF8String:value] : @"<null>"; }
static bool HasExtension(const char *list, const char *name) {
    if (!list) return false;
    std::string value = " " + std::string(list) + " ";
    return value.find(" " + std::string(name) + " ") != std::string::npos;
}
static NSString *Documents(NSString *name) {
    return [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:name];
}
static void Log(NSString *message) {
    NSString *line = [NSString stringWithFormat:@"%@ %@\n", [NSDate date], message];
    NSLog(@"%@", message);
    NSFileHandle *file = [NSFileHandle fileHandleForWritingAtPath:Documents(@"angle-smoke.log")];
    if (!file) {
        [line writeToFile:Documents(@"angle-smoke.log") atomically:YES encoding:NSUTF8StringEncoding error:nil];
    } else {
        [file seekToEndOfFile]; [file writeData:[line dataUsingEncoding:NSUTF8StringEncoding]]; [file closeFile];
    }
}
static void CheckEGL(EGLBoolean result, const char *operation) {
    if (result != EGL_TRUE) {
        char message[180];
        snprintf(message, sizeof(message), "%s failed: EGL error 0x%04x", operation, eglGetError());
        throw std::runtime_error(message);
    }
}

class Renderer {
public:
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLSurface surface = EGL_NO_SURFACE;
    EGLContext context = EGL_NO_CONTEXT;
    GLuint program = 0, vao = 0;
    bool current = false, triangleAvailable = false;
    NSString *shaderError = @"";
    NSMutableDictionary *identity = [NSMutableDictionary dictionary];
    int width = 0, height = 0;
    unsigned errors = 0;

    void checkGL(const char *where) {
        GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            ++errors;
            char message[180];
            snprintf(message, sizeof(message), "%s: GL error 0x%04x", where, error);
            throw std::runtime_error(message);
        }
    }
    GLuint shader(GLenum kind, const char *source) {
        GLuint value = glCreateShader(kind);
        if (!value) throw std::runtime_error("glCreateShader returned zero");
        glShaderSource(value, 1, &source, nullptr); glCompileShader(value);
        GLint status = 0, length = 0;
        glGetShaderiv(value, GL_COMPILE_STATUS, &status);
        glGetShaderiv(value, GL_INFO_LOG_LENGTH, &length);
        std::vector<char> info(static_cast<size_t>(length > 1 ? length : 1), 0);
        if (length > 1) glGetShaderInfoLog(value, length, nullptr, info.data());
        Log([NSString stringWithFormat:@"Shader 0x%x status=%d log=%@", kind, status, Text(info.data())]);
        if (!status) {
            std::string reason = "Shader compilation failed: " + std::string(info.data());
            glDeleteShader(value); throw std::runtime_error(reason);
        }
        return value;
    }
    void buildTriangle() {
        // Vertex ID avoids a per-frame upload. A VAO is still explicitly bound.
        const char *vertex = R"(#version 300 es
precision highp float;
out vec3 color;
const vec2 positions[3] = vec2[3](vec2(-0.65,-0.6),vec2(0.65,-0.6),vec2(0.0,0.65));
const vec3 colors[3] = vec3[3](vec3(1,0.2,0.1),vec3(0.1,1,0.2),vec3(0.2,0.3,1));
void main() { gl_Position = vec4(positions[gl_VertexID],0,1); color=colors[gl_VertexID]; }
)";
        const char *fragment = R"(#version 300 es
precision mediump float;
in vec3 color;
out vec4 result;
void main() { result = vec4(color,1.0); }
)";
        GLuint vs = 0, fs = 0;
        try {
            vs = shader(GL_VERTEX_SHADER, vertex); fs = shader(GL_FRAGMENT_SHADER, fragment);
            program = glCreateProgram();
            glAttachShader(program, vs); glAttachShader(program, fs); glLinkProgram(program);
            GLint status = 0, length = 0;
            glGetProgramiv(program, GL_LINK_STATUS, &status); glGetProgramiv(program, GL_INFO_LOG_LENGTH, &length);
            std::vector<char> info(static_cast<size_t>(length > 1 ? length : 1), 0);
            if (length > 1) glGetProgramInfoLog(program, length, nullptr, info.data());
            Log([NSString stringWithFormat:@"Program link=%d log=%@", status, Text(info.data())]);
            if (!status) throw std::runtime_error("Program link failed: " + std::string(info.data()));
            glGenVertexArrays(1, &vao); glBindVertexArray(vao); checkGL("triangle setup");
            triangleAvailable = true;
        } catch (...) {
            if (vs) glDeleteShader(vs);
            if (fs) glDeleteShader(fs);
            if (program) glDeleteProgram(program);
            program = 0;
            throw;
        }
        glDeleteShader(vs); glDeleteShader(fs);
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
            EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 0, EGL_STENCIL_SIZE, 0, EGL_NONE };
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
        try { buildTriangle(); }
        catch (const std::exception &error) { shaderError = Text(error.what()); Log(shaderError); }
    }
    void resume() {
        if (display != EGL_NO_DISPLAY && context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE) {
            CheckEGL(eglMakeCurrent(display, surface, surface, context), "eglMakeCurrent resume"); current = true;
        }
    }
    void pause() {
        if (current) {
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
        CheckEGL(eglQuerySurface(display, surface, EGL_WIDTH, &width), "eglQuerySurface width");
        CheckEGL(eglQuerySurface(display, surface, EGL_HEIGHT, &height), "eglQuerySurface height");
        if (width <= 0 || height <= 0) return false;
        glViewport(0, 0, width, height);
        glClearColor(0.15f + 0.1f * std::sin(seconds), 0.12f, 0.2f + 0.1f * std::cos(seconds), 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        if (!clearOnly && triangleAvailable) { glUseProgram(program); glBindVertexArray(vao); glDrawArrays(GL_TRIANGLES, 0, 3); }
        checkGL("frame commands");
        CheckEGL(eglSwapBuffers(display, surface), "eglSwapBuffers");
        return true;
    }
    ~Renderer() {
        if (display == EGL_NO_DISPLAY) return;
        if (current) {
            if (vao) glDeleteVertexArrays(1, &vao);
            if (program) glDeleteProgram(program);
        }
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
        if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
        eglTerminate(display);
    }
};

@interface MetalView : UIView
@end
@implementation MetalView
+ (Class)layerClass { return [CAMetalLayer class]; }
- (void)layoutSubviews {
    [super layoutSubviews];
    CAMetalLayer *layer = (CAMetalLayer *)self.layer;
    layer.contentsScale = self.window.screen.scale ?: UIScreen.mainScreen.scale;
    layer.drawableSize = CGSizeMake(self.bounds.size.width * layer.contentsScale, self.bounds.size.height * layer.contentsScale);
}
@end

@interface AngleViewController : UIViewController {
    std::unique_ptr<Renderer> renderer;
    unsigned long long swaps;
    unsigned long long windowSwaps;
    double rateStart, previousCallback, callbackTotal, cpuTotal;
    unsigned callbacks;
    double swapRate, cpuMs, callbackMs;
    bool clearOnly, previousY, previousX, buttonsPrimed;
    __weak GCController *previousController;
}
@property(nonatomic, strong) CADisplayLink *displayLink;
@property(nonatomic, strong) UILabel *overlay;
@property(nonatomic, copy) NSString *failure;
- (void)activate;
- (void)deactivate;
@end
@implementation AngleViewController
- (void)loadView { self.view = [[MetalView alloc] init]; }
- (void)viewDidLoad {
    [super viewDidLoad];
    self.failure = @"";
    self.overlay = [[UILabel alloc] init];
    self.overlay.numberOfLines = 0; self.overlay.textColor = UIColor.whiteColor;
    self.overlay.backgroundColor = [UIColor colorWithWhite:0 alpha:0.65];
    self.overlay.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.overlay.translatesAutoresizingMaskIntoConstraints = NO;
    self.overlay.userInteractionEnabled = NO;
    [self.view addSubview:self.overlay];
    [NSLayoutConstraint activateConstraints:@[
        [self.overlay.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:8],
        [self.overlay.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:8],
        [self.overlay.trailingAnchor constraintLessThanOrEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-8]]];
    Log(@"New ANGLE smoke session; requested callback rate 30 Hz; display FPS unmeasured");
}
- (void)exportResults {
    NSMutableDictionary *result = [NSMutableDictionary dictionaryWithDictionary:renderer ? renderer->identity : @{}];
    result[@"timestamp"] = [[NSDate date] description];
    result[@"requested_callback_hz"] = @30;
    result[@"successful_egl_swaps"] = @(swaps);
    result[@"successful_egl_swaps_per_active_second"] = @(swapRate);
    result[@"actual_display_fps"] = [NSNull null];
    result[@"cpu_callback_mean_ms"] = @(cpuMs);
    result[@"callback_interval_mean_ms"] = @(callbackMs);
    result[@"gl_errors"] = @(renderer ? renderer->errors : 0);
    result[@"failure"] = self.failure;
    result[@"shader_error"] = renderer ? renderer->shaderError : @"";
    result[@"surface_pixels"] = renderer ? @[@(renderer->width), @(renderer->height)] : @[];
    result[@"thermal_state"] = @(NSProcessInfo.processInfo.thermalState);
    result[@"clear_only"] = @(clearOnly);
    NSData *build = [NSData dataWithContentsOfFile:[NSBundle.mainBundle pathForResource:@"angle-build" ofType:@"json"]];
    if (build) result[@"dependency"] = [NSJSONSerialization JSONObjectWithData:build options:0 error:nil] ?: @{};
    NSData *json = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
    [json writeToFile:Documents(@"angle-smoke.json") atomically:YES];
}
- (void)updateOverlay {
    NSString *identity = renderer ? renderer->identity[@"gl_renderer"] : @"initializing";
    self.overlay.text = [NSString stringWithFormat:
        @"ANGLE Metal / GLES3 — %@\nRequested callbacks: 30 Hz | display FPS: unmeasured\n"
        @"Successful EGL swaps: %llu | active rate: %.1f/s\nCPU callback mean: %.2f ms | interval mean: %.2f ms\n"
        @"GL errors: %u | thermal: %@ | %dx%d pixels\nTriangle/Y: clear toggle | Square/X: triangle | %@\n%@%@",
        clearOnly ? @"clear" : @"triangle", swaps, swapRate, cpuMs, callbackMs,
        renderer ? renderer->errors : 0, @[@"nominal", @"fair", @"serious", @"critical"][NSProcessInfo.processInfo.thermalState],
        renderer ? renderer->width : 0, renderer ? renderer->height : 0,
        previousController ? @"controller connected" : @"controller absent", identity ?: @"",
        self.failure.length ? [@"\nBLOCKED: " stringByAppendingString:self.failure] :
        (renderer && renderer->shaderError.length ? [@"\nClear fallback: " stringByAppendingString:renderer->shaderError] : @"")];
}
- (void)activate {
    [self view]; [self.view layoutIfNeeded];
    if (self.displayLink || self.failure.length) return;
    try {
        if (!renderer) { renderer = std::make_unique<Renderer>(); renderer->start((CAMetalLayer *)self.view.layer); }
        else renderer->resume();
        if (!renderer->triangleAvailable) clearOnly = true;
        rateStart = CACurrentMediaTime(); previousCallback = 0;
        callbacks = 0; callbackTotal = cpuTotal = 0; windowSwaps = 0; buttonsPrimed = false;
        self.displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        self.displayLink.preferredFrameRateRange = CAFrameRateRangeMake(30, 30, 30);
        [self.displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
        UIApplication.sharedApplication.idleTimerDisabled = YES;
        Log(@"Active: EGL context current");
    } catch (const std::exception &error) { self.failure = Text(error.what()); Log(self.failure); }
    [self updateOverlay]; [self exportResults];
}
- (void)deactivate {
    [self.displayLink invalidate]; self.displayLink = nil;
    UIApplication.sharedApplication.idleTimerDisabled = NO;
    try { if (renderer) renderer->pause(); }
    catch (const std::exception &error) { self.failure = Text(error.what()); Log(self.failure); }
    buttonsPrimed = false;
    Log(@"Inactive: callbacks paused and context unbound");
    [self updateOverlay]; [self exportResults];
}
- (void)tick:(CADisplayLink *)link {
    (void)link;
    const double start = CACurrentMediaTime();
    if (previousCallback) { callbackTotal += start - previousCallback; ++callbacks; }
    previousCallback = start;
    GCController *controller = nil;
    for (GCController *candidate in GCController.controllers) if (candidate.extendedGamepad) { controller = candidate; break; }
    GCExtendedGamepad *pad = controller.extendedGamepad;
    bool y = pad.buttonY.isPressed, x = pad.buttonX.isPressed;
    if (controller != previousController || !buttonsPrimed) {
        previousController = controller; previousY = y; previousX = x; buttonsPrimed = true;
    } else {
        if (y && !previousY) clearOnly = !clearOnly;
        if (x && !previousX) clearOnly = false;
        previousY = y; previousX = x;
    }
    if (renderer && !renderer->triangleAvailable) clearOnly = true;
    try {
        if (renderer && renderer->draw(start, clearOnly)) { ++swaps; ++windowSwaps; }
    } catch (const std::exception &error) {
        self.failure = Text(error.what()); Log(self.failure); [self deactivate]; return;
    }
    cpuTotal += CACurrentMediaTime() - start;
    if (start - rateStart >= 1.0) {
        swapRate = windowSwaps / (start - rateStart);
        cpuMs = 1000 * cpuTotal / (callbacks + 1);
        callbackMs = callbacks ? 1000 * callbackTotal / callbacks : 0;
        rateStart = start; windowSwaps = 0; callbacks = 0; cpuTotal = callbackTotal = 0; previousCallback = 0;
        [self updateOverlay]; [self exportResults];
    }
}
- (void)dealloc { [self.displayLink invalidate]; }
@end

@interface AngleSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation AngleSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [[AngleViewController alloc] init];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene *)scene { (void)scene; [(AngleViewController *)self.window.rootViewController activate]; }
- (void)sceneWillResignActive:(UIScene *)scene { (void)scene; [(AngleViewController *)self.window.rootViewController deactivate]; }
- (void)sceneDidDisconnect:(UIScene *)scene { (void)scene; [(AngleViewController *)self.window.rootViewController deactivate]; self.window = nil; }
@end
@interface AngleAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation AngleAppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options; return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AngleAppDelegate.class)); }
}
