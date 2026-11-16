#import <UIKit/UIKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <dispatch/dispatch.h>
#import <QuartzCore/CAMetalLayer.h>
#import <GameController/GameController.h>
#include <TargetConditionals.h>
#include <sys/utsname.h>
#include <mach/mach.h>
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
#include "InputProfile.hpp"
#include "OSGScene.hpp"
#include "GLDebugCapture.hpp"
#include "G4Expected.hpp"
#include <CommonCrypto/CommonDigest.h>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace G4 {
bool deviceContextCurrent(){
    return eglGetCurrentContext()!=EGL_NO_CONTEXT&&eglGetCurrentDisplay()!=EGL_NO_DISPLAY;
}
}

static NSMutableDictionary *Evidence;
static NSMutableDictionary *StartupEvidence;
static std::mutex DiagnosticFileMutex;
static std::atomic<unsigned> DiagnosticFileErrors{0};
static unsigned long long SampledFootprintPeak=0;
static NSString *Text(const char* value) { return value ? [NSString stringWithUTF8String:value] : @"<null>"; }
static void Check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
static NSString *Documents(NSString* name) {
    return [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject stringByAppendingPathComponent:name];
}
// Caller serializes with DiagnosticFileMutex. This function never calls Log,
// OSG or GL; it is also safe to use while logging an initialization failure.
static void WriteJSONUnlocked(NSDictionary* value,NSString* name) {
    NSError* error=nil;
    NSData* data=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted|NSJSONWritingSortedKeys error:&error];
    if(!data||![data writeToFile:Documents(name) options:NSDataWritingAtomic error:&error]){
        ++DiagnosticFileErrors;NSLog(@"G4 diagnostic export failed (%@): %@",name,error);
    }
}
static void Log(NSString* message,NSString* startupSession=nil) {
    std::lock_guard lock(DiagnosticFileMutex);
    @autoreleasepool { @try {
    NSString* stage=[message hasPrefix:@"G4 startup "]?[message substringFromIndex:11]:nil;
    if([message hasPrefix:@"Identity: "])stage=@"renderer.identity.complete";
    if([message hasPrefix:@"KHR_debug registered:"])stage=@"renderer.khr-debug.registered";
    if(startupSession&&![StartupEvidence[@"session_id"] isEqualToString:startupSession])stage=nil;
    if(StartupEvidence&&stage){
        const unsigned long long sequence=[StartupEvidence[@"sequence"] unsignedLongLongValue]+1;
        task_vm_info_data_t memory={};mach_msg_type_number_t size=TASK_VM_INFO_COUNT;
        const bool measured=task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&memory,&size)==KERN_SUCCESS&&size>=TASK_VM_INFO_REV1_COUNT;
        NSDictionary* event=@{@"sequence":@(sequence),@"stage":stage,
            @"main_thread":@(NSThread.isMainThread),@"uptime_seconds":@(NSProcessInfo.processInfo.systemUptime),
            @"physical_footprint_bytes":measured?@(memory.phys_footprint):(id)NSNull.null};
        NSMutableArray* events=[StartupEvidence[@"events"] mutableCopy];
        [events addObject:event];
        if(events.count>128){[events removeObjectAtIndex:0];StartupEvidence[@"history_truncated"]=@YES;}
        StartupEvidence[@"sequence"]=@(sequence);StartupEvidence[@"last_checkpoint"]=event;
        StartupEvidence[@"events"]=events;
        WriteJSONUnlocked(StartupEvidence,@"g4-startup.json");
    }
    NSString* line = [NSString stringWithFormat:@"%@ %@%@\n", [NSDate date], message,
        startupSession?[NSString stringWithFormat:@" [session %@]",startupSession]:@""];
    NSLog(@"%@", message);
    NSFileHandle* file = [NSFileHandle fileHandleForWritingAtPath:Documents(@"g4-render.log")];
    if (!file) {if(![line writeToFile:Documents(@"g4-render.log") atomically:YES encoding:NSUTF8StringEncoding error:nil])++DiagnosticFileErrors;}
    else { [file seekToEndOfFile]; [file writeData:[line dataUsingEncoding:NSUTF8StringEncoding]]; [file closeFile]; }
    } @catch(NSException* exception) { (void)exception;++DiagnosticFileErrors; } }
}
static void StartupCheckpoint(const char* stage,NSString* session=nil) {Log([@"G4 startup " stringByAppendingString:Text(stage)],session);}
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
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,hash);
    NSMutableString* value=[NSMutableString string];for(auto byte:hash)[value appendFormat:@"%02x",unsigned(byte)];return value;
}
static std::string FileSHA(const std::filesystem::path& path) {
    Check(std::filesystem::is_regular_file(std::filesystem::symlink_status(path)), "Missing/nonregular asset");
    std::ifstream stream(path,std::ios::binary); CC_SHA256_CTX ctx; CC_SHA256_Init(&ctx);
    char block[65536]; while(stream.read(block,sizeof(block)) || stream.gcount()) CC_SHA256_Update(&ctx,block,(CC_LONG)stream.gcount());
    Check(stream.eof(), "Asset read failure"); unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(hash,&ctx);
    std::ostringstream out;for(auto byte:hash)out<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(byte);return out.str();
}
static std::shared_ptr<G4::Session> PrepareWorld(NSMutableDictionary* report,NSString* startupSession) {
    Check(!NSThread.isMainThread,"World indexing, hashing and loading must stay off the main thread");
    const auto start=std::chrono::steady_clock::now();
    StartupCheckpoint("prepare.provenance.begin",startupSession);
    NSData* build=Read([NSBundle.mainBundle.resourceURL URLByAppendingPathComponent:@"g4-build.json"]);
    Check([Digest(build) isEqualToString:Text(G4Expected::SHA)],"G4 provenance changed");
    report[@"build"]=[NSJSONSerialization JSONObjectWithData:build options:0 error:nil];
    StartupCheckpoint("prepare.provenance.complete",startupSession);
    NSURL* directory=[NSURL fileURLWithPath:Documents(@"Model") isDirectory:YES];
    const auto path=std::filesystem::path(directory.fileSystemRepresentation);
    G4::InputProfile profile;
    NSURL* profileURL=[directory URLByAppendingPathComponent:@"world-profile.json"];
    NSDictionary* description=nil;
    if([profileURL checkResourceIsReachableAndReturnError:nil]){
        description=[NSJSONSerialization JSONObjectWithData:Read(profileURL) options:0 error:nil];
        Check([description isKindOfClass:NSDictionary.class]&&[description[@"schema_version"] isEqual:@1],"Invalid private world profile");
        NSSet* keys=[NSSet setWithArray:description.allKeys];
        Check([keys isEqualToSet:[NSSet setWithArray:@[@"schema_version",@"content",@"archives",@"loose_directories",@"files"]]],"Unexpected world profile fields");
        auto names=[](id value){
            Check([value isKindOfClass:NSArray.class],"Private profile requires ordered arrays");
            std::vector<std::string> result;for(id item in (NSArray*)value){
                Check([item isKindOfClass:NSString.class]&&[(NSString*)item length]>0,"Invalid private profile name");result.emplace_back([(NSString*)item UTF8String]);
            }return result;
        };
        profile.content=names(description[@"content"]);profile.archives=names(description[@"archives"]);
        profile.looseDirectories=names(description[@"loose_directories"]);
    }else{
        description=[NSJSONSerialization JSONObjectWithData:Read([directory URLByAppendingPathComponent:@"manifest.json"]) options:0 error:nil];
        Check([description isKindOfClass:NSDictionary.class]&&[description[@"schema_version"] isEqual:@1],"Invalid original private manifest");
    }
    NSDictionary* files=description[@"files"];Check([files isKindOfClass:NSDictionary.class],"Missing private file hashes");
    for(id name in files){
        Check([name isKindOfClass:NSString.class]&&[files[name] isKindOfClass:NSString.class],"Invalid private hash entry");
        profile.files.emplace([(NSString*)name UTF8String],[(NSString*)files[name] UTF8String]);
    }
    StartupCheckpoint("prepare.private-hashes.before.begin",startupSession);
    profile.verify(path,FileSHA);
    StartupCheckpoint("prepare.private-hashes.before.complete",startupSession);
    {std::lock_guard capabilities(G4::CapabilityRegistryMutex);Check(SceneUtil::glExtensionsReady(),"Initialize genuine GL capabilities before image loading");}
    const auto loadStart=std::chrono::steady_clock::now();
    std::shared_ptr<G4::Session> session;
    {std::lock_guard registry(G4::CapabilityRegistryMutex);
        StartupCheckpoint("prepare.world-index.begin",startupSession);
        auto index=std::make_unique<G4::WorldIndex>(profile.contentPaths(path));
        StartupCheckpoint("prepare.world-index.complete",startupSession);
        StartupCheckpoint("prepare.resources.begin",startupSession);
        auto resources=std::make_unique<G4::Resources>(profile.resourcePaths(path),std::filesystem::path([NSBundle.mainBundle.resourcePath UTF8String])/"Shaders");
        StartupCheckpoint("prepare.resources.complete",startupSession);
        StartupCheckpoint("prepare.session.begin",startupSession);
        session=std::make_shared<G4::Session>(std::move(index),std::move(resources));
        StartupCheckpoint("prepare.session.complete",startupSession);
    }
    report[@"scene_load_wall_ms"]=@(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-loadStart).count());
    StartupCheckpoint("prepare.private-hashes.after.begin",startupSession);
    profile.verify(path,FileSHA);
    StartupCheckpoint("prepare.private-hashes.after.complete",startupSession);
    report[@"private_assets"]=files;report[@"inputs_unchanged"]=@YES;
    report[@"input_verification_scope"]=@"SHA-256 before/after initial preparation; game inputs opened read-only";
    report[@"gl_capabilities_before_images"]=@YES;report[@"parser_geometry_ready"]=@YES;
    report[@"content_files"]=@(profile.content.size());report[@"archive_files"]=@(profile.archives.size());
    report[@"loose_directories"]=@(profile.looseDirectories.size());
    report[@"architecture"]=@"Genuine ResourceSystem/SceneManager/NifOsg, Store specializations, TerrainGrid and BulletShapeManager";
    report[@"lighting_profile"]=@"Genuine upstream GLSL arithmetic and clear-day defaults; dynamic weather/sky UNIMPLEMENTED";
    report[@"full_engine_compatibility"]=@NO;report[@"swimming_implemented"]=@NO;
    report[@"startup_total_wall_ms"]=@(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
    return session;
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
    std::shared_ptr<G4::Session> prepared;
    bool loading,sceneActive,preparationStarted;
    unsigned long long swaps;
    bool clearOnly, previousY, previousA, previousX, previousB, buttonsPrimed, diagnostics;
    double previousTick,frameTotal,frameMax;unsigned long long frameSamples,slowFrames;
    __weak GCController* previousController;
}
@property(nonatomic, strong) CADisplayLink* displayLink;
@property(nonatomic, strong) UILabel* overlay;
@property(nonatomic, copy) NSString* failure;
- (void)activate;
- (void)deactivate;
- (void)toggleDiagnostics;
- (void)resetCamera;
- (void)beginPreparation;
- (void)exportResults;
@end
@implementation G1BViewController
- (BOOL)prefersStatusBarHidden {return YES;}
- (BOOL)prefersHomeIndicatorAutoHidden {return YES;}
- (void)loadView { self.view = [[MetalView alloc] init]; }
- (void)viewDidLoad {
    [super viewDidLoad];
    self.failure = @"";diagnostics=false;
    UITapGestureRecognizer* statusTap=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(toggleDiagnostics)];
    [self.view addGestureRecognizer:statusTap];
    UITapGestureRecognizer* reset=[[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(resetCamera)];reset.numberOfTapsRequired=2;[self.view addGestureRecognizer:reset];[statusTap requireGestureRecognizerToFail:reset];
    Evidence = [@{@"session_id": NSUUID.UUID.UUIDString, @"scope": @"G4 original Seyda Neen exterior",
        @"source_commit":Text(G4Expected::Commit),@"build_metadata_sha256":Text(G4Expected::SHA),
        @"loading_state":@"awaiting-renderer",@"parser_geometry_ready":@NO,
        @"physical_rendering_acceptance": @"UNVERIFIED: independent screenshot/export review required",
        @"gpu_completion": NSNull.null, @"lifecycle_acceptance": NSNull.null,
        @"device_system": UIDevice.currentDevice.systemVersion} mutableCopy];
    struct utsname hardware;
    if (uname(&hardware) == 0) Evidence[@"device_machine"] = Text(hardware.machine);
    Evidence[@"started_utc"] = [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]];
    {std::lock_guard lock(DiagnosticFileMutex);
        StartupEvidence=[@{@"session_id":Evidence[@"session_id"],@"source_commit":Text(G4Expected::Commit),
            @"build_metadata_sha256":Text(G4Expected::SHA),
            @"started_utc":Evidence[@"started_utc"],@"device_system":Evidence[@"device_system"],
            @"physical_rendering_acceptance":@"UNVERIFIED",@"events":@[],@"sequence":@0} mutableCopy];}
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
    Log([NSString stringWithFormat:@"New G4 session %@; source %s; physical rendering acceptance remains unverified",
        Evidence[@"session_id"], G4Expected::Commit]);
    StartupCheckpoint("view.ready");
    [self exportResults]; // Persist a truthful empty snapshot BEFORE any GL/bootstrap call.
    StartupCheckpoint("initial-evidence.attempted");
}
- (void)beginPreparation {
    StartupCheckpoint("prepare.dispatch.begin");
    loading=true;Evidence[@"loading_state"]=@"hashing-and-decoding";
    [self exportResults];
    NSMutableDictionary* session=Evidence;
    NSString* startupSession=Evidence[@"session_id"]; // Immutable token, captured before dispatch.
    NSMutableDictionary* report=[NSMutableDictionary dictionary];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0), ^{
        @autoreleasepool {
            StartupCheckpoint("prepare.worker.begin",startupSession);
            std::shared_ptr<G4::Session> result;
            NSString* failure=nil;
            @try {try { result=PrepareWorld(report,startupSession); }
            catch(const std::exception& error){failure=Text(error.what()) ?: @"G4 world preparation failed (non-UTF8 diagnostic)";}
            }@catch(NSException* exception){failure=[NSString stringWithFormat:@"G4 preparation Objective-C exception %@: %@",exception.name,exception.reason];}
            StartupCheckpoint(failure?"prepare.worker.failed":"prepare.worker.complete",startupSession);
            dispatch_async(dispatch_get_main_queue(), ^{
                // A disconnected old scene must not overwrite a newer session.
                if(Evidence!=session)return;
                StartupCheckpoint("prepare.completion.main");
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
    StartupCheckpoint("prepare.dispatch.complete");
}
- (void)exportResults {
    if (!Evidence) return;
    if (renderer) Evidence[@"runtime_identity"] = renderer->identity;
    Evidence[@"failure"] = self.failure ?: @"";
    NSString* worldError=@"";
    if(renderer&&renderer->osgScene&&renderer->osgScene->ready()){
        const auto& world=renderer->osgScene->session();worldError=Text(world.lastError.c_str());
        Evidence[@"world_loads"]=@(world.loads);Evidence[@"door_transitions"]=@(world.transitions);
        Evidence[@"failed_world_loads"]=@(world.failedLoads);Evidence[@"world_loading"]=@(world.loading());
        Evidence[@"last_world_preparation_ms"]=@(world.lastPreparationMs);
        Evidence[@"last_world_commit_ms"]=@(world.lastCommitMs);Evidence[@"max_world_commit_ms"]=@(world.maxCommitMs);
        Evidence[@"last_device_program_acceptance_ms"]=@(world.lastAcceptanceMs);
        Evidence[@"last_world_request_to_commit_ms"]=@(world.lastLoadLatencyMs);
        Evidence[@"peak_resident_neighborhood_cells"]=@(world.peakResidentCells);
        Evidence[@"peak_resident_model_instances"]=@(world.peakResidentInstances);
        Evidence[@"active_neighborhoods"]=@1;Evidence[@"pending_scene_neighborhoods"]=@(world.loading()?1:0);
        Evidence[@"cache_maintenance_runs"]=@(world.maintenanceRuns);Evidence[@"cache_maintenance_failures"]=@(world.maintenanceFailures);
        Evidence[@"cache_clear_requests"]=@(world.cacheClears);Evidence[@"last_cache_maintenance_ms"]=@(world.lastMaintenanceMs);
        Evidence[@"cache_reference_time"]=@(world.lastCacheReferenceTime);
        Evidence[@"cache_reference_clock"]=@"OSG FrameStamp referenceTime; independent of animation simulationTime";
        Evidence[@"cache_maintenance_error"]=Text(world.lastMaintenanceError.c_str());
        NSMutableDictionary* caches=[NSMutableDictionary dictionary];
        for(const auto& [key,value]:world.cacheStats)caches[Text(key.c_str())]=@(value);
        Evidence[@"resource_cache_stats"]=caches;
        Evidence[@"terrain_prepared_passes"]=@(world.area().terrainPasses);
        Evidence[@"prepared_drawables"]=@(world.area().drawables);Evidence[@"prepared_programs"]=@(world.area().programs);
        Evidence[@"terrain_pass_count_scope"]=@"Prepared inventory, not measured visible draw calls or GPU cost";
        Evidence[@"active_cells"]=@(world.area().cells);Evidence[@"references"]=@(world.area().references);
        Evidence[@"model_instances"]=@(world.area().instances);Evidence[@"collision_objects"]=@(world.area().physics->objectCount());
        Evidence[@"interior"]=Text(world.area().location.interior.c_str());
        Evidence[@"cell_x"]=@(world.area().location.x);Evidence[@"cell_y"]=@(world.area().location.y);
        Evidence[@"water_levels_recorded"]=@(world.area().waterLevels.size());
        NSMutableDictionary* excluded=[NSMutableDictionary dictionary];for(const auto& [name,count]:world.area().exclusions)excluded[Text(name.c_str())]=@(count);
        Evidence[@"exclusions"]=excluded;
    }
    Evidence[@"scene_error"] = renderer && renderer->shaderError.length ? renderer->shaderError : (self.failure.length?self.failure:worldError);
    Evidence[@"successful_egl_swaps"] = @(swaps);
    Evidence[@"clear_only"] = @(clearOnly);
    if(renderer&&renderer->osgScene&&renderer->osgScene->ready()){const auto& nav=renderer->osgScene->navigation();
        Evidence[@"camera"]=@{@"x":@(nav.eye.x()),@"y":@(nav.eye.y()),@"z":@(nav.eye.z()),@"yaw":@(nav.yaw),@"pitch":@(nav.pitch),@"collision_enabled":@YES};}
    Evidence[@"osg_frames"] = @(renderer && renderer->osgScene ? renderer->osgScene->frames : 0);
    Evidence[@"shader_linked"] = @(renderer && renderer->osgScene && renderer->osgScene->shaderLinked);
    Evidence[@"shader_accepted_world_load"]=@(renderer&&renderer->osgScene?renderer->osgScene->shaderAcceptedLoad():0);
    Evidence[@"background_busy_clear_frames"]=@(renderer&&renderer->osgScene?renderer->osgScene->backgroundBusyFrames:0);
    Evidence[@"osg_notification_warnings"]=@(renderer&&renderer->osgScene?renderer->osgScene->warnings():0);
    Evidence[@"logging_callback_errors"]=@(renderer&&renderer->osgScene?renderer->osgScene->loggingErrors():0);
    Evidence[@"logging_file_errors"]=@(DiagnosticFileErrors.load());
    Evidence[@"app_polled_gl_errors"] = @(renderer ? renderer->errors : 0);
    Evidence[@"actual_display_fps"] = NSNull.null;
    Evidence[@"display_callback_timing"]=@{@"samples":@(frameSamples),@"mean_ms":@(frameSamples?frameTotal/frameSamples:0),@"max_ms":@(frameMax),@"over_50ms":@(slowFrames),@"scope":@"CADisplayLink callback intervals, not measured display/GPU FPS"};
    Evidence[@"thermal_state"]=@(NSProcessInfo.processInfo.thermalState);
    task_vm_info_data_t vm={};mach_msg_type_number_t vmCount=TASK_VM_INFO_COUNT;
    const bool vmOK=task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&vm,&vmCount)==KERN_SUCCESS&&vmCount>=TASK_VM_INFO_REV1_COUNT;
    Evidence[@"physical_footprint_bytes"]=vmOK?@(vm.phys_footprint):(id)NSNull.null;
    if(vmOK)SampledFootprintPeak=std::max(SampledFootprintPeak,(unsigned long long)vm.phys_footprint);
    Evidence[@"sampled_peak_physical_footprint_bytes"]=@(SampledFootprintPeak);
    Evidence[@"peak_physical_footprint_bytes"]=NSNull.null;
#if defined(TASK_VM_INFO_REV3_COUNT)
    if(vmOK&&vmCount>=TASK_VM_INFO_REV3_COUNT&&vm.ledger_phys_footprint_peak>0)
        Evidence[@"peak_physical_footprint_bytes"]=@(vm.ledger_phys_footprint_peak);
#endif
    Evidence[@"peak_footprint_scope"]=@"Kernel task ledger lifetime peak where available; sampled peak is separately labelled";
    if(renderer&&renderer->osgScene&&renderer->osgScene->ready()){Evidence[@"grounded"]=@(renderer->osgScene->grounded());Evidence[@"physics_steps"]=@(renderer->osgScene->physicsSteps());Evidence[@"physics_dropped_seconds"]=@(renderer->osgScene->droppedPhysicsSeconds());Evidence[@"last_osg_traversal_wall_ms"]=@(renderer->osgScene->traversalWallMs);}
    bool hasPad=false;for(GCController* c in GCController.controllers)if(c.extendedGamepad){hasPad=true;break;}
    self.overlay.hidden=!diagnostics && hasPad && !self.failure.length && !(renderer&&renderer->shaderError.length) && !worldError.length;
    self.overlay.text = [NSString stringWithFormat:@"G4 genuine world integration | session %@\nParser/geometry: %@ | shader linked: %@\nOSG frames: %@ | EGL swaps: %@\nPhysical acceptance: UNVERIFIED\n%@",
        [Evidence[@"session_id"] substringToIndex:8], Evidence[@"parser_geometry_ready"] ?: @NO, Evidence[@"shader_linked"], Evidence[@"osg_frames"],
        Evidence[@"successful_egl_swaps"], self.failure.length ? self.failure :
            (worldError.length ? worldError : renderer && renderer->shaderError.length ? renderer->shaderError : @"Controller: left stick move, right stick look; A jump; X door; B recovery; Y status; double tap recovery.")];
    if(loading){self.overlay.hidden=NO;}
    if(loading)self.overlay.text=@"Loading original Seyda Neen...\nControls activate after loading completes.";
    {std::lock_guard lock(DiagnosticFileMutex);
        @try{WriteJSONUnlocked(Evidence,@"g4-render.json");}
        @catch(NSException* exception){++DiagnosticFileErrors;NSLog(@"G4 render JSON exception: %@",exception);}}
}
- (void)activate {
    [self view];[self.view layoutIfNeeded];sceneActive=true;
    if(self.failure.length)return;
    @try {try {
        if(!renderer){StartupCheckpoint("renderer.allocate.begin");renderer=std::make_unique<Renderer>();
            StartupCheckpoint("renderer.allocate.complete");StartupCheckpoint("renderer.start.begin");
            renderer->start((CAMetalLayer*)self.view.layer);StartupCheckpoint("renderer.start.returned");
            Check(renderer->sceneAvailable,"G4 EGL/OSG bootstrap failed");StartupCheckpoint("renderer.bootstrap.complete");}
        else if(!self.displayLink)renderer->resume();
        if(prepared){StartupCheckpoint("scene.attach.begin");renderer->osgScene->attach(prepared);prepared.reset();buttonsPrimed=false;StartupCheckpoint("scene.attach.complete");}
        if(!preparationStarted){preparationStarted=true;[self beginPreparation];}
        if(self.displayLink)return;
        buttonsPrimed=false;
        StartupCheckpoint("display-link.begin");
        self.displayLink=[CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        self.displayLink.preferredFrameRateRange=CAFrameRateRangeMake(30,60,60);
        [self.displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
        UIApplication.sharedApplication.idleTimerDisabled=YES;
        StartupCheckpoint("display-link.complete");
    }catch(const std::exception& error){self.failure=Text(error.what())?:@"G4 activation failed (non-UTF8 diagnostic)";Log(self.failure);StartupCheckpoint("activate.cpp-exception");}
    }@catch(NSException* exception){self.failure=[NSString stringWithFormat:@"G4 activation Objective-C exception %@: %@",exception.name,exception.reason];Log(self.failure);StartupCheckpoint("activate.objc-exception");}
    [self exportResults];
}
- (void)deactivate {
    sceneActive=false;previousTick=0;
    if(renderer&&renderer->osgScene)renderer->osgScene->suspend();
    [self.displayLink invalidate]; self.displayLink = nil;
    UIApplication.sharedApplication.idleTimerDisabled = NO;
    try { if (renderer) renderer->pause(); }
    catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); }
    buttonsPrimed = false;
    [self exportResults];
}
- (void)toggleDiagnostics {diagnostics=!diagnostics;[self exportResults];}
- (void)resetCamera {if(renderer&&renderer->osgScene&&renderer->osgScene->ready())renderer->osgScene->session().reset();}
- (void)tick:(CADisplayLink*)link {
    const double now=link.timestamp;
    if(previousTick>0){double ms=(now-previousTick)*1000;if(ms>0&&ms<60000){frameTotal+=ms;frameMax=std::max(frameMax,ms);++frameSamples;if(ms>50)++slowFrames;}}
    previousTick=now;
    GCController* controller = nil;
    for (GCController* candidate in GCController.controllers) if (candidate.extendedGamepad) { controller = candidate; break; }
    const bool y = controller.extendedGamepad.buttonY.isPressed;
    const bool a = controller.extendedGamepad.buttonA.isPressed;
    const bool x = controller.extendedGamepad.buttonX.isPressed,b=controller.extendedGamepad.buttonB.isPressed;
    if(renderer&&renderer->osgScene&&renderer->osgScene->ready()){
        auto& nav=renderer->osgScene->navigation();GCExtendedGamepad* pad=controller.extendedGamepad;
        nav.strafe=pad?pad.leftThumbstick.xAxis.value:0;nav.forward=pad?pad.leftThumbstick.yAxis.value:0;
        nav.vertical=0; // Grounding/gravity cannot be bypassed by triggers.
        nav.lookX=pad?pad.rightThumbstick.xAxis.value:0;nav.lookY=pad?pad.rightThumbstick.yAxis.value:0;
        if(buttonsPrimed&&controller==previousController){
            if(a&&!previousA)nav.jump();
            if(x&&!previousX)renderer->osgScene->session().activate();
            if(b&&!previousB)renderer->osgScene->session().reset();
        }
    }
    if (controller != previousController || !buttonsPrimed) { previousController = controller; previousY = y;previousA=a;previousX=x;previousB=b; buttonsPrimed = true; }
    else { if (y && !previousY) diagnostics = !diagnostics; previousY = y;previousA=a;previousX=x;previousB=b; }
    if (renderer && !renderer->sceneAvailable) clearOnly = true;
    try { if (renderer && renderer->draw(CACurrentMediaTime(), clearOnly)) ++swaps; }
    catch (const std::exception& error) { self.failure = Text(error.what()); Log(self.failure); [self deactivate]; return; }
    if (swaps % 30 == 0) [self exportResults];
}
- (void)didReceiveMemoryWarning {
    [super didReceiveMemoryWarning];
    if(renderer&&renderer->osgScene&&renderer->osgScene->ready())renderer->osgScene->session().memoryWarning();
    Evidence[@"memory_warning_count"]=@([Evidence[@"memory_warning_count"] unsignedLongLongValue]+1);
    [self exportResults];
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
