#import <UIKit/UIKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <dispatch/dispatch.h>
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
#include <filesystem>
#include <utility>
#include "GeometryAdapter.hpp"
#include "OSGScene.hpp"
#include "GLDebugCapture.hpp"
#include "NifProbe.hpp"
#include "G1BExpectations.hpp"
#include "G2Expected.hpp"
#include <CommonCrypto/CommonDigest.h>
#include <fstream>
#include <iomanip>
#include <sstream>

static NSMutableDictionary *Evidence;
static NSString *Text(const char* value) { return value ? [NSString stringWithUTF8String:value] : @"<null>"; }
static void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
static NSString *Documents(NSString* name) {
    return [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:name];
}
static void Log(NSString* message) {
    NSString* line = [NSString stringWithFormat:@"%@ %@\n", [NSDate date], message];
    NSLog(@"%@", message);
    NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:Documents(@"g2-render.log")];
    if (!file) [line writeToFile:Documents(@"g2-render.log") atomically:YES encoding:NSUTF8StringEncoding error:nil];
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

static std::string FileSHA(const std::filesystem::path& path) {
    Check(std::filesystem::is_regular_file(std::filesystem::symlink_status(path)), "Missing/nonregular asset");
    std::ifstream stream(path,std::ios::binary); CC_SHA256_CTX ctx; CC_SHA256_Init(&ctx);
    char block[65536]; while(stream.read(block,sizeof(block)) || stream.gcount()) CC_SHA256_Update(&ctx,block,(CC_LONG)stream.gcount());
    Check(stream.eof(), "Asset read failure"); unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(hash,&ctx);
    std::ostringstream out;for(auto byte:hash)out<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(byte);return out.str();
}
static G2::Environment PrepareGeometry(NSMutableDictionary* report) {
    Check(!NSThread.isMainThread, "CPU loader must run off the main thread");
    const auto startupStart=std::chrono::steady_clock::now();
    NSData* build=Read([NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"g2-build.json"]);
    Check([Digest(build) isEqualToString:Text(G2Expected::SHA)], "G2 provenance changed");
    report[@"build"]=[NSJSONSerialization JSONObjectWithData:build options:0 error:nil];
    NSURL* directory=[NSURL fileURLWithPath:Documents(@"Model") isDirectory:YES];
    NSData* data=Read([directory URLByAppendingPathComponent:@"manifest.json"]);
    NSDictionary* manifest=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    Check([manifest isKindOfClass:NSDictionary.class] && [manifest[@"schema_version"] isEqual:@1], "Invalid private manifest");
    NSDictionary* hashes=manifest[@"files"];Check([hashes isKindOfClass:NSDictionary.class] && hashes.count==2, "Unexpected asset inventory");
    const auto path=std::filesystem::path(directory.fileSystemRepresentation);
    for(NSString* name in @[@"Morrowind.esm",@"Morrowind.bsa"])
        Check([Text(FileSHA(path/name.UTF8String).c_str()) isEqual:hashes[name]], "Private asset hash mismatch");
    const auto loadStart=std::chrono::steady_clock::now();
    auto model=G2::load(path);
    report[@"scene_load_wall_ms"]=@(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-loadStart).count());
    for(NSString* name in @[@"Morrowind.esm",@"Morrowind.bsa"])
        Check([Text(FileSHA(path/name.UTF8String).c_str()) isEqual:hashes[name]], "Private inputs changed during loading");
    report[@"inputs_unchanged"]=@YES;
    report[@"cell"]=Text(model.cell.c_str());
    report[@"references"]=@(model.references);report[@"model_instances"]=@(model.instances);
    report[@"unique_models"]=@(model.models.size());report[@"point_lights"]=@(model.lights.size());
    report[@"editor_markers_excluded"]=@(model.markers);report[@"model_less_lights"]=@(model.modelLessLights);
    report[@"collision_branches_excluded"]=@(model.collisionBranches);
    report[@"particle_branches_omitted"]=@(model.particleBranches);
    report[@"static_environment_only"]=@YES;report[@"full_effects_compatibility"]=@NO;
    report[@"decoded_texture_bytes"]=@(model.decodedBytes);
    report[@"unique_samplers"]=@(model.samplerCount);
    report[@"texture_storage_budget_estimate_bytes"]=@(model.samplerBytes);
    report[@"time_varying_lights_frozen"]=@(model.timeVaryingLights);report[@"off_default_lights"]=@(model.disabledLights);
    NSMutableArray* models=[NSMutableArray array];for(const auto& key:model.models)[models addObject:Text(key.c_str())];report[@"model_resources"]=models;
    NSMutableArray* textureKeys=[NSMutableArray array];for(const auto& key:model.textures)[textureKeys addObject:Text(key.c_str())];report[@"texture_resources"]=textureKeys;
    report[@"geometry"]=@{@"vertices":@(model.vertices),@"triangles":@(model.triangles),@"shapes":@(model.shapes)};
    report[@"private_assets"] = hashes; report[@"parser_geometry_ready"]=@YES;
    report[@"startup_total_wall_ms"]=@(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-startupStart).count());
    return model;
}

