// SPDX-License-Identifier: GPL-3.0-or-later
#import "Capabilities.hpp"
#import <QuartzCore/CAMetalLayer.h>

#include <vulkan/vulkan.h>
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
    void check(VkResult result, const char* operation)
    {
        if (result != VK_SUCCESS)
            throw std::runtime_error(std::string(operation) + " returned VkResult " + std::to_string(result));
    }

    NSString* string(const char* text)
    {
        return text ? ([NSString stringWithUTF8String:text] ?: @"<invalid UTF-8>") : @"";
    }
    NSArray* version(uint32_t value)
    {
        return @[@(VK_VERSION_MAJOR(value)), @(VK_VERSION_MINOR(value)), @(VK_VERSION_PATCH(value))];
    }
    NSString* hex(const uint8_t* data, size_t size)
    {
        NSMutableString* result = [NSMutableString stringWithCapacity:size * 2];
        for (size_t i = 0; i < size; ++i) [result appendFormat:@"%02x", data[i]];
        return result;
    }

    template<class T, class Query> std::vector<T> enumerate(Query query, const char* operation)
    {
        for (int attempt = 0; attempt < 4; ++attempt)
        {
            uint32_t count = 0;
            check(query(&count, static_cast<T*>(nullptr)), operation);
            std::vector<T> values(count);
            const VkResult result = query(&count, values.data());
            if (result == VK_INCOMPLETE) continue;
            check(result, operation);
            values.resize(count);
            return values;
        }
        throw std::runtime_error(std::string(operation) + " remained VK_INCOMPLETE");
    }
    bool has(const std::vector<VkExtensionProperties>& extensions, const char* name)
    {
        return std::any_of(extensions.begin(), extensions.end(), [&](const auto& extension) {
            return std::string(extension.extensionName) == name;
        });
    }
    NSDictionary* extensionMap(const std::vector<VkExtensionProperties>& extensions)
    {
        NSMutableDictionary* result = [NSMutableDictionary dictionary];
        for (const auto& extension : extensions) result[string(extension.extensionName)] = @(extension.specVersion);
        return result;
    }

    struct Context
    {
        VkInstance instance = VK_NULL_HANDLE;
        VkSurfaceKHR surface = VK_NULL_HANDLE;
        VkDebugUtilsMessengerEXT messenger = VK_NULL_HANDLE;
        PFN_vkDestroyDebugUtilsMessengerEXT destroyMessenger = nullptr;
        std::atomic<uint64_t> warnings{0}, errors{0};
        NSMutableArray* messages = [NSMutableArray array];
        void close()
        {
            if (surface) vkDestroySurfaceKHR(instance, surface, nullptr);
            if (messenger) destroyMessenger(instance, messenger, nullptr);
            if (instance) vkDestroyInstance(instance, nullptr);
            surface = VK_NULL_HANDLE; messenger = VK_NULL_HANDLE; instance = VK_NULL_HANDLE;
        }
        ~Context() { close(); }
        static VKAPI_ATTR VkBool32 VKAPI_CALL debug(VkDebugUtilsMessageSeverityFlagBitsEXT severity,
            VkDebugUtilsMessageTypeFlagsEXT type, const VkDebugUtilsMessengerCallbackDataEXT* message, void* user) noexcept
        {
            auto* context = static_cast<Context*>(user);
            if (severity & VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT) ++context->errors;
            else ++context->warnings;
            @autoreleasepool
            {
                @try
                {
                    NSDictionary* entry = @{@"severity": @(severity), @"type": @(type),
                        @"message_id": @(message ? message->messageIdNumber : 0),
                        @"message_id_name": string(message ? message->pMessageIdName : nullptr),
                        @"message": string(message ? message->pMessage : "(no message)")};
                    @synchronized (context->messages) { [context->messages addObject:entry]; }
                    NSLog(@"VULKAN QUERY DEBUG: %@", entry[@"message"]);
                }
                @catch (NSException* exception) { (void)exception; }
            }
            return VK_FALSE;
        }
    };

    // Full Vulkan 1.0 feature snapshot, not just the features enabled by the cube.
    void coreFeatures(NSMutableDictionary* output, const VkPhysicalDeviceFeatures& f)
    {
#define F(name) output[@"VkPhysicalDeviceFeatures." #name] = @(f.name != VK_FALSE)
        F(robustBufferAccess); F(fullDrawIndexUint32); F(imageCubeArray); F(independentBlend);
        F(geometryShader); F(tessellationShader); F(sampleRateShading); F(dualSrcBlend); F(logicOp);
        F(multiDrawIndirect); F(drawIndirectFirstInstance); F(depthClamp); F(depthBiasClamp);
        F(fillModeNonSolid); F(depthBounds); F(wideLines); F(largePoints); F(alphaToOne); F(multiViewport);
        F(samplerAnisotropy); F(textureCompressionETC2); F(textureCompressionASTC_LDR); F(textureCompressionBC);
        F(occlusionQueryPrecise); F(pipelineStatisticsQuery); F(vertexPipelineStoresAndAtomics);
        F(fragmentStoresAndAtomics); F(shaderTessellationAndGeometryPointSize); F(shaderImageGatherExtended);
        F(shaderStorageImageExtendedFormats); F(shaderStorageImageMultisample); F(shaderStorageImageReadWithoutFormat);
        F(shaderStorageImageWriteWithoutFormat); F(shaderUniformBufferArrayDynamicIndexing);
        F(shaderSampledImageArrayDynamicIndexing); F(shaderStorageBufferArrayDynamicIndexing);
        F(shaderStorageImageArrayDynamicIndexing); F(shaderClipDistance); F(shaderCullDistance);
        F(shaderFloat64); F(shaderInt64); F(shaderInt16); F(shaderResourceResidency); F(shaderResourceMinLod);
        F(sparseBinding); F(sparseResidencyBuffer); F(sparseResidencyImage2D); F(sparseResidencyImage3D);
        F(sparseResidency2Samples); F(sparseResidency4Samples); F(sparseResidency8Samples); F(sparseResidency16Samples);
        F(sparseResidencyAliased); F(variableMultisampleRate); F(inheritedQueries);
#undef F
    }

    void coreLimits(NSMutableDictionary* output, const VkPhysicalDeviceLimits& l)
    {
#define L(name) output[@"VkPhysicalDeviceLimits." #name] = @(l.name)
        L(maxImageDimension1D); L(maxImageDimension2D); L(maxImageDimension3D); L(maxImageDimensionCube);
        L(maxImageArrayLayers); L(maxTexelBufferElements); L(maxUniformBufferRange); L(maxStorageBufferRange);
        L(maxPushConstantsSize); L(maxMemoryAllocationCount); L(maxSamplerAllocationCount); L(bufferImageGranularity);
        L(sparseAddressSpaceSize); L(maxBoundDescriptorSets); L(maxPerStageDescriptorSamplers);
        L(maxPerStageDescriptorUniformBuffers); L(maxPerStageDescriptorStorageBuffers); L(maxPerStageDescriptorSampledImages);
        L(maxPerStageDescriptorStorageImages); L(maxPerStageDescriptorInputAttachments); L(maxPerStageResources);
        L(maxDescriptorSetSamplers); L(maxDescriptorSetUniformBuffers); L(maxDescriptorSetUniformBuffersDynamic);
        L(maxDescriptorSetStorageBuffers); L(maxDescriptorSetStorageBuffersDynamic); L(maxDescriptorSetSampledImages);
        L(maxDescriptorSetStorageImages); L(maxDescriptorSetInputAttachments); L(maxVertexInputAttributes);
        L(maxVertexInputBindings); L(maxVertexInputAttributeOffset); L(maxVertexInputBindingStride); L(maxVertexOutputComponents);
        L(maxTessellationGenerationLevel); L(maxTessellationPatchSize); L(maxTessellationControlPerVertexInputComponents);
        L(maxTessellationControlPerVertexOutputComponents); L(maxTessellationControlPerPatchOutputComponents);
        L(maxTessellationControlTotalOutputComponents); L(maxTessellationEvaluationInputComponents);
        L(maxTessellationEvaluationOutputComponents); L(maxGeometryShaderInvocations); L(maxGeometryInputComponents);
        L(maxGeometryOutputComponents); L(maxGeometryOutputVertices); L(maxGeometryTotalOutputComponents);
        L(maxFragmentInputComponents); L(maxFragmentOutputAttachments); L(maxFragmentDualSrcAttachments);
        L(maxFragmentCombinedOutputResources); L(maxComputeSharedMemorySize); L(maxComputeWorkGroupInvocations);
        L(subPixelPrecisionBits); L(subTexelPrecisionBits); L(mipmapPrecisionBits); L(maxDrawIndexedIndexValue);
        L(maxDrawIndirectCount); L(maxSamplerLodBias); L(maxSamplerAnisotropy); L(maxViewports); L(viewportSubPixelBits);
        L(minMemoryMapAlignment); L(minTexelBufferOffsetAlignment); L(minUniformBufferOffsetAlignment);
        L(minStorageBufferOffsetAlignment); L(minTexelOffset); L(maxTexelOffset); L(minTexelGatherOffset); L(maxTexelGatherOffset);
        L(minInterpolationOffset); L(maxInterpolationOffset); L(subPixelInterpolationOffsetBits); L(maxFramebufferWidth);
        L(maxFramebufferHeight); L(maxFramebufferLayers); L(framebufferColorSampleCounts); L(framebufferDepthSampleCounts);
        L(framebufferStencilSampleCounts); L(framebufferNoAttachmentsSampleCounts); L(maxColorAttachments);
        L(sampledImageColorSampleCounts); L(sampledImageIntegerSampleCounts); L(sampledImageDepthSampleCounts);
        L(sampledImageStencilSampleCounts); L(storageImageSampleCounts); L(maxSampleMaskWords); L(timestampComputeAndGraphics);
        L(timestampPeriod); L(maxClipDistances); L(maxCullDistances); L(maxCombinedClipAndCullDistances);
        L(discreteQueuePriorities); L(pointSizeGranularity); L(lineWidthGranularity); L(strictLines);
        L(standardSampleLocations); L(optimalBufferCopyOffsetAlignment); L(optimalBufferCopyRowPitchAlignment); L(nonCoherentAtomSize);
#undef L
        output[@"VkPhysicalDeviceLimits.maxComputeWorkGroupCount"] = @[@(l.maxComputeWorkGroupCount[0]), @(l.maxComputeWorkGroupCount[1]), @(l.maxComputeWorkGroupCount[2])];
        output[@"VkPhysicalDeviceLimits.maxComputeWorkGroupSize"] = @[@(l.maxComputeWorkGroupSize[0]), @(l.maxComputeWorkGroupSize[1]), @(l.maxComputeWorkGroupSize[2])];
        output[@"VkPhysicalDeviceLimits.maxViewportDimensions"] = @[@(l.maxViewportDimensions[0]), @(l.maxViewportDimensions[1])];
        output[@"VkPhysicalDeviceLimits.viewportBoundsRange"] = @[@(l.viewportBoundsRange[0]), @(l.viewportBoundsRange[1])];
        output[@"VkPhysicalDeviceLimits.pointSizeRange"] = @[@(l.pointSizeRange[0]), @(l.pointSizeRange[1])];
        output[@"VkPhysicalDeviceLimits.lineWidthRange"] = @[@(l.lineWidthRange[0]), @(l.lineWidthRange[1])];
        output[@"VkPhysicalDeviceLimits.timestampComputeAndGraphics"] = @(l.timestampComputeAndGraphics != VK_FALSE);
        output[@"VkPhysicalDeviceLimits.strictLines"] = @(l.strictLines != VK_FALSE);
        output[@"VkPhysicalDeviceLimits.standardSampleLocations"] = @(l.standardSampleLocations != VK_FALSE);
    }

    NSDictionary* features(VkPhysicalDevice device, uint32_t api, const std::vector<VkExtensionProperties>& extensions,
        NSMutableArray* queried, NSMutableArray* unknown)
    {
        NSMutableDictionary* output = [NSMutableDictionary dictionary];
        VkPhysicalDeviceFeatures2 root{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
        VkPhysicalDeviceVulkan11Features v11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES};
        VkPhysicalDeviceVulkan12Features v12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
        VkPhysicalDeviceVulkan13Features v13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
        VkPhysicalDevice16BitStorageFeatures storage16{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_16BIT_STORAGE_FEATURES};
        VkPhysicalDeviceMultiviewFeatures multiview{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MULTIVIEW_FEATURES};
        VkPhysicalDeviceVariablePointersFeatures pointers{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VARIABLE_POINTERS_FEATURES};
        VkPhysicalDeviceProtectedMemoryFeatures protectedMemory{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROTECTED_MEMORY_FEATURES};
        VkPhysicalDeviceSamplerYcbcrConversionFeatures ycbcr{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SAMPLER_YCBCR_CONVERSION_FEATURES};
        VkPhysicalDeviceShaderDrawParametersFeatures drawParameters{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_DRAW_PARAMETERS_FEATURES};
        VkPhysicalDeviceTimelineSemaphoreFeatures timeline{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TIMELINE_SEMAPHORE_FEATURES};
        VkPhysicalDeviceScalarBlockLayoutFeatures scalar{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SCALAR_BLOCK_LAYOUT_FEATURES};
        VkPhysicalDeviceImagelessFramebufferFeatures imageless{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGELESS_FRAMEBUFFER_FEATURES};
        VkPhysicalDeviceDescriptorIndexingFeatures indexing{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES};
        VkPhysicalDeviceDynamicRenderingFeatures dynamic{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DYNAMIC_RENDERING_FEATURES};
        VkPhysicalDeviceRobustness2FeaturesEXT robust{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ROBUSTNESS_2_FEATURES_EXT};
        VkPhysicalDeviceCustomBorderColorFeaturesEXT border{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_CUSTOM_BORDER_COLOR_FEATURES_EXT};
        VkPhysicalDeviceLineRasterizationFeaturesEXT lines{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_LINE_RASTERIZATION_FEATURES_EXT};
        VkPhysicalDevicePortabilitySubsetFeaturesKHR portability{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PORTABILITY_SUBSET_FEATURES_KHR};
        VkPhysicalDeviceProvokingVertexFeaturesEXT provoking{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROVOKING_VERTEX_FEATURES_EXT};
        VkPhysicalDeviceTransformFeedbackFeaturesEXT transform{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TRANSFORM_FEEDBACK_FEATURES_EXT};
        VkPhysicalDeviceDepthClipEnableFeaturesEXT depthClip{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DEPTH_CLIP_ENABLE_FEATURES_EXT};
        VkPhysicalDeviceVertexAttributeDivisorFeaturesEXT divisor{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VERTEX_ATTRIBUTE_DIVISOR_FEATURES_EXT};
        VkPhysicalDeviceBorderColorSwizzleFeaturesEXT swizzle{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_BORDER_COLOR_SWIZZLE_FEATURES_EXT};
        VkPhysicalDeviceConditionalRenderingFeaturesEXT conditional{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_CONDITIONAL_RENDERING_FEATURES_EXT};
        VkPhysicalDeviceMaintenance4Features maintenance4{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MAINTENANCE_4_FEATURES};
        VkPhysicalDeviceMaintenance5FeaturesKHR maintenance5{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MAINTENANCE_5_FEATURES_KHR};
        VkPhysicalDeviceImage2DViewOf3DFeaturesEXT image2D{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_2D_VIEW_OF_3D_FEATURES_EXT};
        VkPhysicalDeviceImageRobustnessFeatures imageRobust{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_ROBUSTNESS_FEATURES};
        VkPhysicalDevicePipelineCreationCacheControlFeatures cacheControl{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_CREATION_CACHE_CONTROL_FEATURES};
        void** tail = &root.pNext;
        const auto append = [&](auto& value, NSString* name) { *tail = &value; tail = &value.pNext; [queried addObject:name]; };
        const bool core12 = api >= VK_API_VERSION_1_2, core13 = api >= VK_API_VERSION_1_3;
        if (core12) { append(v11, @"VkPhysicalDeviceVulkan11Features"); append(v12, @"VkPhysicalDeviceVulkan12Features"); }
        else
        {
            if (api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_16bit_storage")) append(storage16, @"VkPhysicalDevice16BitStorageFeatures");
            if (api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_multiview")) append(multiview, @"VkPhysicalDeviceMultiviewFeatures");
            if (api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_variable_pointers")) append(pointers, @"VkPhysicalDeviceVariablePointersFeatures");
            if (api >= VK_API_VERSION_1_1) append(protectedMemory, @"VkPhysicalDeviceProtectedMemoryFeatures");
            if (api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_sampler_ycbcr_conversion")) append(ycbcr, @"VkPhysicalDeviceSamplerYcbcrConversionFeatures");
            if (api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_shader_draw_parameters")) append(drawParameters, @"VkPhysicalDeviceShaderDrawParametersFeatures");
            if (has(extensions, "VK_KHR_timeline_semaphore")) append(timeline, @"VkPhysicalDeviceTimelineSemaphoreFeatures");
            if (has(extensions, "VK_EXT_scalar_block_layout")) append(scalar, @"VkPhysicalDeviceScalarBlockLayoutFeatures");
            if (has(extensions, "VK_KHR_imageless_framebuffer")) append(imageless, @"VkPhysicalDeviceImagelessFramebufferFeatures");
            if (has(extensions, "VK_EXT_descriptor_indexing")) append(indexing, @"VkPhysicalDeviceDescriptorIndexingFeatures");
        }
        if (core13) append(v13, @"VkPhysicalDeviceVulkan13Features");
        else if (has(extensions, "VK_KHR_dynamic_rendering")) append(dynamic, @"VkPhysicalDeviceDynamicRenderingFeatures");
        const bool robustnessAvailable = has(extensions, "VK_EXT_robustness2") || has(extensions, "VK_KHR_robustness2");
        if (robustnessAvailable) append(robust, @"VkPhysicalDeviceRobustness2FeaturesEXT");
        if (has(extensions, "VK_EXT_custom_border_color")) append(border, @"VkPhysicalDeviceCustomBorderColorFeaturesEXT");
        const bool lineAvailable = has(extensions, "VK_EXT_line_rasterization") || has(extensions, "VK_KHR_line_rasterization");
        if (lineAvailable) append(lines, @"VkPhysicalDeviceLineRasterizationFeaturesEXT");
        if (has(extensions, "VK_KHR_portability_subset")) append(portability, @"VkPhysicalDevicePortabilitySubsetFeaturesKHR");
        if (has(extensions, "VK_EXT_provoking_vertex")) append(provoking, @"VkPhysicalDeviceProvokingVertexFeaturesEXT");
        if (has(extensions, "VK_EXT_transform_feedback")) append(transform, @"VkPhysicalDeviceTransformFeedbackFeaturesEXT");
        if (has(extensions, "VK_EXT_depth_clip_enable")) append(depthClip, @"VkPhysicalDeviceDepthClipEnableFeaturesEXT");
        const bool divisorAvailable = has(extensions, "VK_EXT_vertex_attribute_divisor") || has(extensions, "VK_KHR_vertex_attribute_divisor");
        if (divisorAvailable) append(divisor, @"VkPhysicalDeviceVertexAttributeDivisorFeaturesEXT");
        if (has(extensions, "VK_EXT_border_color_swizzle")) append(swizzle, @"VkPhysicalDeviceBorderColorSwizzleFeaturesEXT");
        if (has(extensions, "VK_EXT_conditional_rendering")) append(conditional, @"VkPhysicalDeviceConditionalRenderingFeaturesEXT");
        if (!core13 && has(extensions, "VK_KHR_maintenance4")) append(maintenance4, @"VkPhysicalDeviceMaintenance4Features");
        if (has(extensions, "VK_KHR_maintenance5")) append(maintenance5, @"VkPhysicalDeviceMaintenance5FeaturesKHR");
        if (has(extensions, "VK_EXT_image_2d_view_of_3d")) append(image2D, @"VkPhysicalDeviceImage2DViewOf3DFeaturesEXT");
        if (!core13 && has(extensions, "VK_EXT_image_robustness")) append(imageRobust, @"VkPhysicalDeviceImageRobustnessFeatures");
        if (!core13 && has(extensions, "VK_EXT_pipeline_creation_cache_control")) append(cacheControl, @"VkPhysicalDevicePipelineCreationCacheControlFeatures");
        vkGetPhysicalDeviceFeatures2(device, &root);
        coreFeatures(output, root.features);
#define B(type, name, value) output[@#type "." #name] = @((value) != VK_FALSE)
#define V11(name) B(VkPhysicalDeviceVulkan11Features, name, v11.name)
#define V12(name) B(VkPhysicalDeviceVulkan12Features, name, v12.name)
#define V13(name) B(VkPhysicalDeviceVulkan13Features, name, v13.name)
        if (core12)
        {
            V11(storageBuffer16BitAccess); V11(uniformAndStorageBuffer16BitAccess); V11(storagePushConstant16); V11(storageInputOutput16);
            V11(multiview); V11(multiviewGeometryShader); V11(multiviewTessellationShader); V11(variablePointersStorageBuffer);
            V11(variablePointers); V11(protectedMemory); V11(samplerYcbcrConversion); V11(shaderDrawParameters);
            V12(samplerMirrorClampToEdge); V12(drawIndirectCount); V12(storageBuffer8BitAccess); V12(uniformAndStorageBuffer8BitAccess);
            V12(storagePushConstant8); V12(shaderBufferInt64Atomics); V12(shaderSharedInt64Atomics); V12(shaderFloat16); V12(shaderInt8);
            V12(descriptorIndexing); V12(shaderInputAttachmentArrayDynamicIndexing); V12(shaderUniformTexelBufferArrayDynamicIndexing);
            V12(shaderStorageTexelBufferArrayDynamicIndexing); V12(shaderUniformBufferArrayNonUniformIndexing);
            V12(shaderSampledImageArrayNonUniformIndexing); V12(shaderStorageBufferArrayNonUniformIndexing);
            V12(shaderStorageImageArrayNonUniformIndexing); V12(shaderInputAttachmentArrayNonUniformIndexing);
            V12(shaderUniformTexelBufferArrayNonUniformIndexing); V12(shaderStorageTexelBufferArrayNonUniformIndexing);
            V12(descriptorBindingUniformBufferUpdateAfterBind); V12(descriptorBindingSampledImageUpdateAfterBind);
            V12(descriptorBindingStorageImageUpdateAfterBind); V12(descriptorBindingStorageBufferUpdateAfterBind);
            V12(descriptorBindingUniformTexelBufferUpdateAfterBind); V12(descriptorBindingStorageTexelBufferUpdateAfterBind);
            V12(descriptorBindingUpdateUnusedWhilePending); V12(descriptorBindingPartiallyBound);
            V12(descriptorBindingVariableDescriptorCount); V12(runtimeDescriptorArray); V12(samplerFilterMinmax); V12(scalarBlockLayout);
            V12(imagelessFramebuffer); V12(uniformBufferStandardLayout); V12(shaderSubgroupExtendedTypes);
            V12(separateDepthStencilLayouts); V12(hostQueryReset); V12(timelineSemaphore); V12(bufferDeviceAddress);
            V12(bufferDeviceAddressCaptureReplay); V12(bufferDeviceAddressMultiDevice); V12(vulkanMemoryModel);
            V12(vulkanMemoryModelDeviceScope); V12(vulkanMemoryModelAvailabilityVisibilityChains);
            V12(shaderOutputViewportIndex); V12(shaderOutputLayer); V12(subgroupBroadcastDynamicId);
        }
        if (core13)
        {
            V13(robustImageAccess); V13(inlineUniformBlock); V13(descriptorBindingInlineUniformBlockUpdateAfterBind);
            V13(pipelineCreationCacheControl); V13(privateData); V13(shaderDemoteToHelperInvocation); V13(shaderTerminateInvocation);
            V13(subgroupSizeControl); V13(computeFullSubgroups); V13(synchronization2); V13(textureCompressionASTC_HDR);
            V13(shaderZeroInitializeWorkgroupMemory); V13(dynamicRendering); V13(shaderIntegerDotProduct); V13(maintenance4);
        }
        // Aliases are populated from the legally queried aggregate, never queried twice in pNext.
        if (core12 || api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_16bit_storage"))
        {
            B(VkPhysicalDevice16BitStorageFeatures, storageBuffer16BitAccess, core12 ? v11.storageBuffer16BitAccess : storage16.storageBuffer16BitAccess);
            B(VkPhysicalDevice16BitStorageFeatures, uniformAndStorageBuffer16BitAccess, core12 ? v11.uniformAndStorageBuffer16BitAccess : storage16.uniformAndStorageBuffer16BitAccess);
            B(VkPhysicalDevice16BitStorageFeatures, storagePushConstant16, core12 ? v11.storagePushConstant16 : storage16.storagePushConstant16);
            B(VkPhysicalDevice16BitStorageFeatures, storageInputOutput16, core12 ? v11.storageInputOutput16 : storage16.storageInputOutput16);
        }
        if (core12 || api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_multiview"))
        {
            B(VkPhysicalDeviceMultiviewFeatures, multiview, core12 ? v11.multiview : multiview.multiview);
            B(VkPhysicalDeviceMultiviewFeatures, multiviewGeometryShader, core12 ? v11.multiviewGeometryShader : multiview.multiviewGeometryShader);
            B(VkPhysicalDeviceMultiviewFeatures, multiviewTessellationShader, core12 ? v11.multiviewTessellationShader : multiview.multiviewTessellationShader);
        }
        if (core12 || has(extensions, "VK_KHR_timeline_semaphore")) B(VkPhysicalDeviceTimelineSemaphoreFeatures, timelineSemaphore, core12 ? v12.timelineSemaphore : timeline.timelineSemaphore);
        if (core12 || has(extensions, "VK_EXT_scalar_block_layout")) B(VkPhysicalDeviceScalarBlockLayoutFeatures, scalarBlockLayout, core12 ? v12.scalarBlockLayout : scalar.scalarBlockLayout);
        if (core12 || has(extensions, "VK_KHR_imageless_framebuffer")) B(VkPhysicalDeviceImagelessFramebufferFeatures, imagelessFramebuffer, core12 ? v12.imagelessFramebuffer : imageless.imagelessFramebuffer);
        if (core12 || api >= VK_API_VERSION_1_1 || has(extensions, "VK_KHR_shader_draw_parameters"))
            B(VkPhysicalDeviceShaderDrawParametersFeatures, shaderDrawParameters, core12 ? v11.shaderDrawParameters : drawParameters.shaderDrawParameters);
        if (core13 || has(extensions, "VK_KHR_dynamic_rendering")) B(VkPhysicalDeviceDynamicRenderingFeatures, dynamicRendering, core13 ? v13.dynamicRendering : dynamic.dynamicRendering);
        if (core13 || has(extensions, "VK_EXT_image_robustness"))
            B(VkPhysicalDeviceImageRobustnessFeatures, robustImageAccess, core13 ? v13.robustImageAccess : imageRobust.robustImageAccess);
        if (core13 || has(extensions, "VK_EXT_pipeline_creation_cache_control"))
            B(VkPhysicalDevicePipelineCreationCacheControlFeatures, pipelineCreationCacheControl, core13 ? v13.pipelineCreationCacheControl : cacheControl.pipelineCreationCacheControl);
#define INDEX(name) B(VkPhysicalDeviceDescriptorIndexingFeatures, name, core12 ? v12.name : indexing.name)
        if (core12 || has(extensions, "VK_EXT_descriptor_indexing"))
        {
            INDEX(shaderInputAttachmentArrayDynamicIndexing); INDEX(shaderUniformTexelBufferArrayDynamicIndexing);
            INDEX(shaderStorageTexelBufferArrayDynamicIndexing); INDEX(shaderUniformBufferArrayNonUniformIndexing);
            INDEX(shaderSampledImageArrayNonUniformIndexing); INDEX(shaderStorageBufferArrayNonUniformIndexing);
            INDEX(shaderStorageImageArrayNonUniformIndexing); INDEX(shaderInputAttachmentArrayNonUniformIndexing);
            INDEX(shaderUniformTexelBufferArrayNonUniformIndexing); INDEX(shaderStorageTexelBufferArrayNonUniformIndexing);
            INDEX(descriptorBindingUniformBufferUpdateAfterBind); INDEX(descriptorBindingSampledImageUpdateAfterBind);
            INDEX(descriptorBindingStorageImageUpdateAfterBind); INDEX(descriptorBindingStorageBufferUpdateAfterBind);
            INDEX(descriptorBindingUniformTexelBufferUpdateAfterBind); INDEX(descriptorBindingStorageTexelBufferUpdateAfterBind);
            INDEX(descriptorBindingUpdateUnusedWhilePending); INDEX(descriptorBindingPartiallyBound);
            INDEX(descriptorBindingVariableDescriptorCount); INDEX(runtimeDescriptorArray);
        }
#undef INDEX
        if (robustnessAvailable)
        {
            B(VkPhysicalDeviceRobustness2FeaturesEXT, robustBufferAccess2, robust.robustBufferAccess2);
            B(VkPhysicalDeviceRobustness2FeaturesEXT, robustImageAccess2, robust.robustImageAccess2);
            B(VkPhysicalDeviceRobustness2FeaturesEXT, nullDescriptor, robust.nullDescriptor);
            B(VkPhysicalDeviceRobustness2FeaturesKHR, robustBufferAccess2, robust.robustBufferAccess2);
            B(VkPhysicalDeviceRobustness2FeaturesKHR, robustImageAccess2, robust.robustImageAccess2);
            B(VkPhysicalDeviceRobustness2FeaturesKHR, nullDescriptor, robust.nullDescriptor);
        }
        if (has(extensions, "VK_EXT_custom_border_color"))
        {
            B(VkPhysicalDeviceCustomBorderColorFeaturesEXT, customBorderColors, border.customBorderColors);
            B(VkPhysicalDeviceCustomBorderColorFeaturesEXT, customBorderColorWithoutFormat, border.customBorderColorWithoutFormat);
        }
        if (lineAvailable)
        {
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, rectangularLines, lines.rectangularLines);
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, bresenhamLines, lines.bresenhamLines);
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, smoothLines, lines.smoothLines);
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, stippledRectangularLines, lines.stippledRectangularLines);
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, stippledBresenhamLines, lines.stippledBresenhamLines);
            B(VkPhysicalDeviceLineRasterizationFeaturesEXT, stippledSmoothLines, lines.stippledSmoothLines);
        }
#define PORT(name) B(VkPhysicalDevicePortabilitySubsetFeaturesKHR, name, portability.name)
        if (has(extensions, "VK_KHR_portability_subset"))
        {
            PORT(constantAlphaColorBlendFactors); PORT(events); PORT(imageViewFormatReinterpretation);
            PORT(imageViewFormatSwizzle); PORT(imageView2DOn3DImage); PORT(multisampleArrayImage);
            PORT(mutableComparisonSamplers); PORT(pointPolygons); PORT(samplerMipLodBias);
            PORT(separateStencilMaskRef); PORT(shaderSampleRateInterpolationFunctions); PORT(tessellationIsolines);
            PORT(tessellationPointMode); PORT(triangleFans); PORT(vertexAttributeAccessBeyondStride);
        }
#undef PORT
        if (has(extensions, "VK_EXT_provoking_vertex"))
        {
            B(VkPhysicalDeviceProvokingVertexFeaturesEXT, provokingVertexLast, provoking.provokingVertexLast);
            B(VkPhysicalDeviceProvokingVertexFeaturesEXT, transformFeedbackPreservesProvokingVertex, provoking.transformFeedbackPreservesProvokingVertex);
        }
        if (has(extensions, "VK_EXT_transform_feedback"))
        {
            B(VkPhysicalDeviceTransformFeedbackFeaturesEXT, transformFeedback, transform.transformFeedback);
            B(VkPhysicalDeviceTransformFeedbackFeaturesEXT, geometryStreams, transform.geometryStreams);
        }
        if (has(extensions, "VK_EXT_depth_clip_enable")) B(VkPhysicalDeviceDepthClipEnableFeaturesEXT, depthClipEnable, depthClip.depthClipEnable);
        if (divisorAvailable)
        {
            B(VkPhysicalDeviceVertexAttributeDivisorFeaturesEXT, vertexAttributeInstanceRateDivisor, divisor.vertexAttributeInstanceRateDivisor);
            B(VkPhysicalDeviceVertexAttributeDivisorFeaturesEXT, vertexAttributeInstanceRateZeroDivisor, divisor.vertexAttributeInstanceRateZeroDivisor);
        }
        if (has(extensions, "VK_EXT_border_color_swizzle"))
        {
            B(VkPhysicalDeviceBorderColorSwizzleFeaturesEXT, borderColorSwizzle, swizzle.borderColorSwizzle);
            B(VkPhysicalDeviceBorderColorSwizzleFeaturesEXT, borderColorSwizzleFromImage, swizzle.borderColorSwizzleFromImage);
        }
        if (has(extensions, "VK_EXT_conditional_rendering"))
        {
            B(VkPhysicalDeviceConditionalRenderingFeaturesEXT, conditionalRendering, conditional.conditionalRendering);
            B(VkPhysicalDeviceConditionalRenderingFeaturesEXT, inheritedConditionalRendering, conditional.inheritedConditionalRendering);
        }
        if (core13 || has(extensions, "VK_KHR_maintenance4"))
            B(VkPhysicalDeviceMaintenance4Features, maintenance4, core13 ? v13.maintenance4 : maintenance4.maintenance4);
        if (has(extensions, "VK_KHR_maintenance5")) B(VkPhysicalDeviceMaintenance5FeaturesKHR, maintenance5, maintenance5.maintenance5);
        if (has(extensions, "VK_EXT_image_2d_view_of_3d"))
        {
            B(VkPhysicalDeviceImage2DViewOf3DFeaturesEXT, image2DViewOf3D, image2D.image2DViewOf3D);
            B(VkPhysicalDeviceImage2DViewOf3DFeaturesEXT, sampler2DViewOf3D, image2D.sampler2DViewOf3D);
        }
#undef V11
#undef V12
#undef V13
#undef B
        [unknown addObject:@"Unlisted feature fields were not legally queried by this collector; omission is not VK_FALSE. No queried feature is enabled or exercised."];
        return output;
    }

    void properties(VkPhysicalDevice device, uint32_t api, const std::vector<VkExtensionProperties>& extensions,
        NSMutableDictionary* identity, NSMutableDictionary* output, NSMutableArray* queried)
    {
        VkPhysicalDeviceProperties2 root{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
        VkPhysicalDeviceVulkan11Properties v11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_PROPERTIES};
        VkPhysicalDeviceVulkan12Properties v12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_PROPERTIES};
        VkPhysicalDeviceVulkan13Properties v13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_PROPERTIES};
        VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
        VkPhysicalDeviceIDProperties ids{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES};
        VkPhysicalDeviceSubgroupProperties subgroup{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
        VkPhysicalDevicePointClippingProperties clipping{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_POINT_CLIPPING_PROPERTIES};
        VkPhysicalDeviceMultiviewProperties multiview{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MULTIVIEW_PROPERTIES};
        VkPhysicalDeviceMaintenance3Properties maintenance3{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MAINTENANCE_3_PROPERTIES};
        VkPhysicalDevicePortabilitySubsetPropertiesKHR portability{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PORTABILITY_SUBSET_PROPERTIES_KHR};
        VkPhysicalDeviceCustomBorderColorPropertiesEXT border{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_CUSTOM_BORDER_COLOR_PROPERTIES_EXT};
        VkPhysicalDeviceRobustness2PropertiesEXT robust{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ROBUSTNESS_2_PROPERTIES_EXT};
        VkPhysicalDeviceTransformFeedbackPropertiesEXT transform{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TRANSFORM_FEEDBACK_PROPERTIES_EXT};
        VkPhysicalDeviceProvokingVertexPropertiesEXT provoking{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROVOKING_VERTEX_PROPERTIES_EXT};
        VkPhysicalDeviceVertexAttributeDivisorPropertiesEXT divisor{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VERTEX_ATTRIBUTE_DIVISOR_PROPERTIES_EXT};
        VkPhysicalDeviceMaintenance4Properties maintenance4{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MAINTENANCE_4_PROPERTIES};
        VkPhysicalDeviceMaintenance5PropertiesKHR maintenance5{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MAINTENANCE_5_PROPERTIES_KHR};
        VkPhysicalDeviceDescriptorIndexingProperties indexing{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_PROPERTIES};
        VkPhysicalDeviceSamplerFilterMinmaxProperties minmax{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SAMPLER_FILTER_MINMAX_PROPERTIES};
        void** tail = &root.pNext;
        const auto append = [&](auto& value, NSString* name) { *tail = &value; tail = &value.pNext; [queried addObject:name]; };
        const bool core12 = api >= VK_API_VERSION_1_2, core13 = api >= VK_API_VERSION_1_3;
        if (core12) { append(v11, @"VkPhysicalDeviceVulkan11Properties"); append(v12, @"VkPhysicalDeviceVulkan12Properties"); }
        else
        {
            if (api >= VK_API_VERSION_1_1)
            {
                append(ids, @"VkPhysicalDeviceIDProperties"); append(subgroup, @"VkPhysicalDeviceSubgroupProperties");
                append(clipping, @"VkPhysicalDevicePointClippingProperties"); append(multiview, @"VkPhysicalDeviceMultiviewProperties");
                append(maintenance3, @"VkPhysicalDeviceMaintenance3Properties");
            }
            if (has(extensions, "VK_KHR_driver_properties")) append(driver, @"VkPhysicalDeviceDriverProperties");
            if (has(extensions, "VK_EXT_descriptor_indexing")) append(indexing, @"VkPhysicalDeviceDescriptorIndexingProperties");
            if (has(extensions, "VK_EXT_sampler_filter_minmax")) append(minmax, @"VkPhysicalDeviceSamplerFilterMinmaxProperties");
        }
        if (core13) append(v13, @"VkPhysicalDeviceVulkan13Properties");
        if (has(extensions, "VK_KHR_portability_subset")) append(portability, @"VkPhysicalDevicePortabilitySubsetPropertiesKHR");
        if (has(extensions, "VK_EXT_custom_border_color")) append(border, @"VkPhysicalDeviceCustomBorderColorPropertiesEXT");
        const bool robustAvailable = has(extensions, "VK_EXT_robustness2") || has(extensions, "VK_KHR_robustness2");
        if (robustAvailable) append(robust, @"VkPhysicalDeviceRobustness2PropertiesEXT");
        if (has(extensions, "VK_EXT_transform_feedback")) append(transform, @"VkPhysicalDeviceTransformFeedbackPropertiesEXT");
        if (has(extensions, "VK_EXT_provoking_vertex")) append(provoking, @"VkPhysicalDeviceProvokingVertexPropertiesEXT");
        const bool divisorAvailable = has(extensions, "VK_EXT_vertex_attribute_divisor") || has(extensions, "VK_KHR_vertex_attribute_divisor");
        if (divisorAvailable) append(divisor, @"VkPhysicalDeviceVertexAttributeDivisorPropertiesEXT");
        if (!core13 && has(extensions, "VK_KHR_maintenance4")) append(maintenance4, @"VkPhysicalDeviceMaintenance4Properties");
        if (has(extensions, "VK_KHR_maintenance5")) append(maintenance5, @"VkPhysicalDeviceMaintenance5PropertiesKHR");
        vkGetPhysicalDeviceProperties2(device, &root);
        const auto& p = root.properties;
        output[@"VkPhysicalDeviceProperties.apiVersion"] = @(p.apiVersion);
        output[@"VkPhysicalDeviceProperties.vendorID"] = @(p.vendorID);
        output[@"VkPhysicalDeviceProperties.deviceID"] = @(p.deviceID);
        output[@"VkPhysicalDeviceProperties.deviceType"] = @(p.deviceType);
        identity[@"pipeline_cache_uuid"] = hex(p.pipelineCacheUUID, VK_UUID_SIZE);
        if (core12 || api >= VK_API_VERSION_1_1)
        {
            identity[@"device_uuid"] = hex(core12 ? v11.deviceUUID : ids.deviceUUID, VK_UUID_SIZE);
            identity[@"driver_uuid"] = hex(core12 ? v11.driverUUID : ids.driverUUID, VK_UUID_SIZE);
        }
        if (core12 || has(extensions, "VK_KHR_driver_properties"))
        {
            identity[@"driver_id"] = @(core12 ? v12.driverID : driver.driverID);
            identity[@"driver_name"] = string(core12 ? v12.driverName : driver.driverName);
            identity[@"driver_info"] = string(core12 ? v12.driverInfo : driver.driverInfo);
            const auto& c = core12 ? v12.conformanceVersion : driver.conformanceVersion;
            identity[@"conformance_version"] = @[@(c.major), @(c.minor), @(c.subminor), @(c.patch)];
        }
#define P(type, name, value) output[@#type "." #name] = @(value)
#define P11(name) P(VkPhysicalDeviceVulkan11Properties, name, v11.name)
#define P12(name) P(VkPhysicalDeviceVulkan12Properties, name, v12.name)
#define P13(name) P(VkPhysicalDeviceVulkan13Properties, name, v13.name)
#define PB(type, name, value) output[@#type "." #name] = @((value) != VK_FALSE)
#define PB12(name) PB(VkPhysicalDeviceVulkan12Properties, name, v12.name)
        if (core12)
        {
            P11(subgroupSize); P11(subgroupSupportedStages); P11(subgroupSupportedOperations);
            P11(subgroupQuadOperationsInAllStages); P11(pointClippingBehavior); P11(maxMultiviewViewCount);
            P11(maxMultiviewInstanceIndex); P11(protectedNoFault); P11(maxPerSetDescriptors); P11(maxMemoryAllocationSize);
            P12(denormBehaviorIndependence); P12(roundingModeIndependence);
            P12(shaderSignedZeroInfNanPreserveFloat16); P12(shaderSignedZeroInfNanPreserveFloat32); P12(shaderSignedZeroInfNanPreserveFloat64);
            P12(shaderDenormPreserveFloat16); P12(shaderDenormPreserveFloat32); P12(shaderDenormPreserveFloat64);
            P12(shaderDenormFlushToZeroFloat16); P12(shaderDenormFlushToZeroFloat32); P12(shaderDenormFlushToZeroFloat64);
            P12(shaderRoundingModeRTEFloat16); P12(shaderRoundingModeRTEFloat32); P12(shaderRoundingModeRTEFloat64);
            P12(shaderRoundingModeRTZFloat16); P12(shaderRoundingModeRTZFloat32); P12(shaderRoundingModeRTZFloat64);
            P12(maxUpdateAfterBindDescriptorsInAllPools); P12(shaderUniformBufferArrayNonUniformIndexingNative);
            P12(shaderSampledImageArrayNonUniformIndexingNative); P12(shaderStorageBufferArrayNonUniformIndexingNative);
            P12(shaderStorageImageArrayNonUniformIndexingNative); P12(shaderInputAttachmentArrayNonUniformIndexingNative);
            P12(robustBufferAccessUpdateAfterBind); P12(quadDivergentImplicitLod); P12(maxPerStageDescriptorUpdateAfterBindSamplers);
            P12(maxPerStageDescriptorUpdateAfterBindUniformBuffers); P12(maxPerStageDescriptorUpdateAfterBindStorageBuffers);
            P12(maxPerStageDescriptorUpdateAfterBindSampledImages); P12(maxPerStageDescriptorUpdateAfterBindStorageImages);
            P12(maxPerStageDescriptorUpdateAfterBindInputAttachments); P12(maxPerStageUpdateAfterBindResources);
            P12(maxDescriptorSetUpdateAfterBindSamplers); P12(maxDescriptorSetUpdateAfterBindUniformBuffers);
            P12(maxDescriptorSetUpdateAfterBindUniformBuffersDynamic); P12(maxDescriptorSetUpdateAfterBindStorageBuffers);
            P12(maxDescriptorSetUpdateAfterBindStorageBuffersDynamic); P12(maxDescriptorSetUpdateAfterBindSampledImages);
            P12(maxDescriptorSetUpdateAfterBindStorageImages); P12(maxDescriptorSetUpdateAfterBindInputAttachments);
            P12(supportedDepthResolveModes); P12(supportedStencilResolveModes); P12(independentResolveNone); P12(independentResolve);
            P12(filterMinmaxSingleComponentFormats); P12(filterMinmaxImageComponentMapping);
            P12(maxTimelineSemaphoreValueDifference); P12(framebufferIntegerColorSampleCounts);
            // VkBool32 properties must remain JSON booleans, not integer 0/1.
            PB(VkPhysicalDeviceVulkan11Properties, subgroupQuadOperationsInAllStages, v11.subgroupQuadOperationsInAllStages);
            PB(VkPhysicalDeviceVulkan11Properties, protectedNoFault, v11.protectedNoFault);
            PB12(shaderSignedZeroInfNanPreserveFloat16); PB12(shaderSignedZeroInfNanPreserveFloat32); PB12(shaderSignedZeroInfNanPreserveFloat64);
            PB12(shaderDenormPreserveFloat16); PB12(shaderDenormPreserveFloat32); PB12(shaderDenormPreserveFloat64);
            PB12(shaderDenormFlushToZeroFloat16); PB12(shaderDenormFlushToZeroFloat32); PB12(shaderDenormFlushToZeroFloat64);
            PB12(shaderRoundingModeRTEFloat16); PB12(shaderRoundingModeRTEFloat32); PB12(shaderRoundingModeRTEFloat64);
            PB12(shaderRoundingModeRTZFloat16); PB12(shaderRoundingModeRTZFloat32); PB12(shaderRoundingModeRTZFloat64);
            PB12(shaderUniformBufferArrayNonUniformIndexingNative); PB12(shaderSampledImageArrayNonUniformIndexingNative);
            PB12(shaderStorageBufferArrayNonUniformIndexingNative); PB12(shaderStorageImageArrayNonUniformIndexingNative);
            PB12(shaderInputAttachmentArrayNonUniformIndexingNative); PB12(robustBufferAccessUpdateAfterBind); PB12(quadDivergentImplicitLod);
            PB12(independentResolveNone); PB12(independentResolve); PB12(filterMinmaxSingleComponentFormats); PB12(filterMinmaxImageComponentMapping);
        }
        if (core13)
        {
            P13(minSubgroupSize); P13(maxSubgroupSize); P13(maxComputeWorkgroupSubgroups); P13(requiredSubgroupSizeStages);
            P13(maxInlineUniformBlockSize); P13(maxPerStageDescriptorInlineUniformBlocks);
            P13(maxPerStageDescriptorUpdateAfterBindInlineUniformBlocks); P13(maxDescriptorSetInlineUniformBlocks);
            P13(maxDescriptorSetUpdateAfterBindInlineUniformBlocks); P13(maxInlineUniformTotalSize);
            P13(storageTexelBufferOffsetAlignmentBytes); P13(storageTexelBufferOffsetSingleTexelAlignment);
            P13(uniformTexelBufferOffsetAlignmentBytes); P13(uniformTexelBufferOffsetSingleTexelAlignment); P13(maxBufferSize);
            P(VkPhysicalDeviceMaintenance4Properties, maxBufferSize, v13.maxBufferSize);
        }
        if (core12 || api >= VK_API_VERSION_1_1)
        {
            P(VkPhysicalDeviceSubgroupProperties, subgroupSize, core12 ? v11.subgroupSize : subgroup.subgroupSize);
            P(VkPhysicalDeviceSubgroupProperties, supportedStages, core12 ? v11.subgroupSupportedStages : subgroup.supportedStages);
            P(VkPhysicalDeviceSubgroupProperties, supportedOperations, core12 ? v11.subgroupSupportedOperations : subgroup.supportedOperations);
            PB(VkPhysicalDeviceSubgroupProperties, quadOperationsInAllStages, core12 ? v11.subgroupQuadOperationsInAllStages : subgroup.quadOperationsInAllStages);
            P(VkPhysicalDevicePointClippingProperties, pointClippingBehavior, core12 ? v11.pointClippingBehavior : clipping.pointClippingBehavior);
            P(VkPhysicalDeviceMultiviewProperties, maxMultiviewViewCount, core12 ? v11.maxMultiviewViewCount : multiview.maxMultiviewViewCount);
            P(VkPhysicalDeviceMultiviewProperties, maxMultiviewInstanceIndex, core12 ? v11.maxMultiviewInstanceIndex : multiview.maxMultiviewInstanceIndex);
            P(VkPhysicalDeviceMaintenance3Properties, maxPerSetDescriptors, core12 ? v11.maxPerSetDescriptors : maintenance3.maxPerSetDescriptors);
            P(VkPhysicalDeviceMaintenance3Properties, maxMemoryAllocationSize, core12 ? v11.maxMemoryAllocationSize : maintenance3.maxMemoryAllocationSize);
        }
        if (has(extensions, "VK_KHR_portability_subset")) P(VkPhysicalDevicePortabilitySubsetPropertiesKHR, minVertexInputBindingStrideAlignment, portability.minVertexInputBindingStrideAlignment);
        if (has(extensions, "VK_EXT_custom_border_color")) P(VkPhysicalDeviceCustomBorderColorPropertiesEXT, maxCustomBorderColorSamplers, border.maxCustomBorderColorSamplers);
        if (robustAvailable)
        {
            P(VkPhysicalDeviceRobustness2PropertiesEXT, robustStorageBufferAccessSizeAlignment, robust.robustStorageBufferAccessSizeAlignment);
            P(VkPhysicalDeviceRobustness2PropertiesEXT, robustUniformBufferAccessSizeAlignment, robust.robustUniformBufferAccessSizeAlignment);
        }
        if (has(extensions, "VK_EXT_transform_feedback"))
        {
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackStreams, transform.maxTransformFeedbackStreams);
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackBuffers, transform.maxTransformFeedbackBuffers);
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackBufferSize, transform.maxTransformFeedbackBufferSize);
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackStreamDataSize, transform.maxTransformFeedbackStreamDataSize);
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackBufferDataSize, transform.maxTransformFeedbackBufferDataSize);
            P(VkPhysicalDeviceTransformFeedbackPropertiesEXT, maxTransformFeedbackBufferDataStride, transform.maxTransformFeedbackBufferDataStride);
            PB(VkPhysicalDeviceTransformFeedbackPropertiesEXT, transformFeedbackQueries, transform.transformFeedbackQueries);
            PB(VkPhysicalDeviceTransformFeedbackPropertiesEXT, transformFeedbackStreamsLinesTriangles, transform.transformFeedbackStreamsLinesTriangles);
            PB(VkPhysicalDeviceTransformFeedbackPropertiesEXT, transformFeedbackRasterizationStreamSelect, transform.transformFeedbackRasterizationStreamSelect);
            PB(VkPhysicalDeviceTransformFeedbackPropertiesEXT, transformFeedbackDraw, transform.transformFeedbackDraw);
        }
        if (has(extensions, "VK_EXT_provoking_vertex"))
        {
            PB(VkPhysicalDeviceProvokingVertexPropertiesEXT, provokingVertexModePerPipeline, provoking.provokingVertexModePerPipeline);
            PB(VkPhysicalDeviceProvokingVertexPropertiesEXT, transformFeedbackPreservesTriangleFanProvokingVertex, provoking.transformFeedbackPreservesTriangleFanProvokingVertex);
        }
        if (divisorAvailable) P(VkPhysicalDeviceVertexAttributeDivisorPropertiesEXT, maxVertexAttribDivisor, divisor.maxVertexAttribDivisor);
        if (core12 || has(extensions, "VK_EXT_descriptor_indexing"))
            P(VkPhysicalDeviceDescriptorIndexingProperties, robustBufferAccessUpdateAfterBind,
                (core12 ? v12.robustBufferAccessUpdateAfterBind : indexing.robustBufferAccessUpdateAfterBind) != VK_FALSE);
        if (core12 || has(extensions, "VK_EXT_sampler_filter_minmax"))
        {
            P(VkPhysicalDeviceSamplerFilterMinmaxProperties, filterMinmaxSingleComponentFormats,
                (core12 ? v12.filterMinmaxSingleComponentFormats : minmax.filterMinmaxSingleComponentFormats) != VK_FALSE);
            P(VkPhysicalDeviceSamplerFilterMinmaxProperties, filterMinmaxImageComponentMapping,
                (core12 ? v12.filterMinmaxImageComponentMapping : minmax.filterMinmaxImageComponentMapping) != VK_FALSE);
        }
        if (!core13 && has(extensions, "VK_KHR_maintenance4")) P(VkPhysicalDeviceMaintenance4Properties, maxBufferSize, maintenance4.maxBufferSize);
        if (has(extensions, "VK_KHR_maintenance5"))
        {
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, earlyFragmentMultisampleCoverageAfterSampleCounting, maintenance5.earlyFragmentMultisampleCoverageAfterSampleCounting);
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, earlyFragmentSampleMaskTestBeforeSampleCounting, maintenance5.earlyFragmentSampleMaskTestBeforeSampleCounting);
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, depthStencilSwizzleOneSupport, maintenance5.depthStencilSwizzleOneSupport);
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, polygonModePointSize, maintenance5.polygonModePointSize);
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, nonStrictSinglePixelWideLinesUseParallelogram, maintenance5.nonStrictSinglePixelWideLinesUseParallelogram);
            PB(VkPhysicalDeviceMaintenance5PropertiesKHR, nonStrictWideLinesUseParallelogram, maintenance5.nonStrictWideLinesUseParallelogram);
        }
