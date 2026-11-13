#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <GameController/GameController.h>
#include <TargetConditionals.h>
#include <sys/utsname.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <chrono>
#include <cstdio>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include "OSGScene.hpp"
#include "GLDebugCapture.hpp"
#include "NifProbe.hpp"
#include "G1BExpectations.hpp"
#include "G1CExpectations.hpp"

static NSMutableDictionary *Evidence;
static NSString *Text(const char* value) { return value ? [NSString stringWithUTF8String:value] : @"<null>"; }
static void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
static NSString *Documents(NSString* name) {
    return [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:name];
}
static void Log(NSString* message) {
    NSString* line = [NSString stringWithFormat:@"%@ %@\n", [NSDate date], message];
    NSLog(@"%@", message);
    NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:Documents(@"g1c-render.log")];
    if (!file) [line writeToFile:Documents(@"g1c-render.log") atomically:YES encoding:NSUTF8StringEncoding error:nil];
    else { [file seekToEndOfFile]; [file writeData:[line dataUsingEncoding:NSUTF8StringEncoding]]; [file closeFile]; }
}
static bool HasExtension(const char* list, const char* name) {
    if (!list) return false;
    return (" " + std::string(list) + " ").find(" " + std::string(name) + " ") != std::string::npos;
}
static void CheckEGL(EGLBoolean result, const char* operation) {
    if (result != EGL_TRUE) {
        char message[180];
        snprintf(message, sizeof(message), "%s failed: EGL error 0x%04x", operation, eglGetError());
        throw std::runtime_error(message);
    }
}
static NSData* Read(NSURL* url) {
    NSNumber *regular = nil, *link = nil;
    Check([url getResourceValue:&regular forKey:NSURLIsRegularFileKey error:nil] && regular.boolValue,
        "Missing/nonregular bundled input");
    Check([url getResourceValue:&link forKey:NSURLIsSymbolicLinkKey error:nil] && !link.boolValue, "Linked bundled input");
    NSData* value = [NSData dataWithContentsOfURL:url];
    Check(value != nil, "Cannot read bundled input");
    return value;
}
static NSString* Digest(NSData* data) {
    return Text(G1A::sha256(std::string(static_cast<const char*>(data.bytes), data.length)).c_str());
}
static NSDictionary* Snapshot(NSURL* directory, NSDictionary* expected, NSUInteger count = 12) {
    NSArray<NSURL*>* entries = [NSFileManager.defaultManager contentsOfDirectoryAtURL:directory
        includingPropertiesForKeys:nil options:0 error:nil];
    Check(entries && entries.count == expected.count && entries.count == count, "Fixture inventory mismatch");
    NSMutableDictionary* result = [NSMutableDictionary dictionary];
    for (NSURL* entry in entries) {
        Check(expected[entry.lastPathComponent] != nil, "Unexpected fixture entry");
        NSData* data = Read(entry);
        NSDictionary* value = @{@"sha256": Digest(data), @"size": @(data.length)};
        Check([value isEqual:expected[entry.lastPathComponent]], "Fixture hash/size mismatch");
        result[entry.lastPathComponent] = value;
    }
    return result;
}

