// SPDX-License-Identifier: GPL-3.0-or-later
// Independent capability queries only. No Mesa, OSG, logical device or rendering loop.
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#import "Capabilities.hpp"
#import "Audit.hpp"

#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <string>
#include <sys/utsname.h>

namespace
{
    NSString* documents()
    {
        return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    }
    void writeJSON(NSDictionary* value, NSString* name)
    {
        NSError* error = nil;
        NSData* data = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
        if (!data || ![data writeToFile:[documents() stringByAppendingPathComponent:name] options:NSDataWritingAtomic error:&error])
            throw std::runtime_error(std::string("Cannot export ") + name.UTF8String + ": " + (error.localizedDescription.UTF8String ?: "unknown error"));
    }
}

@interface CapsMetalView : UIView
@end
@implementation CapsMetalView
+ (Class)layerClass { return CAMetalLayer.class; }
@end

@interface CapsViewController : UIViewController
- (void)activate;
- (void)deactivate;
@end

@implementation CapsViewController
{
    CapsMetalView* _surface;
    UITextView* _text;
    UIButton* _share;
    GCController* _controller;
    BOOL _active, _running, _queried;
    NSMutableString* _log;
}
- (void)loadView
{
    self.view = [[UIView alloc] initWithFrame:CGRectZero];
    self.view.backgroundColor = UIColor.blackColor;
    _surface = [[CapsMetalView alloc] initWithFrame:CGRectZero];
    CAMetalLayer* layer = (CAMetalLayer*)_surface.layer;
    layer.device = MTLCreateSystemDefaultDevice();
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = YES;
    [self.view addSubview:_surface];
    _text = [[UITextView alloc] initWithFrame:CGRectZero];
    _text.editable = NO;
    _text.backgroundColor = UIColor.blackColor;
    _text.textColor = UIColor.whiteColor;
    _text.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    _text.text = @"iOS Zink capability audit\nPreparing a one-time Vulkan query...\nNo rendering loop or display-FPS measurement.";
    [self.view addSubview:_text];
    _share = [UIButton buttonWithType:UIButtonTypeSystem];
    [_share setTitle:@"Share audit results (Square/X)" forState:UIControlStateNormal];
    [_share addTarget:self action:@selector(exportResults) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:_share];
    _log = [NSMutableString string];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(controllersChanged:) name:GCControllerDidConnectNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(controllersChanged:) name:GCControllerDidDisconnectNotification object:nil];
}
- (void)viewDidLayoutSubviews
{
    [super viewDidLayoutSubviews];
    _surface.frame = self.view.bounds;
    CAMetalLayer* layer = (CAMetalLayer*)_surface.layer;
    CGFloat scale = self.view.window.windowScene.screen.scale;
    if (scale <= 0) scale = self.view.contentScaleFactor;
    layer.contentsScale = scale;
    layer.drawableSize = CGSizeMake(std::round(self.view.bounds.size.width * scale), std::round(self.view.bounds.size.height * scale));
    CGRect safe = UIEdgeInsetsInsetRect(self.view.bounds, self.view.safeAreaInsets);
    _text.frame = CGRectMake(safe.origin.x + 8, safe.origin.y + 4, std::max<CGFloat>(1, safe.size.width - 16), std::max<CGFloat>(1, safe.size.height - 52));
    _share.frame = CGRectMake(safe.origin.x + 8, CGRectGetMaxY(safe) - 44, std::max<CGFloat>(1, safe.size.width - 16), 40);
}
- (void)record:(NSString*)message
{
    NSLog(@"%@", message);
    [_log appendFormat:@"%@: %@\n", NSDate.date.description, message];
    [_log writeToFile:[documents() stringByAppendingPathComponent:@"audit-latest.log"] atomically:YES encoding:NSUTF8StringEncoding error:nullptr];
}
- (void)controllersChanged:(NSNotification*)notification
{
    (void)notification;
    if (_controller)
    {
        _controller.extendedGamepad.buttonY.pressedChangedHandler = nil;
        _controller.extendedGamepad.buttonX.pressedChangedHandler = nil;
    }
    _controller = nil;
    for (GCController* candidate in GCController.controllers)
        if (candidate.extendedGamepad) { _controller = candidate; break; }
    __weak CapsViewController* weakSelf = self;
    _controller.extendedGamepad.buttonY.pressedChangedHandler = ^(GCControllerButtonInput* button, float value, BOOL pressed) {
        (void)button; (void)value;
        if (pressed) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf runQuery]; });
    };
    _controller.extendedGamepad.buttonX.pressedChangedHandler = ^(GCControllerButtonInput* button, float value, BOOL pressed) {
        (void)button; (void)value;
        if (pressed) dispatch_async(dispatch_get_main_queue(), ^{ [weakSelf exportResults]; });
    };
    [self record:_controller ? @"Controller connected: Triangle/Y reruns query; Square/X exports" : @"No controller; results are also available in Files"];
}
- (void)runQuery
{
    if (!_active || _running || self.presentedViewController) return;
    _running = YES;
    _text.text = @"Querying Vulkan capabilities; no GPU workloads are submitted...";
    [self.view layoutIfNeeded];
    [self record:@"BEGIN: capability query only; feature enablement and Zink execution are not tested"];
    try
    {
        NSString* path = [NSBundle.mainBundle pathForResource:@"mesa-25.1.9-requirements" ofType:@"json"];
        NSData* requirementsData = path ? [NSData dataWithContentsOfFile:path] : nil;
        if (!requirementsData) throw std::runtime_error("Missing pinned requirements manifest");
        NSError* error = nil;
        NSDictionary* requirements = [NSJSONSerialization JSONObjectWithData:requirementsData options:0 error:&error];
        if (error || ![requirements isKindOfClass:NSDictionary.class]) throw std::runtime_error("Invalid requirements manifest");
        NSMutableDictionary* capabilities = [collectCapabilities((CAMetalLayer*)_surface.layer) mutableCopy];
        capabilities[@"audit_id"] = NSUUID.UUID.UUIDString;
        capabilities[@"recorded_at"] = [[NSISO8601DateFormatter new] stringFromDate:NSDate.date];
        capabilities[@"application"] = @{@"bundle_identifier": NSBundle.mainBundle.bundleIdentifier ?: @"unknown",
            @"source_revision": [NSBundle.mainBundle objectForInfoDictionaryKey:@"CapsSourceRevision"] ?: @"not recorded",
            @"iOS_version": UIDevice.currentDevice.systemVersion, @"model": UIDevice.currentDevice.model,
            @"thermal_state": @(NSProcessInfo.processInfo.thermalState), @"actual_display_fps": NSNull.null,
            @"requested_refresh_hz": NSNull.null, @"note": @"No rendering loop, frame pacing or thermal workload test"};
        struct utsname hardware{};
        if (uname(&hardware) == 0)
        {
            NSMutableDictionary* application = [capabilities[@"application"] mutableCopy];
            application[@"hardware_machine"] = [NSString stringWithUTF8String:hardware.machine] ?: @"unknown";
            capabilities[@"application"] = application;
        }
        // Save raw data first so comparison failures cannot hide a completed query.
        writeJSON(capabilities, @"caps-latest.json");
        // A failed comparison must not leave an earlier report paired with new raw data.
        for (NSString* name in @[@"comparison-latest.json", @"summary-latest.txt"])
        {
            NSString* old = [documents() stringByAppendingPathComponent:name];
            if ([NSFileManager.defaultManager fileExistsAtPath:old]
                && ![NSFileManager.defaultManager removeItemAtPath:old error:&error])
                throw std::runtime_error("Cannot replace earlier comparison output");
        }
        writeJSON(requirements, @"requirements-latest.json");
        NSDictionary* report = evaluateCapabilities(capabilities, requirements);
        writeJSON(report, @"comparison-latest.json");
        NSString* summary = auditSummary(report);
        if (![summary writeToFile:[documents() stringByAppendingPathComponent:@"summary-latest.txt"] atomically:YES encoding:NSUTF8StringEncoding error:&error])
            throw std::runtime_error("Cannot export text summary");
        _text.text = [summary stringByAppendingString:@"\nTriangle/Y: repeat query\nSquare/X: share files\nFiles > On My iPhone > iOS Zink Caps\nLatest files are replaced on a new query.\n"];
        _queried = YES;
        [self record:@"COMPLETE: raw capabilities, requirements, comparison and text summary exported. Zink viability remains unproven."];
    }
    catch (const std::exception& failure)
    {
        NSString* message = [NSString stringWithUTF8String:failure.what()];
        _text.text = [@"QUERY BLOCKED\n" stringByAppendingString:message];
        [self record:[@"BLOCKED: " stringByAppendingString:message]];
    }
    _running = NO;
}
- (void)exportResults
{
    if (!_active || _running || self.presentedViewController) return;
    NSMutableArray* urls = [NSMutableArray array];
    for (NSString* name in @[@"caps-latest.json", @"requirements-latest.json", @"comparison-latest.json", @"summary-latest.txt", @"audit-latest.log"])
    {
        NSString* path = [documents() stringByAppendingPathComponent:name];
        if ([NSFileManager.defaultManager fileExistsAtPath:path]) [urls addObject:[NSURL fileURLWithPath:path]];
    }
    if (!urls.count) { [self record:@"No results to share; run the query first"]; return; }
    UIActivityViewController* share = [[UIActivityViewController alloc] initWithActivityItems:urls applicationActivities:nil];
    share.popoverPresentationController.sourceView = _share;
    [self presentViewController:share animated:YES completion:nil];
}
- (void)activate
{
    [self loadViewIfNeeded];
    _active = YES;
    [self controllersChanged:nil];
    if (!_queried) [self runQuery];
}
- (void)deactivate
{
    _active = NO;
    [self record:@"INACTIVE: no callbacks, queries or GPU submissions scheduled"];
}
- (void)dealloc
{
    [NSNotificationCenter.defaultCenter removeObserver:self];
    _controller.extendedGamepad.buttonY.pressedChangedHandler = nil;
    _controller.extendedGamepad.buttonX.pressedChangedHandler = nil;
}
@end

@interface CapsSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation CapsSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options
{
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [CapsViewController new];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene*)scene { (void)scene; [(CapsViewController*)self.window.rootViewController activate]; }
- (void)sceneWillResignActive:(UIScene*)scene { (void)scene; [(CapsViewController*)self.window.rootViewController deactivate]; }
- (void)sceneDidDisconnect:(UIScene*)scene
{
    (void)scene;
    [(CapsViewController*)self.window.rootViewController deactivate];
    self.window = nil;
}
@end

@interface CapsAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation CapsAppDelegate
@end

int main(int argc, char** argv)
{
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(CapsAppDelegate.class)); }
}