#undef P11
#undef P12
#undef P13
#undef PB12
#undef PB
#undef P
    }

    NSDictionary* formatProperties(VkPhysicalDevice device)
    {
        struct NamedFormat { const char* name; VkFormat format; };
#define FORMAT(name) {#name, name}
        const NamedFormat selected[]{
            FORMAT(VK_FORMAT_R8_UNORM), FORMAT(VK_FORMAT_R8_SNORM), FORMAT(VK_FORMAT_R8_UINT), FORMAT(VK_FORMAT_R8_SINT),
            FORMAT(VK_FORMAT_R8G8_UNORM), FORMAT(VK_FORMAT_R8G8_SNORM), FORMAT(VK_FORMAT_R8G8_UINT), FORMAT(VK_FORMAT_R8G8_SINT),
            FORMAT(VK_FORMAT_R8G8B8A8_UNORM), FORMAT(VK_FORMAT_R8G8B8A8_SRGB), FORMAT(VK_FORMAT_R8G8B8A8_SNORM),
            FORMAT(VK_FORMAT_R8G8B8A8_UINT), FORMAT(VK_FORMAT_R8G8B8A8_SINT),
            FORMAT(VK_FORMAT_B8G8R8A8_UNORM), FORMAT(VK_FORMAT_B8G8R8A8_SRGB),
            FORMAT(VK_FORMAT_A2B10G10R10_UNORM_PACK32), FORMAT(VK_FORMAT_B10G11R11_UFLOAT_PACK32),
            FORMAT(VK_FORMAT_R16_UNORM), FORMAT(VK_FORMAT_R16_SNORM), FORMAT(VK_FORMAT_R16_UINT), FORMAT(VK_FORMAT_R16_SINT), FORMAT(VK_FORMAT_R16_SFLOAT),
            FORMAT(VK_FORMAT_R16G16_UNORM), FORMAT(VK_FORMAT_R16G16_SNORM), FORMAT(VK_FORMAT_R16G16_SFLOAT), FORMAT(VK_FORMAT_R16G16B16A16_SFLOAT),
            FORMAT(VK_FORMAT_R32_UINT), FORMAT(VK_FORMAT_R32_SINT), FORMAT(VK_FORMAT_R32_SFLOAT),
            FORMAT(VK_FORMAT_R32G32_SFLOAT), FORMAT(VK_FORMAT_R32G32B32_SFLOAT), FORMAT(VK_FORMAT_R32G32B32_SINT),
            FORMAT(VK_FORMAT_R32G32B32_UINT), FORMAT(VK_FORMAT_R32G32B32A32_SFLOAT),
            FORMAT(VK_FORMAT_D16_UNORM), FORMAT(VK_FORMAT_X8_D24_UNORM_PACK32), FORMAT(VK_FORMAT_D32_SFLOAT), FORMAT(VK_FORMAT_S8_UINT),
            FORMAT(VK_FORMAT_D16_UNORM_S8_UINT), FORMAT(VK_FORMAT_D24_UNORM_S8_UINT), FORMAT(VK_FORMAT_D32_SFLOAT_S8_UINT),
            FORMAT(VK_FORMAT_BC1_RGB_UNORM_BLOCK), FORMAT(VK_FORMAT_BC1_RGB_SRGB_BLOCK),
            FORMAT(VK_FORMAT_BC1_RGBA_UNORM_BLOCK), FORMAT(VK_FORMAT_BC1_RGBA_SRGB_BLOCK),
            FORMAT(VK_FORMAT_BC2_UNORM_BLOCK), FORMAT(VK_FORMAT_BC2_SRGB_BLOCK),
            FORMAT(VK_FORMAT_BC3_UNORM_BLOCK), FORMAT(VK_FORMAT_BC3_SRGB_BLOCK),
            FORMAT(VK_FORMAT_BC4_UNORM_BLOCK), FORMAT(VK_FORMAT_BC4_SNORM_BLOCK),
            FORMAT(VK_FORMAT_BC5_UNORM_BLOCK), FORMAT(VK_FORMAT_BC5_SNORM_BLOCK),
            FORMAT(VK_FORMAT_BC6H_UFLOAT_BLOCK), FORMAT(VK_FORMAT_BC6H_SFLOAT_BLOCK),
            FORMAT(VK_FORMAT_BC7_UNORM_BLOCK), FORMAT(VK_FORMAT_BC7_SRGB_BLOCK),
            FORMAT(VK_FORMAT_ETC2_R8G8B8_UNORM_BLOCK), FORMAT(VK_FORMAT_ETC2_R8G8B8A8_UNORM_BLOCK),
            FORMAT(VK_FORMAT_ASTC_4x4_UNORM_BLOCK), FORMAT(VK_FORMAT_ASTC_4x4_SRGB_BLOCK)
        };
#undef FORMAT
        NSMutableDictionary* output = [NSMutableDictionary dictionary];
        for (const auto& item : selected)
        {
            VkFormatProperties p{};
            vkGetPhysicalDeviceFormatProperties(device, item.format, &p);
            NSMutableArray* imageQueries = [NSMutableArray array];
            // Format flags and usage-combination support are separate evidence.
            const VkImageUsageFlags usages[]{VK_IMAGE_USAGE_SAMPLED_BIT,
                VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
                VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
                VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT};
            for (VkImageUsageFlags usage : usages)
            {
                VkImageFormatProperties image{};
                const VkResult result = vkGetPhysicalDeviceImageFormatProperties(device, item.format,
                    VK_IMAGE_TYPE_2D, VK_IMAGE_TILING_OPTIMAL, usage, 0, &image);
                NSMutableDictionary* query = [@{@"usage_flags": @(usage), @"result": @(result),
                    @"query_status": result == VK_SUCCESS ? @"supported" : result == VK_ERROR_FORMAT_NOT_SUPPORTED ? @"unsupported" : @"unknown"} mutableCopy];
                if (result == VK_SUCCESS)
                {
                    query[@"max_extent"] = @[@(image.maxExtent.width), @(image.maxExtent.height), @(image.maxExtent.depth)];
                    query[@"max_mip_levels"] = @(image.maxMipLevels);
                    query[@"max_array_layers"] = @(image.maxArrayLayers);
                    query[@"sample_counts"] = @(image.sampleCounts);
                    query[@"max_resource_size"] = @(image.maxResourceSize);
                }
                [imageQueries addObject:query];
            }
            output[string(item.name)] = @{@"value": @(item.format), @"linearTilingFeatures": @(p.linearTilingFeatures),
                @"optimalTilingFeatures": @(p.optimalTilingFeatures), @"bufferFeatures": @(p.bufferFeatures), @"image_queries": imageQueries};
        }
        return output;
    }

    NSDictionary* memoryProperties(VkPhysicalDevice device)
    {
        VkPhysicalDeviceMemoryProperties p{};
        vkGetPhysicalDeviceMemoryProperties(device, &p);
        NSMutableArray* heaps = [NSMutableArray array], *types = [NSMutableArray array];
        for (uint32_t i = 0; i < p.memoryHeapCount; ++i)
            [heaps addObject:@{@"index": @(i), @"size_bytes": @(p.memoryHeaps[i].size), @"flags": @(p.memoryHeaps[i].flags)}];
        for (uint32_t i = 0; i < p.memoryTypeCount; ++i)
            [types addObject:@{@"index": @(i), @"heap_index": @(p.memoryTypes[i].heapIndex), @"flags": @(p.memoryTypes[i].propertyFlags)}];
        return @{@"heaps": heaps, @"types": types, @"note": @"Heap sizes are reported Vulkan limits, not an iOS process memory entitlement or available-memory guarantee."};
    }

    NSDictionary* surfaceProperties(VkPhysicalDevice device, Context& context, NSMutableArray* queues, NSMutableArray* unknown)
    {
        uint32_t count = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(device, &count, nullptr);
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(device, &count, families.data());
        families.resize(count);
        bool anyGraphicsPresent = false, anyPresentUnknown = false;
        for (uint32_t i = 0; i < families.size(); ++i)
        {
            const auto& f = families[i];
            NSMutableDictionary* queue = [@{@"index": @(i), @"queue_count": @(f.queueCount), @"queue_flags": @(f.queueFlags),
                @"timestamp_valid_bits": @(f.timestampValidBits), @"minimum_image_transfer_granularity":
                @[@(f.minImageTransferGranularity.width), @(f.minImageTransferGranularity.height), @(f.minImageTransferGranularity.depth)]} mutableCopy];
            if (context.surface)
            {
                VkBool32 present = VK_FALSE;
                const VkResult result = vkGetPhysicalDeviceSurfaceSupportKHR(device, i, context.surface, &present);
                queue[@"present_query_result"] = @(result);
                if (result == VK_SUCCESS)
                {
                    queue[@"present_supported"] = @(present != VK_FALSE);
                    anyGraphicsPresent |= f.queueCount && (f.queueFlags & VK_QUEUE_GRAPHICS_BIT) && present;
                }
                else anyPresentUnknown = true;
            }
            [queues addObject:queue];
        }
        if (!context.surface)
        {
            [unknown addObject:@"No Metal surface available; queue presentation and surface usage compatibility are unknown."];
            return @{@"query_status": @"unknown", @"note": @"No surface created. No presentation was attempted."};
        }
        NSMutableDictionary* output = [@{@"query_status": @"queried", @"presentation_tested": @NO,
            @"note": @"Surface support queries only; no logical device, swapchain, acquire, rendering or present call."} mutableCopy];
        if (anyGraphicsPresent || !anyPresentUnknown) output[@"graphics_present_queue"] = @(anyGraphicsPresent);
        VkSurfaceCapabilitiesKHR caps{};
        const VkResult result = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(device, context.surface, &caps);
        output[@"capabilities_result"] = @(result);
        if (result == VK_SUCCESS)
        {
            output[@"supported_usage_flags"] = @(caps.supportedUsageFlags);
            output[@"minimum_image_count"] = @(caps.minImageCount); output[@"maximum_image_count"] = @(caps.maxImageCount);
            output[@"current_extent"] = @[@(caps.currentExtent.width), @(caps.currentExtent.height)];
            output[@"minimum_extent"] = @[@(caps.minImageExtent.width), @(caps.minImageExtent.height)];
            output[@"maximum_extent"] = @[@(caps.maxImageExtent.width), @(caps.maxImageExtent.height)];
            output[@"supported_composite_alpha"] = @(caps.supportedCompositeAlpha);
            output[@"supported_transforms"] = @(caps.supportedTransforms); output[@"current_transform"] = @(caps.currentTransform);
        }
        else [unknown addObject:[NSString stringWithFormat:@"vkGetPhysicalDeviceSurfaceCapabilitiesKHR failed: %d", result]];
        try
        {
            auto formats = enumerate<VkSurfaceFormatKHR>([&](auto* n, auto* values) {
                return vkGetPhysicalDeviceSurfaceFormatsKHR(device, context.surface, n, values);
            }, "vkGetPhysicalDeviceSurfaceFormatsKHR");
            NSMutableArray* values = [NSMutableArray array];
            for (const auto& format : formats) [values addObject:@{@"format": @(format.format), @"color_space": @(format.colorSpace)}];
            output[@"formats"] = values;
            auto modes = enumerate<VkPresentModeKHR>([&](auto* n, auto* values) {
                return vkGetPhysicalDeviceSurfacePresentModesKHR(device, context.surface, n, values);
            }, "vkGetPhysicalDeviceSurfacePresentModesKHR");
            NSMutableArray* presentModes = [NSMutableArray array];
            for (const auto mode : modes) [presentModes addObject:@(mode)];
            output[@"present_modes"] = presentModes;
        }
        catch (const std::exception& error) { [unknown addObject:string(error.what())]; }
        return output;
    }
}