G1C::Scene LoadGeometry() {
#if !TARGET_OS_IPHONE || TARGET_OS_SIMULATOR
    throw std::runtime_error("Physical iPhoneOS product required");
#endif
    NSURL* bundle = NSBundle.mainBundle.resourceURL;
    NSData* build = Read([bundle URLByAppendingPathComponent:@"g1b-build.json"]);
    Check([Digest(build) isEqualToString:Text(G1BExpected::BuildSHA256)], "Build metadata hash mismatch");
    NSDictionary* metadata = [NSJSONSerialization JSONObjectWithData:build options:0 error:nil];
    Check([metadata isKindOfClass:NSDictionary.class] &&
        [metadata[@"source_commit"] isEqual:Text(G1BExpected::SourceCommit)], "Wrong build/source metadata");
    Evidence[@"build"] = metadata;
    NSURL* directory = [bundle URLByAppendingPathComponent:@"Fixtures" isDirectory:YES];
    NSDictionary* before = Snapshot(directory, metadata[@"fixture_snapshot"]);
    Evidence[@"inputs_before"] = before;
    const auto path = std::filesystem::path(directory.fileSystemRepresentation);
    NSMutableArray* cases = [NSMutableArray array];
    Evidence[@"parser_cases"] = cases;
    for (std::size_t i = 0; i < 6; ++i) {
        auto result = G0C::runCase(i, path);
        [cases addObject:@{@"mode": Text(result.mode.c_str()), @"passed": @(result.passed),
            @"exit_code": @(result.exitCode), @"stdout": Text(result.output.c_str()), @"stderr": Text(result.error.c_str())}];
        Check(result.passed, "Genuine parser case failed");
    }
    NSURL* textures = [bundle URLByAppendingPathComponent:@"TexturedFixtures" isDirectory:YES];
    NSDictionary* fixtureManifest = metadata[@"g1c"][@"fixture_manifest"];
    NSMutableDictionary* expected = [fixtureManifest[@"files"] mutableCopy];
    NSData* manifestData = Read([textures URLByAppendingPathComponent:@"fixture-manifest.json"]);
    expected[@"fixture-manifest.json"] = @{@"sha256": Digest(manifestData), @"size": @(manifestData.length)};
    NSDictionary* textureBefore = Snapshot(textures, expected, 11);
    // The compiled metadata digest pins the manifest through its resource inventory.
    for (NSString* name in textureBefore) {
        NSString* key = [@"TexturedFixtures/" stringByAppendingString:name];
        Check([textureBefore[name][@"sha256"] isEqual:metadata[@"resources_sha256"][key]], "Texture fixture metadata mismatch");
    }
    auto owned = G1C::load(std::filesystem::path(textures.fileSystemRepresentation), "textured.bsa",
        G1CExpected::NifSHA256, G1CExpected::TextureSHA256);
    const auto geometryHash = G1A::geometrySHA256(owned.geometry);
    Check(geometryHash == G1BExpected::GeometrySHA256, "Geometry digest differs from proven G1A");
    Check(owned.pixelsSHA256 == G1CExpected::PixelsSHA256, "Decoded RGBA pixels mismatch");
    Evidence[@"geometry"] = @{@"object_id": @"eIOSStatic", @"model": @"TeXtUrEd.NIF",
        @"resource_key": @"meshes/textured.nif", @"resource_sha256": Text(owned.nifSHA256.c_str()),
        @"geometry_sha256": Text(geometryHash.c_str()), @"vertices": @(owned.geometry.positions.size()),
        @"triangles": @(owned.geometry.indices.size() / 3), @"geometry_objects": @1, @"parser_released": @YES};
    Evidence[@"texture"] = @{@"resource_key": Text(owned.textureKey.c_str()),
        @"resource_sha256": Text(owned.textureSHA256.c_str()), @"rgba_sha256": Text(owned.pixelsSHA256.c_str()),
        @"width": @(owned.image->s()), @"height": @(owned.image->t()), @"uv_sets": @1,
        @"diffuse": @[@(owned.diffuse.r()), @(owned.diffuse.g()), @(owned.diffuse.b()), @(owned.diffuse.a())],
        @"cache_hits": @(owned.cacheStats.mHit), @"cache_size_before_clear": @(owned.cacheStats.mSize),
        @"sampler": @"NEAREST/CLAMP_TO_EDGE; no mipmaps", @"parser_vfs_cache_released": @YES};
    Evidence[@"texture_inputs_before"] = textureBefore;
    Evidence[@"texture_inputs_after"] = Snapshot(textures, expected, 11);
    Check([Evidence[@"texture_inputs_after"] isEqual:textureBefore], "Texture inputs changed");
    Evidence[@"inputs_after"] = Snapshot(directory, metadata[@"fixture_snapshot"]);
    Check([Evidence[@"inputs_after"] isEqual:before], "Inputs changed during parsing/conversion");
    Evidence[@"inputs_unchanged"] = @YES;
    Evidence[@"parser_geometry_ready"] = @YES;
    return owned;
}

// The extracted v2 class retains external EGL ownership, single swap, diagnostics and teardown.
#include "AngleRenderer.hpp"

@interface MetalView : UIView
@end
@implementation MetalView
+ (Class)layerClass { return CAMetalLayer.class; }
- (void)layoutSubviews {
    [super layoutSubviews];
    CAMetalLayer* layer = (CAMetalLayer*)self.layer;
    layer.contentsScale = self.window.screen.scale ?: UIScreen.mainScreen.scale;
    layer.drawableSize = CGSizeMake(self.bounds.size.width * layer.contentsScale, self.bounds.size.height * layer.contentsScale);
}
@end

