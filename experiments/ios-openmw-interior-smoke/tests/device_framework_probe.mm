// Compile/link only. Never execute this iPhoneOS product on the CI host.
#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#import <dispatch/dispatch.h>
#include <CommonCrypto/CommonDigest.h>
int main() {
    @autoreleasepool {
        CGPoint origin=CGPointZero; // Require the actual CoreGraphics data symbol.
        NSBundle* bundle=NSBundle.mainBundle;
        UIApplication* app=UIApplication.sharedApplication;
        CAMetalLayer* layer=[CAMetalLayer layer];
        NSArray* controllers=GCController.controllers;
        id<MTLDevice> device=MTLCreateSystemDefaultDevice();
        unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256("",0,digest);
        dispatch_async(dispatch_get_main_queue(), ^{(void)CGRectGetWidth(layer.bounds);});
        return int(origin.x)+int(CFGetTypeID(CFSTR("G2 framework probe")))
            +int(bundle!=nil)+int(app!=nil)+int(device!=nil)+int(controllers.count)+int(digest[0]);
    }
}