NSDictionary* collectCapabilities(CAMetalLayer* layer)
{
    uint32_t loaderVersion = VK_API_VERSION_1_0;
    check(vkEnumerateInstanceVersion(&loaderVersion), "vkEnumerateInstanceVersion");
    if (loaderVersion < VK_API_VERSION_1_1) throw std::runtime_error("Capability collector requires Vulkan instance API 1.1");
    const auto extensions = enumerate<VkExtensionProperties>([](auto* n, auto* values) {
        return vkEnumerateInstanceExtensionProperties(nullptr, n, values);
    }, "vkEnumerateInstanceExtensionProperties");
    std::vector<const char*> enabled;
    Context context;
    VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    if (has(extensions, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME))
    {
        enabled.push_back(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);
        instanceInfo.flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
    }
    const bool metalSurface = layer && has(extensions, VK_KHR_SURFACE_EXTENSION_NAME) && has(extensions, VK_EXT_METAL_SURFACE_EXTENSION_NAME);
    if (metalSurface) { enabled.push_back(VK_KHR_SURFACE_EXTENSION_NAME); enabled.push_back(VK_EXT_METAL_SURFACE_EXTENSION_NAME); }
    const bool debug = has(extensions, VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
    VkDebugUtilsMessengerCreateInfoEXT debugInfo{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};
    if (debug)
    {
        enabled.push_back(VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
        debugInfo.messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
        debugInfo.messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT | VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT
            | VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
        debugInfo.pfnUserCallback = Context::debug; debugInfo.pUserData = &context;
        instanceInfo.pNext = &debugInfo;
    }
    const uint32_t requested = std::min(loaderVersion, VK_API_VERSION_1_3);
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "iOS Zink capability audit"; app.apiVersion = requested;
    instanceInfo.pApplicationInfo = &app;
    instanceInfo.enabledExtensionCount = static_cast<uint32_t>(enabled.size()); instanceInfo.ppEnabledExtensionNames = enabled.data();
    check(vkCreateInstance(&instanceInfo, nullptr, &context.instance), "vkCreateInstance");
    if (debug)
    {
        auto create = reinterpret_cast<PFN_vkCreateDebugUtilsMessengerEXT>(vkGetInstanceProcAddr(context.instance, "vkCreateDebugUtilsMessengerEXT"));
        context.destroyMessenger = reinterpret_cast<PFN_vkDestroyDebugUtilsMessengerEXT>(vkGetInstanceProcAddr(context.instance, "vkDestroyDebugUtilsMessengerEXT"));
        if (!create || !context.destroyMessenger) throw std::runtime_error("Advertised debug-utils entry points unavailable");
        check(create(context.instance, &debugInfo, nullptr, &context.messenger), "vkCreateDebugUtilsMessengerEXT");
    }
    NSMutableArray* globalUnknown = [NSMutableArray array];
    if (metalSurface)
    {
        VkMetalSurfaceCreateInfoEXT info{VK_STRUCTURE_TYPE_METAL_SURFACE_CREATE_INFO_EXT};
        info.pLayer = layer;
        const VkResult result = vkCreateMetalSurfaceEXT(context.instance, &info, nullptr, &context.surface);
        if (result != VK_SUCCESS) [globalUnknown addObject:[NSString stringWithFormat:@"Metal surface creation failed: %d", result]];
    }
    NSMutableArray* devices = [NSMutableArray array];
    for (VkPhysicalDevice device : enumerate<VkPhysicalDevice>([&](auto* n, auto* values) {
        return vkEnumeratePhysicalDevices(context.instance, n, values);
    }, "vkEnumeratePhysicalDevices"))
    {
        VkPhysicalDeviceProperties p{};
        vkGetPhysicalDeviceProperties(device, &p);
        NSMutableDictionary* identity = [@{@"device_name": string(p.deviceName), @"api_version": version(p.apiVersion),
            @"api_version_raw": @(p.apiVersion), @"effective_query_api_version": version(std::min(p.apiVersion, requested)),
            @"vendor_id": @(p.vendorID), @"device_id": @(p.deviceID), @"device_type": @(p.deviceType), @"driver_version": @(p.driverVersion)} mutableCopy];
        NSMutableDictionary* result = [@{@"identity": identity} mutableCopy];
        NSMutableArray* unknown = [NSMutableArray array], *queried = [NSMutableArray array], *queues = [NSMutableArray array];
        result[@"unknown"] = unknown; result[@"queried_structures"] = queried;
        try
        {
            const auto deviceExtensions = enumerate<VkExtensionProperties>([&](auto* n, auto* values) {
                return vkEnumerateDeviceExtensionProperties(device, nullptr, n, values);
            }, "vkEnumerateDeviceExtensionProperties");
            result[@"extensions"] = extensionMap(deviceExtensions);
            const uint32_t api = std::min(p.apiVersion, requested);
            result[@"features"] = features(device, api, deviceExtensions, queried, unknown);
            NSMutableDictionary* limits = [NSMutableDictionary dictionary], *propertyValues = [NSMutableDictionary dictionary];
            coreLimits(limits, p.limits); result[@"limits"] = limits;
            properties(device, api, deviceExtensions, identity, propertyValues, queried); result[@"properties"] = propertyValues;
            result[@"formats"] = formatProperties(device); result[@"memory"] = memoryProperties(device);
            result[@"surface"] = surfaceProperties(device, context, queues, unknown); result[@"queues"] = queues;
            result[@"query_status"] = @"complete";
        }
        catch (const std::exception& error)
        {
            result[@"query_status"] = @"partial";
            [unknown addObject:string(error.what())];
        }
        [devices addObject:result];
    }
    if (!devices.count) [globalUnknown addObject:@"No physical devices were enumerated; no device compatibility assessment can be made."];
    NSMutableArray* enabledNames = [NSMutableArray array];
    for (const char* name : enabled) [enabledNames addObject:string(name)];
    // Finish all Vulkan calls before snapshotting callback diagnostics.
    context.close();
    NSArray* debugMessages;
    @synchronized (context.messages) { debugMessages = [context.messages copy]; }
    return @{@"schema_version": @1, @"instance": @{@"api_version": version(loaderVersion), @"requested_api_version": version(requested),
        @"header_version": @(VK_HEADER_VERSION), @"extensions": extensionMap(extensions), @"enabled_extensions": enabledNames,
        @"validation_layer_enabled": @NO, @"debug_utils_enabled": @(debug), @"debug_warnings": @(context.warnings.load()),
        @"debug_errors": @(context.errors.load()), @"debug_messages": debugMessages}, @"devices": devices, @"unknown": globalUnknown,
        @"query_only": @YES, @"logical_device_created": @NO, @"presentation_tested": @NO,
        @"note": @"Reported capabilities only. No Mesa/Zink/OSG, enabled device features, shaders, rendering, readback, performance or correctness tests."};
}