@interface G1BViewController : UIViewController {
    std::unique_ptr<Renderer> renderer;
    unsigned long long swaps;
    bool clearOnly, previousY, buttonsPrimed;
    __weak GCController* previousController;
}
@property(nonatomic, strong) CADisplayLink* displayLink;
@property(nonatomic, strong) UILabel* overlay;
@property(nonatomic, copy) NSString* failure;
- (void)activate;
- (void)deactivate;
@end
@implementation G1BViewController
- (void)loadView { self.view = [[MetalView alloc] init]; }
- (void)viewDidLoad {
    [super viewDidLoad];
    self.failure = @"";
    Evidence = [@{@"session_id": NSUUID.UUID.UUIDString, @"scope": @"G1C synthetic textured NIF resource",
        @"physical_rendering_acceptance": @"UNVERIFIED: independent screenshot/export review required",
        @"gpu_completion": NSNull.null, @"lifecycle_acceptance": NSNull.null,
        @"device_system": UIDevice.currentDevice.systemVersion} mutableCopy];
    struct utsname hardware;
    if (uname(&hardware) == 0) Evidence[@"device_machine"] = Text(hardware.machine);
    Evidence[@"started_utc"] = [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]];
    self.overlay = [[UILabel alloc] init];
    self.overlay.numberOfLines = 6;
    self.overlay.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    self.overlay.textColor = UIColor.whiteColor;
    self.overlay.backgroundColor = [UIColor colorWithWhite:0 alpha:.65];
    self.overlay.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.overlay];
    [NSLayoutConstraint activateConstraints:@[
        [self.overlay.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:8],
        [self.overlay.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-8],
        [self.overlay.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:8],
        [self.overlay.heightAnchor constraintLessThanOrEqualToConstant:100]]];
    Log([NSString stringWithFormat:@"New G1C session %@; source %s; physical rendering acceptance remains unverified",
        Evidence[@"session_id"], G1BExpected::SourceCommit]);
}
- (void)exportResults {
    if (!Evidence) return;
    if (renderer) Evidence[@"runtime_identity"] = renderer->identity;
    Evidence[@"failure"] = self.failure ?: @"";
    Evidence[@"scene_error"] = renderer ? renderer->shaderError : @"";
    Evidence[@"successful_egl_swaps"] = @(swaps);
    Evidence[@"clear_only"] = @(clearOnly);
    Evidence[@"osg_frames"] = @(renderer && renderer->osgScene ? renderer->osgScene->frames : 0);
    Evidence[@"shader_linked"] = @(renderer && renderer->osgScene && renderer->osgScene->shaderLinked);
    Evidence[@"app_polled_gl_errors"] = @(renderer ? renderer->errors : 0);
    Evidence[@"actual_display_fps"] = NSNull.null;
    self.overlay.text = [NSString stringWithFormat:@"G1C textured NIF | session %@\nParser/geometry: %@ | shader linked: %@\nOSG frames: %@ | EGL swaps: %@\nPhysical acceptance: UNVERIFIED\n%@",
        [Evidence[@"session_id"] substringToIndex:8], Evidence[@"parser_geometry_ready"] ?: @NO, Evidence[@"shader_linked"], Evidence[@"osg_frames"],
        Evidence[@"successful_egl_swaps"], self.failure.length ? self.failure :
            (renderer && renderer->shaderError.length ? renderer->shaderError : @"Triangle/Y: diagnostic clear toggle")];
    NSData* data = [NSJSONSerialization dataWithJSONObject:Evidence options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
    if (data) [data writeToFile:Documents(@"g1c-render.json") atomically:YES];
}
- (void)activate {
    [self view]; [self.view layoutIfNeeded];
    if (self.displayLink || self.failure.length) return;
    try {
        if (!renderer) { renderer = std::make_unique<Renderer>(); renderer->start((CAMetalLayer*)self.view.layer); }
        else renderer->resume();
        if (!renderer->sceneAvailable) clearOnly = true;
        buttonsPrimed = false;
        self.displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        self.displayLink.preferredFrameRateRange = CAFrameRateRangeMake(30, 30, 30);
        [self.displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
        UIApplication.sharedApplication.idleTimerDisabled = YES;
    } catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); }
    [self exportResults];
}
- (void)deactivate {
    [self.displayLink invalidate]; self.displayLink = nil;
    UIApplication.sharedApplication.idleTimerDisabled = NO;
    try { if (renderer) renderer->pause(); }
    catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); }
    buttonsPrimed = false;
    [self exportResults];
}
- (void)tick:(CADisplayLink*)link {
    (void)link;
    GCController* controller = nil;
    for (GCController* candidate in GCController.controllers) if (candidate.extendedGamepad) { controller = candidate; break; }
    const bool y = controller.extendedGamepad.buttonY.isPressed;
    if (controller != previousController || !buttonsPrimed) { previousController = controller; previousY = y; buttonsPrimed = true; }
    else { if (y && !previousY) clearOnly = !clearOnly; previousY = y; }
    if (renderer && !renderer->sceneAvailable) clearOnly = true;
    try { if (renderer && renderer->draw(CACurrentMediaTime(), clearOnly)) ++swaps; }
    catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); [self deactivate]; return; }
    if (swaps % 30 == 0) [self exportResults];
}
- (void)dealloc { [self.displayLink invalidate]; }
@end

@interface G1BSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation G1BSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
    (void)session; (void)options;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [[G1BViewController alloc] init];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene*)scene { (void)scene; [(G1BViewController*)self.window.rootViewController activate]; }
- (void)sceneWillResignActive:(UIScene*)scene { (void)scene; [(G1BViewController*)self.window.rootViewController deactivate]; }
- (void)sceneDidDisconnect:(UIScene*)scene {
    (void)scene; [(G1BViewController*)self.window.rootViewController deactivate]; self.window = nil;
}
@end
@interface G1BAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation G1BAppDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
    (void)application; (void)options; return YES;
}
@end
int main(int argc, char** argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(G1BAppDelegate.class)); }
}
