#import <UIKit/UIKit.h>
#import <dispatch/dispatch.h>
#import "NifCheck.hpp"
#include <sys/utsname.h>

@interface NifViewController : UIViewController
@property(nonatomic, strong) UILabel *statusLabel;
@property(nonatomic, strong) UITextView *details;
@property(nonatomic, strong) UIButton *shareButton;
@property(nonatomic, strong) NSURL *jsonURL;
@property(nonatomic, strong) NSURL *logURL;
@property(nonatomic) BOOL started;
@end

@implementation NifViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.statusLabel = [UILabel new];
    self.statusLabel.text = @"OpenMW NIF check — pending";
    self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle1];
    self.statusLabel.numberOfLines = 0;
    self.details = [UITextView new];
    self.details.editable = NO;
    self.details.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    self.details.text = @"Synthetic ESM/BSA/VFS → genuine NIF parser. No rendering.";
    self.shareButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.shareButton setTitle:@"Share diagnostic files" forState:UIControlStateNormal];
    [self.shareButton addTarget:self action:@selector(shareResults) forControlEvents:UIControlEventTouchUpInside];
    self.shareButton.enabled = NO;
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[self.statusLabel, self.details, self.shareButton]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 12;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [stack.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [stack.topAnchor constraintEqualToAnchor:safe.topAnchor constant:12],
        [stack.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-12],
        [self.details.heightAnchor constraintGreaterThanOrEqualToConstant:80]]];
}
- (BOOL)saveEvidence:(NSDictionary *)result error:(NSError **)error {
    NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    if (!documents) return NO;
    self.jsonURL = [documents URLByAppendingPathComponent:@"nif-smoke.json"];
    self.logURL = [documents URLByAppendingPathComponent:@"nif-smoke.log"];
    NSData *json = [NSJSONSerialization dataWithJSONObject:result
        options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:error];
    if (!json || ![json writeToURL:self.jsonURL options:NSDataWritingAtomic error:error]) return NO;
    NSString *text = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    // Both exports contain the complete structured findings, not just a PASS label.
    return [text writeToURL:self.logURL atomically:YES encoding:NSUTF8StringEncoding error:error];
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    if (self.started) return;
    self.started = YES;
    self.statusLabel.text = @"OpenMW NIF check — RUNNING";
    NSError *pendingError = nil;
    if (![self saveEvidence:@{@"status": @"RUNNING", @"scope": @"No completed OpenMW device result yet"} error:&pendingError]) {
        self.statusLabel.text = @"FAIL — cannot save diagnostics";
        self.details.text = pendingError.localizedDescription ?: @"Documents directory unavailable";
        return;
    }
    NSURL *fixtures = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"Fixtures" isDirectory:YES];
    NSURL *metadata = [NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"nif-build.json"];
    // One short data test, no render loop or background execution assertion.
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        NSDictionary *check = RunNifCheck(fixtures, metadata);
        dispatch_async(dispatch_get_main_queue(), ^{
            NSMutableDictionary *result = [check mutableCopy];
            result[@"device"] = @{@"model": UIDevice.currentDevice.model,
                @"system": UIDevice.currentDevice.systemVersion,
                @"thermal_state": @(NSProcessInfo.processInfo.thermalState),
                @"bundle_id": NSBundle.mainBundle.bundleIdentifier ?: @"unknown"};
            struct utsname hardware;
            if (uname(&hardware) == 0) result[@"hardware_machine"] = [NSString stringWithUTF8String:hardware.machine];
            NSError *error = nil;
            BOOL saved = [self saveEvidence:result error:&error];
            BOOL passed = saved && [result[@"status"] isEqualToString:@"PASS"];
            self.statusLabel.text = passed ? @"PASS — genuine OpenMW NIF execution" : @"FAIL — inspect diagnostics";
            self.statusLabel.textColor = passed ? UIColor.systemGreenColor : UIColor.systemRedColor;
            if (saved) {
                NSString *summary = [NSString stringWithFormat:@"ID: %@\nMODL: %@\nVFS: %@\nVertices: %@\nTriangles: %@\nGeometry objects: %@\nSHA-256: %@\n\n",
                    result[@"object_id"] ?: @"unavailable", result[@"model"] ?: @"unavailable",
                    result[@"resource_key"] ?: @"unavailable", result[@"decoded"][@"vertices"] ?: @"unavailable",
                    result[@"decoded"][@"triangles"] ?: @"unavailable", result[@"decoded"][@"geometry"] ?: @"unavailable",
                    result[@"resource_sha256"] ?: @"unavailable"];
                NSString *json = [[NSString alloc] initWithData:
                    [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil]
                    encoding:NSUTF8StringEncoding];
                self.details.text = [summary stringByAppendingString:json ?: @"JSON unavailable"];
            } else self.details.text = error.localizedDescription ?: @"Could not export result";
            self.shareButton.enabled = saved;
        });
    });
}
- (void)shareResults {
    if (!self.jsonURL || !self.logURL || self.presentedViewController) return;
    UIActivityViewController *sheet = [[UIActivityViewController alloc]
        initWithActivityItems:@[self.jsonURL, self.logURL] applicationActivities:nil];
    sheet.popoverPresentationController.sourceView = self.shareButton;
    sheet.popoverPresentationController.sourceRect = self.shareButton.bounds;
    [self presentViewController:sheet animated:YES completion:nil];
}
@end

@interface NifSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation NifSceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [NifViewController new];
    [self.window makeKeyAndVisible];
}
@end
@interface NifAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation NifAppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options { return YES; }
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(NifAppDelegate.class)); }
}