// Main-thread, one-shot ownership handoff. The worker never creates EGL/viewer state.
static G2::Environment* PreparedAttachment=nullptr;
G2::Environment LoadGeometry() {
    Check(NSThread.isMainThread && PreparedAttachment && PreparedAttachment->scene.valid(), "Missing prepared interior attachment");
    auto model=std::move(*PreparedAttachment);PreparedAttachment=nullptr;return model;
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
    std::shared_ptr<G2::Environment> prepared;
    bool loading,sceneActive;
    unsigned long long swaps;
    bool clearOnly, previousY, previousA, buttonsPrimed;
    float touchForward,touchStrafe,touchVertical;
    __weak GCController* previousController;
}
@property(nonatomic, strong) CADisplayLink* displayLink;
@property(nonatomic, strong) UILabel* overlay;
@property(nonatomic, copy) NSString* failure;
- (void)activate;
- (void)deactivate;
- (void)pan:(UIPanGestureRecognizer*)gesture;
- (void)moveDown:(UIButton*)button;
- (void)moveUp:(UIButton*)button;
- (void)resetCamera;
- (void)beginPreparation;
- (void)exportResults;
@end
@implementation G1BViewController
- (void)loadView { self.view = [[MetalView alloc] init]; }
- (void)viewDidLoad {
    [super viewDidLoad];
    self.failure = @"";
    [self.view addGestureRecognizer:[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(pan:)]];
    UITapGestureRecognizer* reset=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(resetCamera)];reset.numberOfTapsRequired=2;[self.view addGestureRecognizer:reset];
    UIStackView* movement=[[UIStackView alloc] init];movement.axis=UILayoutConstraintAxisHorizontal;movement.spacing=10;movement.distribution=UIStackViewDistributionFillEqually;
    NSArray* titles=@[@"Left",@"Forward",@"Back",@"Right",@"Up",@"Down"];
    const int tags[]={-1,2,-2,1,3,-3};
    for(unsigned i=0;i<6;++i){UIButton* b=[UIButton buttonWithType:UIButtonTypeSystem];[b setTitle:titles[i] forState:UIControlStateNormal];b.tag=tags[i];b.backgroundColor=[UIColor colorWithWhite:.1 alpha:.8];
        [b addTarget:self action:@selector(moveDown:) forControlEvents:UIControlEventTouchDown];
        [b addTarget:self action:@selector(moveUp:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];[movement addArrangedSubview:b];}
    movement.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:movement];
    [NSLayoutConstraint activateConstraints:@[[movement.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-8],
        [movement.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor],[movement.widthAnchor constraintEqualToAnchor:self.view.widthAnchor multiplier:.7],[movement.heightAnchor constraintEqualToConstant:42]]];
    Evidence = [@{@"session_id": NSUUID.UUID.UUIDString, @"scope": @"G2 original Morrowind interior",
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
    Log([NSString stringWithFormat:@"New G2 session %@; source %s; physical rendering acceptance remains unverified",
        Evidence[@"session_id"], G1BExpected::SourceCommit]);
    [self beginPreparation];
}
- (void)beginPreparation {
    loading=true;Evidence[@"loading_state"]=@"hashing-and-decoding";
    [self exportResults];
    NSMutableDictionary* session=Evidence;
    NSMutableDictionary* report=[NSMutableDictionary dictionary];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0), ^{
        @autoreleasepool {
            std::shared_ptr<G2::Environment> result;
            NSString* failure=nil;
            try { result=std::make_shared<G2::Environment>(PrepareGeometry(report)); }
            catch(const std::exception& error){failure=Text(error.what()) ?: @"Interior preparation failed (non-UTF8 diagnostic)";}
            dispatch_async(dispatch_get_main_queue(), ^{
                // A disconnected old scene must not overwrite a newer session.
                if(Evidence!=session)return;
                self->loading=false;
                if(failure){self.failure=failure;Evidence[@"loading_state"]=@"failed";Log(failure);}
                else {
                    self->prepared=result;
                    [Evidence addEntriesFromDictionary:report];Evidence[@"loading_state"]=@"prepared";
                    if(self->sceneActive)[self activate];
                }
                [self exportResults];
            });
        }
    });
}
- (void)exportResults {
    if (!Evidence) return;
    if (renderer) Evidence[@"runtime_identity"] = renderer->identity;
    Evidence[@"failure"] = self.failure ?: @"";
    Evidence[@"scene_error"] = renderer ? renderer->shaderError : (self.failure ?: @"");
    Evidence[@"successful_egl_swaps"] = @(swaps);
    Evidence[@"clear_only"] = @(clearOnly);
    if(renderer&&renderer->osgScene){const auto& nav=renderer->osgScene->navigation;
        Evidence[@"camera"]=@{@"x":@(nav.eye.x()),@"y":@(nav.eye.y()),@"z":@(nav.eye.z()),@"yaw":@(nav.yaw),@"pitch":@(nav.pitch),@"collision_enabled":@NO};}
    Evidence[@"osg_frames"] = @(renderer && renderer->osgScene ? renderer->osgScene->frames : 0);
    Evidence[@"shader_linked"] = @(renderer && renderer->osgScene && renderer->osgScene->shaderLinked);
    Evidence[@"app_polled_gl_errors"] = @(renderer ? renderer->errors : 0);
    Evidence[@"actual_display_fps"] = NSNull.null;
    self.overlay.text = [NSString stringWithFormat:@"G2 Fargoth interior | session %@\nParser/geometry: %@ | shader linked: %@\nOSG frames: %@ | EGL swaps: %@\nPhysical acceptance: UNVERIFIED\n%@",
        [Evidence[@"session_id"] substringToIndex:8], Evidence[@"parser_geometry_ready"] ?: @NO, Evidence[@"shader_linked"], Evidence[@"osg_frames"],
        Evidence[@"successful_egl_swaps"], self.failure.length ? self.failure :
            (renderer && renderer->shaderError.length ? renderer->shaderError : @"Triangle/Y: diagnostic clear toggle")];
    if(loading)self.overlay.text=@"Loading Fargoth's House...\nControls activate after loading completes.";
    NSData* data = [NSJSONSerialization dataWithJSONObject:Evidence options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil];
    if (data) [data writeToFile:Documents(@"g2-render.json") atomically:YES];
}
- (void)activate {
    [self view]; [self.view layoutIfNeeded];sceneActive=true;
    if(!renderer && (loading || !prepared))return;
    if (self.displayLink || self.failure.length) return;
    try {
        if (!renderer) {
            PreparedAttachment=prepared.get();
            renderer = std::make_unique<Renderer>();renderer->start((CAMetalLayer*)self.view.layer);
            PreparedAttachment=nullptr;prepared.reset();
        }
        else renderer->resume();
        if (!renderer->sceneAvailable) clearOnly = true;
        buttonsPrimed = false;
        self.displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        self.displayLink.preferredFrameRateRange = CAFrameRateRangeMake(30, 30, 30);
        [self.displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
        UIApplication.sharedApplication.idleTimerDisabled = YES;
    } catch (const std::exception& error) { PreparedAttachment=nullptr;prepared.reset();self.failure = Text(error.what()); Log(self.failure); }
    [self exportResults];
}
- (void)deactivate {
    sceneActive=false;
    touchForward=touchStrafe=touchVertical=0;
    if(renderer&&renderer->osgScene)renderer->osgScene->navigation.suspend();
    [self.displayLink invalidate]; self.displayLink = nil;
    UIApplication.sharedApplication.idleTimerDisabled = NO;
    try { if (renderer) renderer->pause(); }
    catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); }
    buttonsPrimed = false;
    [self exportResults];
}
- (void)pan:(UIPanGestureRecognizer*)gesture {
    CGPoint delta=[gesture translationInView:self.view];[gesture setTranslation:CGPointZero inView:self.view];
    if(renderer&&renderer->osgScene)renderer->osgScene->navigation.turn(-delta.x*.004,-delta.y*.004);
}
- (void)resetCamera {if(renderer&&renderer->osgScene)renderer->osgScene->navigation.reset();}
- (void)moveDown:(UIButton*)button {
    float value=button.tag>0?1:-1;switch(std::abs(int(button.tag))){case 1:touchStrafe=value;break;case 2:touchForward=value;break;case 3:touchVertical=value;break;}
}
- (void)moveUp:(UIButton*)button {
    switch(std::abs(int(button.tag))){case 1:touchStrafe=0;break;case 2:touchForward=0;break;case 3:touchVertical=0;break;}
}
- (void)tick:(CADisplayLink*)link {
    (void)link;
    GCController* controller = nil;
    for (GCController* candidate in GCController.controllers) if (candidate.extendedGamepad) { controller = candidate; break; }
    const bool y = controller.extendedGamepad.buttonY.isPressed;
    const bool a = controller.extendedGamepad.buttonA.isPressed;
    if(renderer&&renderer->osgScene){
        auto& nav=renderer->osgScene->navigation;GCExtendedGamepad* pad=controller.extendedGamepad;
        nav.strafe=pad?pad.leftThumbstick.xAxis.value:touchStrafe;nav.forward=pad?pad.leftThumbstick.yAxis.value:touchForward;
        nav.vertical=pad?pad.rightTrigger.value-pad.leftTrigger.value:touchVertical;
        nav.lookX=pad?pad.rightThumbstick.xAxis.value:0;nav.lookY=pad?pad.rightThumbstick.yAxis.value:0;
        if(buttonsPrimed&&controller==previousController&&a&&!previousA)nav.reset();
    }
    if (controller != previousController || !buttonsPrimed) { previousController = controller; previousY = y;previousA=a; buttonsPrimed = true; }
    else { if (y && !previousY) clearOnly = !clearOnly; previousY = y;previousA=a; }
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
