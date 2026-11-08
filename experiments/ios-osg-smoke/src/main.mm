// Isolated OSG traversal over the proven external ANGLE Metal context.
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
#include "OSGScene.hpp"
#include "GLDebugCapture.hpp"

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
    NSFileHandle *file = [NSFileHandle fileHandleForWritingAtPath:Documents(@"osg-smoke.log")];
    if (!file) {
        [line writeToFile:Documents(@"osg-smoke.log") atomically:YES encoding:NSUTF8StringEncoding error:nil];
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

@interface OSGViewController : UIViewController {
    std::unique_ptr<Renderer> renderer;
    unsigned long long swaps;
    unsigned long long windowSwaps;
    double rateStart, previousCallback, callbackTotal, cpuTotal;
    unsigned callbacks;
    double swapRate, cpuMs, callbackMs;
    bool clearOnly, previousY, previousX, previousRight, buttonsPrimed;
    __weak GCController *previousController;
}
@property(nonatomic, strong) CADisplayLink *displayLink;
@property(nonatomic, strong) UILabel *overlay;
@property(nonatomic, copy) NSString *failure;
- (void)activate;
- (void)deactivate;
@end
@implementation OSGViewController
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
    Log(@"New OSG ANGLE session; requested callback rate 30 Hz; display FPS unmeasured");
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
    result[@"osg_frames"] = @(renderer && renderer->osgScene ? renderer->osgScene->frames : 0);
    result[@"osg_traversal_wall_ms"] = @(renderer && renderer->osgScene ? renderer->osgScene->traversalWallMs : 0);
    result[@"osg_warnings"] = @(renderer && renderer->osgScene ? renderer->osgScene->warnings() : 0);
    result[@"gl_errors"] = @(renderer ? renderer->errors : 0);
    result[@"failure"] = self.failure;
    result[@"shader_error"] = renderer ? renderer->shaderError : @"";
    result[@"surface_pixels"] = renderer ? @[@(renderer->width), @(renderer->height)] : @[];
    result[@"thermal_state"] = @(NSProcessInfo.processInfo.thermalState);
    result[@"clear_only"] = @(clearOnly);
    result[@"selected_cube"] = renderer && renderer->osgScene ?
        (renderer->osgScene->isTextured() ? @"textured" : @"colored") : @"unavailable";
    result[@"texture_profile"] = renderer && renderer->osgScene ? Text(renderer->osgScene->selectedTextureProfile()) : @"unavailable";
    NSMutableArray *profileResults = [NSMutableArray array];
    if (renderer && renderer->osgScene) for (unsigned profile = 0; profile < 3; ++profile)
        [profileResults addObject:@{@"profile": Text(OSGScene::textureProfileName(profile)),
                                   @"first_traversal_completed": @(renderer->osgScene->textureProfileRendered(profile))}];
    result[@"texture_profiles"] = profileResults;
    NSData *build = [NSData dataWithContentsOfFile:[NSBundle.mainBundle pathForResource:@"angle-build" ofType:@"json"]];
    if (build) result[@"dependency"] = [NSJSONSerialization JSONObjectWithData:build options:0 error:nil] ?: @{};
    NSData *osgBuild = [NSData dataWithContentsOfFile:[NSBundle.mainBundle pathForResource:@"osg-build" ofType:@"json"]];
    if (osgBuild) result[@"osg_build"] = [NSJSONSerialization JSONObjectWithData:osgBuild options:0 error:nil] ?: @{};
    NSData *json = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
    [json writeToFile:Documents(@"osg-smoke.json") atomically:YES];
}
- (void)updateOverlay {
    NSString *identity = renderer ? renderer->identity[@"gl_renderer"] : @"initializing";
    self.overlay.text = [NSString stringWithFormat:
        @"OSG / ANGLE Metal / GLES3 — %@\nRequested callbacks: 30 Hz | display FPS: unmeasured\n"
        @"Successful EGL swaps: %llu | active rate: %.1f/s\nCPU callback mean: %.2f ms | interval mean: %.2f ms\n"
        @"GL errors: %u | thermal: %@ | %dx%d pixels\nTriangle/Y: clear toggle | Square/X: texture/color | %@\n%@%@",
        clearOnly ? @"clear" : (renderer && renderer->osgScene && renderer->osgScene->isTextured() ? @"textured cube" : @"colored cube"), swaps, swapRate, cpuMs, callbackMs,
        renderer ? renderer->errors : 0, @[@"nominal", @"fair", @"serious", @"critical"][NSProcessInfo.processInfo.thermalState],
        renderer ? renderer->width : 0, renderer ? renderer->height : 0,
        previousController ? @"controller connected" : @"controller absent", identity ?: @"",
        self.failure.length ? [@"\nBLOCKED: " stringByAppendingString:self.failure] :
        (renderer && renderer->shaderError.length ? [@"\nClear fallback: " stringByAppendingString:renderer->shaderError] : @"")];
    if (renderer && renderer->osgScene)
        self.overlay.text = [self.overlay.text stringByAppendingFormat:@"\nSelected texture: %@ | D-pad Right: cycle\nOSG traversals: %llu | traversal wall: %.2f ms | warnings/errors: %u",
            Text(renderer->osgScene->selectedTextureProfile()), renderer->osgScene->frames, renderer->osgScene->traversalWallMs, renderer->osgScene->warnings()];
}
- (void)activate {
    [self view]; [self.view layoutIfNeeded];
    if (self.displayLink || self.failure.length) return;
    try {
        if (!renderer) { renderer = std::make_unique<Renderer>(); renderer->start((CAMetalLayer *)self.view.layer); }
        else renderer->resume();
        if (!renderer->sceneAvailable) clearOnly = true;
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
    bool right = pad.dpad.right.isPressed;
    if (controller != previousController || !buttonsPrimed) {
        previousController = controller; previousY = y; previousX = x; buttonsPrimed = true;
        previousRight = right;
    } else {
        if (y && !previousY) clearOnly = !clearOnly;
        if (x && !previousX && renderer && renderer->osgScene)
            renderer->osgScene->setTextured(!renderer->osgScene->isTextured());
        if (right && !previousRight && renderer && renderer->osgScene)
            renderer->osgScene->cycleTextureProfile();
        previousY = y; previousX = x;
        previousRight = right;
    }
    if (renderer && !renderer->sceneAvailable) clearOnly = true;
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

@interface OSGSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation OSGSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [[OSGViewController alloc] init];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene *)scene { (void)scene; [(OSGViewController *)self.window.rootViewController activate]; }
- (void)sceneWillResignActive:(UIScene *)scene { (void)scene; [(OSGViewController *)self.window.rootViewController deactivate]; }
- (void)sceneDidDisconnect:(UIScene *)scene { (void)scene; [(OSGViewController *)self.window.rootViewController deactivate]; self.window = nil; }
@end
@interface OSGAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation OSGAppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options; return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(OSGAppDelegate.class)); }
}
