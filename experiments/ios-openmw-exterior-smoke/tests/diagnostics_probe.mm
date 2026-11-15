// SDK-only compile/link. Do not execute this device binary on the CI host.
#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#include <mach/mach.h>
int main(){@autoreleasepool{
    task_vm_info_data_t vm={};mach_msg_type_number_t count=TASK_VM_INFO_COUNT;
    kern_return_t status=task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&vm,&count);
    NSProcessInfoThermalState thermal=NSProcessInfo.processInfo.thermalState;
    GCController* controller=GCController.controllers.firstObject;
    GCExtendedGamepad* pad=controller.extendedGamepad;
    return int(status==KERN_SUCCESS)+int(vm.phys_footprint>0)+int(thermal)+int(pad.buttonA.isPressed)+int(CGPointZero.x);
}}
