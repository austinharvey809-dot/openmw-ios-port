// SPDX-License-Identifier: GPL-3.0-or-later
// Independent experiment: no OpenMW, SDL, Mesa, OpenGL or readback path.
#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>

#include <vulkan/vulkan.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
    FILE* logFile = nullptr;

    void logLine(const std::string& message)
    {
        NSLog(@"%s", message.c_str());
        if (logFile)
        {
            std::fprintf(logFile, "%s\n", message.c_str());
            std::fflush(logFile);
        }
    }

    void check(VkResult result, const char* operation)
    {
        if (result != VK_SUCCESS)
            throw std::runtime_error(std::string(operation) + " returned VkResult " + std::to_string(result));
    }

    std::string version(uint32_t value)
    {
        return std::to_string(VK_VERSION_MAJOR(value)) + "." + std::to_string(VK_VERSION_MINOR(value)) + "."
            + std::to_string(VK_VERSION_PATCH(value));
    }

    bool has(const std::vector<VkExtensionProperties>& extensions, const char* name)
    {
        return std::any_of(extensions.begin(), extensions.end(), [&](const auto& e) {
            return std::string(e.extensionName) == name;
        });
    }

    template <class T, class Query> std::vector<T> enumerate(Query query, const char* operation)
    {
        // VK_INCOMPLETE can occur when the list changes between the two queries.
        for (int attempt = 0; attempt != 4; ++attempt)
        {
            uint32_t count = 0;
            check(query(&count, static_cast<T*>(nullptr)), operation);
            std::vector<T> values(count);
            VkResult result = query(&count, values.data());
            if (result == VK_INCOMPLETE)
                continue;
            check(result, operation);
            values.resize(count);
            return values;
        }
        throw std::runtime_error(std::string(operation) + ": list remained incomplete");
    }

    class Renderer
    {
    public:
        void initialize(CAMetalLayer* layer)
        {
            uint32_t loaderVersion = VK_API_VERSION_1_0;
            check(vkEnumerateInstanceVersion(&loaderVersion), "vkEnumerateInstanceVersion");
            if (loaderVersion < VK_API_VERSION_1_1)
                throw std::runtime_error("Vulkan 1.1 required for capability queries");
            logLine("MoltenVK-linked instance API: " + version(loaderVersion));
            const auto extensions = enumerate<VkExtensionProperties>([](auto* n, auto* p) {
                return vkEnumerateInstanceExtensionProperties(nullptr, n, p);
            }, "instance extensions");
            std::vector<const char*> enabled{VK_KHR_SURFACE_EXTENSION_NAME, VK_EXT_METAL_SURFACE_EXTENSION_NAME};
            for (const char* name : enabled)
                if (!has(extensions, name))
                    throw std::runtime_error(std::string("Missing required instance extension: ") + name);

            VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
            if (has(extensions, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME))
            {
                enabled.push_back(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);
                instanceInfo.flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
            }
            VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
            app.pApplicationName = "iOS direct swapchain smoke";
            app.applicationVersion = VK_MAKE_VERSION(0, 1, 0);
            app.apiVersion = std::min(loaderVersion, VK_API_VERSION_1_3);
            instanceInfo.pApplicationInfo = &app;
            instanceInfo.enabledExtensionCount = static_cast<uint32_t>(enabled.size());
            instanceInfo.ppEnabledExtensionNames = enabled.data();
            check(vkCreateInstance(&instanceInfo, nullptr, &mInstance), "vkCreateInstance");
            VkMetalSurfaceCreateInfoEXT surfaceInfo{VK_STRUCTURE_TYPE_METAL_SURFACE_CREATE_INFO_EXT};
            surfaceInfo.pLayer = layer;
            check(vkCreateMetalSurfaceEXT(mInstance, &surfaceInfo, nullptr, &mSurface), "vkCreateMetalSurfaceEXT");

            auto devices = enumerate<VkPhysicalDevice>([&](auto* n, auto* p) {
                return vkEnumeratePhysicalDevices(mInstance, n, p);
            }, "physical devices");
            for (VkPhysicalDevice candidate : devices)
            {
                uint32_t count = 0;
                vkGetPhysicalDeviceQueueFamilyProperties(candidate, &count, nullptr);
                std::vector<VkQueueFamilyProperties> families(count);
                vkGetPhysicalDeviceQueueFamilyProperties(candidate, &count, families.data());
                for (uint32_t i = 0; i != count; ++i)
                {
                    VkBool32 present = VK_FALSE;
                    check(vkGetPhysicalDeviceSurfaceSupportKHR(candidate, i, mSurface, &present), "surface support");
                    if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) && present)
                    {
                        mPhysical = candidate;
                        mQueueFamily = i;
                        break;
                    }
                }
                if (mPhysical)
                    break;
            }
            if (!mPhysical)
                throw std::runtime_error("No single graphics/present queue for this Metal surface");
            const auto deviceExtensions = enumerate<VkExtensionProperties>([&](auto* n, auto* p) {
                return vkEnumerateDeviceExtensionProperties(mPhysical, nullptr, n, p);
            }, "device extensions");
            logCapabilities(deviceExtensions);
            if (!has(deviceExtensions, VK_KHR_SWAPCHAIN_EXTENSION_NAME))
                throw std::runtime_error("VK_KHR_swapchain unavailable");
            std::vector<const char*> deviceEnabled{VK_KHR_SWAPCHAIN_EXTENSION_NAME};
            if (has(deviceExtensions, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME))
                deviceEnabled.push_back(VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME);
            float priority = 1.0f;
            VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
            queueInfo.queueFamilyIndex = mQueueFamily;
            queueInfo.queueCount = 1;
            queueInfo.pQueuePriorities = &priority;
            VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
            deviceInfo.queueCreateInfoCount = 1;
            deviceInfo.pQueueCreateInfos = &queueInfo;
            deviceInfo.enabledExtensionCount = static_cast<uint32_t>(deviceEnabled.size());
            deviceInfo.ppEnabledExtensionNames = deviceEnabled.data();
            // No optional device features, descriptor indexing, shader compiler or Mesa required.
            check(vkCreateDevice(mPhysical, &deviceInfo, nullptr, &mDevice), "vkCreateDevice");
            vkGetDeviceQueue(mDevice, mQueueFamily, 0, &mQueue);
            VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
            poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
            poolInfo.queueFamilyIndex = mQueueFamily;
            check(vkCreateCommandPool(mDevice, &poolInfo, nullptr, &mPool), "vkCreateCommandPool");
            VkCommandBufferAllocateInfo alloc{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
            alloc.commandPool = mPool;
            alloc.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
            alloc.commandBufferCount = 1;
            check(vkAllocateCommandBuffers(mDevice, &alloc, &mCommand), "vkAllocateCommandBuffers");
            VkSemaphoreCreateInfo semaphoreInfo{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
            check(vkCreateSemaphore(mDevice, &semaphoreInfo, nullptr, &mAvailable), "acquire semaphore");
            VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
            fenceInfo.flags = VK_FENCE_CREATE_SIGNALED_BIT;
            check(vkCreateFence(mDevice, &fenceInfo, nullptr, &mFence), "submit fence");
            logLine("READY: VK_EXT_metal_surface + graphics/present queue; swapchain will follow layout");
        }

        bool render(uint32_t width, uint32_t height, double seconds)
        {
            if (!width || !height)
                return false;
            if (mDirty || width != mRequestedWidth || height != mRequestedHeight)
                recreate(width, height);
            check(vkWaitForFences(mDevice, 1, &mFence, VK_TRUE, 1000000000ull), "submit fence wait (1s)");
            uint32_t image = 0;
            VkResult acquire = vkAcquireNextImageKHR(mDevice, mSwapchain, 100000000ull, mAvailable, VK_NULL_HANDLE, &image);
            if (acquire == VK_TIMEOUT || acquire == VK_NOT_READY)
                return false;
            if (acquire == VK_ERROR_OUT_OF_DATE_KHR)
            {
                mDirty = true;
                return false;
            }
            if (acquire != VK_SUBOPTIMAL_KHR)
                check(acquire, "vkAcquireNextImageKHR");
            check(vkResetCommandBuffer(mCommand, 0), "vkResetCommandBuffer");
            VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
            begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
            check(vkBeginCommandBuffer(mCommand, &begin), "vkBeginCommandBuffer");
            VkClearValue clear{};
            // A slow visible color cycle distinguishes a live swapchain from a static launch screen.
            clear.color.float32[0] = 0.15f + 0.35f * static_cast<float>(0.5 + 0.5 * std::sin(seconds));
            clear.color.float32[1] = 0.15f + 0.35f * static_cast<float>(0.5 + 0.5 * std::sin(seconds + 2.1));
            clear.color.float32[2] = 0.15f + 0.35f * static_cast<float>(0.5 + 0.5 * std::sin(seconds + 4.2));
            clear.color.float32[3] = 1.0f;
            VkRenderPassBeginInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
            pass.renderPass = mPass;
            pass.framebuffer = mFrames.at(image);
            pass.renderArea.extent = mExtent;
            pass.clearValueCount = 1;
            pass.pClearValues = &clear;
            vkCmdBeginRenderPass(mCommand, &pass, VK_SUBPASS_CONTENTS_INLINE);
            vkCmdEndRenderPass(mCommand);
            check(vkEndCommandBuffer(mCommand), "vkEndCommandBuffer");
            const VkPipelineStageFlags waitStage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
            VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
            submit.waitSemaphoreCount = 1;
            submit.pWaitSemaphores = &mAvailable;
            submit.pWaitDstStageMask = &waitStage;
            submit.commandBufferCount = 1;
            submit.pCommandBuffers = &mCommand;
            submit.signalSemaphoreCount = 1;
            submit.pSignalSemaphores = &mPresentReady.at(image);
            check(vkResetFences(mDevice, 1, &mFence), "vkResetFences");
            check(vkQueueSubmit(mQueue, 1, &submit, mFence), "vkQueueSubmit");
            VkPresentInfoKHR present{VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};
            present.waitSemaphoreCount = 1;
            present.pWaitSemaphores = &mPresentReady.at(image);
            present.swapchainCount = 1;
            present.pSwapchains = &mSwapchain;
            present.pImageIndices = &image;
            VkResult result = vkQueuePresentKHR(mQueue, &present);
            if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR || acquire == VK_SUBOPTIMAL_KHR)
                mDirty = true;
            if (result != VK_ERROR_OUT_OF_DATE_KHR && result != VK_SUBOPTIMAL_KHR)
                check(result, "vkQueuePresentKHR");
            if (result == VK_ERROR_OUT_OF_DATE_KHR)
                return false;
            ++mPresents;
            return true;
        }

        void quiesce()
        {
            if (mDevice)
                check(vkDeviceWaitIdle(mDevice), "vkDeviceWaitIdle before inactive/resize");
        }
        void invalidateSurfaceSize() { mDirty = true; }
        uint64_t presents() const { return mPresents; }

        ~Renderer()
        {
            if (mDevice)
            {
                vkDeviceWaitIdle(mDevice);
                destroySwapchain();
                if (mFence) vkDestroyFence(mDevice, mFence, nullptr);
                if (mAvailable) vkDestroySemaphore(mDevice, mAvailable, nullptr);
                if (mPool) vkDestroyCommandPool(mDevice, mPool, nullptr);
                vkDestroyDevice(mDevice, nullptr);
            }
            if (mSurface) vkDestroySurfaceKHR(mInstance, mSurface, nullptr);
            if (mInstance) vkDestroyInstance(mInstance, nullptr);
        }

    private:
        void logCapabilities(const std::vector<VkExtensionProperties>& extensions)
        {
            VkPhysicalDeviceProperties properties{};
            vkGetPhysicalDeviceProperties(mPhysical, &properties);
            if (properties.apiVersion < VK_API_VERSION_1_1)
                throw std::runtime_error("Selected physical device does not support Vulkan 1.1");
            logLine(std::string("DEVICE: ") + properties.deviceName + "; Vulkan " + version(properties.apiVersion)
                + "; vendor=" + std::to_string(properties.vendorID) + "; driver=" + std::to_string(properties.driverVersion));
            if (properties.apiVersion >= VK_API_VERSION_1_2)
            {
                VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
                VkPhysicalDeviceProperties2 details{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
                details.pNext = &driver;
                vkGetPhysicalDeviceProperties2(mPhysical, &details);
                logLine(std::string("DRIVER: ") + driver.driverName + "; " + driver.driverInfo);
            }
            for (const auto& extension : extensions)
                logLine(std::string("EXT: ") + extension.extensionName + " revision=" + std::to_string(extension.specVersion));
            VkPhysicalDeviceFeatures2 features{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
            VkPhysicalDeviceVulkan12Features v12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
            VkPhysicalDeviceVulkan13Features v13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
            VkPhysicalDevicePortabilitySubsetFeaturesKHR portability{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PORTABILITY_SUBSET_FEATURES_KHR};
            VkPhysicalDeviceRobustness2FeaturesEXT robustness{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ROBUSTNESS_2_FEATURES_EXT};
            VkPhysicalDeviceCustomBorderColorFeaturesEXT border{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_CUSTOM_BORDER_COLOR_FEATURES_EXT};
            VkPhysicalDeviceLineRasterizationFeaturesEXT lines{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_LINE_RASTERIZATION_FEATURES_EXT};
            void** tail = &features.pNext;
            const auto append = [&](auto& value) { *tail = &value; tail = &value.pNext; };
            if (properties.apiVersion >= VK_API_VERSION_1_2) append(v12);
            if (properties.apiVersion >= VK_API_VERSION_1_3) append(v13);
            if (has(extensions, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME)) append(portability);
            if (has(extensions, VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME)) append(border);
            if (has(extensions, VK_EXT_LINE_RASTERIZATION_EXTENSION_NAME)) append(lines);
            bool robustnessAvailable = has(extensions, VK_EXT_ROBUSTNESS_2_EXTENSION_NAME);
#ifdef VK_KHR_robustness2
            VkPhysicalDeviceRobustness2FeaturesKHR robustnessKHR{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ROBUSTNESS_2_FEATURES_KHR};
            const bool hasRobustnessKHR = has(extensions, VK_KHR_ROBUSTNESS_2_EXTENSION_NAME);
            if (hasRobustnessKHR)
            {
                append(robustnessKHR);
                robustnessAvailable = true;
            }
            else
#endif
            if (robustnessAvailable) append(robustness);
            vkGetPhysicalDeviceFeatures2(mPhysical, &features);
            const auto flag = [](const char* name, VkBool32 value) {
                logLine(std::string("FEATURE (reported, not enabled): ") + name + "=" + (value ? "true" : "false"));
            };
            flag("logicOp", features.features.logicOp);
            flag("fillModeNonSolid", features.features.fillModeNonSolid);
            flag("shaderClipDistance", features.features.shaderClipDistance);
            flag("robustBufferAccess", features.features.robustBufferAccess);
            if (properties.apiVersion >= VK_API_VERSION_1_2)
            {
                flag("timelineSemaphore", v12.timelineSemaphore);
                flag("scalarBlockLayout", v12.scalarBlockLayout);
                flag("imagelessFramebuffer", v12.imagelessFramebuffer);
                flag("descriptorIndexing", v12.descriptorIndexing);
            }
            if (properties.apiVersion >= VK_API_VERSION_1_3) flag("dynamicRendering", v13.dynamicRendering);
            if (has(extensions, VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME))
            {
                flag("customBorderColors", border.customBorderColors);
                flag("customBorderColorWithoutFormat", border.customBorderColorWithoutFormat);
            }
            if (has(extensions, VK_EXT_LINE_RASTERIZATION_EXTENSION_NAME))
            {
                flag("rectangularLines", lines.rectangularLines);
                flag("bresenhamLines", lines.bresenhamLines);
                flag("smoothLines", lines.smoothLines);
            }
            if (robustnessAvailable)
            {
                VkBool32 nullDescriptor = robustness.nullDescriptor;
#ifdef VK_KHR_robustness2
                if (hasRobustnessKHR) nullDescriptor = robustnessKHR.nullDescriptor;
#endif
                flag("nullDescriptor", nullDescriptor);
            }
            else logLine("FEATURE: nullDescriptor=unavailable (no KHR/EXT robustness2)");
            if (has(extensions, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME))
            {
                flag("portability.triangleFans", portability.triangleFans);
                flag("portability.events", portability.events);
                flag("portability.imageViewFormatReinterpretation", portability.imageViewFormatReinterpretation);
            }
            logLine("LIMIT: maxImageDimension2D=" + std::to_string(properties.limits.maxImageDimension2D)
                + "; maxPerStageDescriptorSamplers=" + std::to_string(properties.limits.maxPerStageDescriptorSamplers));
            logLine("Capability logging is not a Zink compatibility certification.");
        }

        void recreate(uint32_t width, uint32_t height)
        {
            quiesce();
            destroySwapchain();
            VkSurfaceCapabilitiesKHR caps{};
            check(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(mPhysical, mSurface, &caps), "surface capabilities");
            if (!(caps.supportedUsageFlags & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT))
                throw std::runtime_error("Swapchain images cannot be color attachments");
            auto formats = enumerate<VkSurfaceFormatKHR>([&](auto* n, auto* p) {
                return vkGetPhysicalDeviceSurfaceFormatsKHR(mPhysical, mSurface, n, p);
            }, "surface formats");
            if (formats.empty()) throw std::runtime_error("No surface formats");
            auto format = formats.front();
            for (const auto& candidate : formats)
                if (candidate.format == VK_FORMAT_B8G8R8A8_UNORM && candidate.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                    format = candidate;
            if (format.format == VK_FORMAT_UNDEFINED) format.format = VK_FORMAT_B8G8R8A8_UNORM;
            const auto modes = enumerate<VkPresentModeKHR>([&](auto* n, auto* p) {
                return vkGetPhysicalDeviceSurfacePresentModesKHR(mPhysical, mSurface, n, p);
            }, "present modes");
            if (std::find(modes.begin(), modes.end(), VK_PRESENT_MODE_FIFO_KHR) == modes.end())
                throw std::runtime_error("FIFO presentation unavailable");
            mExtent = caps.currentExtent;
            if (mExtent.width == std::numeric_limits<uint32_t>::max())
            {
                mExtent.width = std::clamp(width, caps.minImageExtent.width, caps.maxImageExtent.width);
                mExtent.height = std::clamp(height, caps.minImageExtent.height, caps.maxImageExtent.height);
            }
            if (!mExtent.width || !mExtent.height) throw std::runtime_error("Zero surface extent");
            uint32_t imageCount = caps.minImageCount + 1;
            if (caps.maxImageCount) imageCount = std::min(imageCount, caps.maxImageCount);
            VkCompositeAlphaFlagBitsKHR alpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
            for (auto choice : {VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR,
                     VK_COMPOSITE_ALPHA_POST_MULTIPLIED_BIT_KHR, VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR})
                if (caps.supportedCompositeAlpha & choice) { alpha = choice; break; }
            VkSwapchainCreateInfoKHR swap{VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR};
            swap.surface = mSurface;
            swap.minImageCount = imageCount;
            swap.imageFormat = format.format;
            swap.imageColorSpace = format.colorSpace;
            swap.imageExtent = mExtent;
            swap.imageArrayLayers = 1;
            swap.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
            swap.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
            swap.preTransform = caps.currentTransform;
            swap.compositeAlpha = alpha;
            swap.presentMode = VK_PRESENT_MODE_FIFO_KHR;
            swap.clipped = VK_TRUE;
            check(vkCreateSwapchainKHR(mDevice, &swap, nullptr, &mSwapchain), "vkCreateSwapchainKHR");
            auto images = enumerate<VkImage>([&](auto* n, auto* p) {
                return vkGetSwapchainImagesKHR(mDevice, mSwapchain, n, p);
            }, "swapchain images");
            VkAttachmentDescription attachment{};
            attachment.format = format.format;
            attachment.samples = VK_SAMPLE_COUNT_1_BIT;
            attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
            attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
            attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
            attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
            attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
            attachment.finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
            VkAttachmentReference color{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
            VkSubpassDescription subpass{};
            subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
            subpass.colorAttachmentCount = 1;
            subpass.pColorAttachments = &color;
            VkSubpassDependency dependency{};
            dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
            dependency.dstSubpass = 0;
            dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
            dependency.dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
            dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
            VkRenderPassCreateInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
            pass.attachmentCount = 1;
            pass.pAttachments = &attachment;
            pass.subpassCount = 1;
            pass.pSubpasses = &subpass;
            pass.dependencyCount = 1;
            pass.pDependencies = &dependency;
            check(vkCreateRenderPass(mDevice, &pass, nullptr, &mPass), "vkCreateRenderPass");
            for (VkImage image : images)
            {
                VkImageView view = VK_NULL_HANDLE;
                VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
                viewInfo.image = image;
                viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
                viewInfo.format = format.format;
                viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
                check(vkCreateImageView(mDevice, &viewInfo, nullptr, &view), "vkCreateImageView");
                mViews.push_back(view);
                VkFramebuffer frame = VK_NULL_HANDLE;
                VkFramebufferCreateInfo frameInfo{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
                frameInfo.renderPass = mPass;
                frameInfo.attachmentCount = 1;
                frameInfo.pAttachments = &mViews.back();
                frameInfo.width = mExtent.width;
                frameInfo.height = mExtent.height;
                frameInfo.layers = 1;
                check(vkCreateFramebuffer(mDevice, &frameInfo, nullptr, &frame), "vkCreateFramebuffer");
                mFrames.push_back(frame);
                VkSemaphore semaphore = VK_NULL_HANDLE;
                VkSemaphoreCreateInfo semaphoreInfo{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
                check(vkCreateSemaphore(mDevice, &semaphoreInfo, nullptr, &semaphore), "present semaphore");
                // Per-image presentation semaphores: submit-fence completion alone does not retire presentation.
                mPresentReady.push_back(semaphore);
            }
            mRequestedWidth = width;
            mRequestedHeight = height;
            mDirty = false;
            logLine("SWAPCHAIN: " + std::to_string(mExtent.width) + "x" + std::to_string(mExtent.height)
                + "; images=" + std::to_string(images.size()) + "; format=" + std::to_string(format.format)
                + "; FIFO; COLOR_ATTACHMENT only; no framebuffer readback");
        }

        void destroySwapchain()
        {
            for (auto frame : mFrames) vkDestroyFramebuffer(mDevice, frame, nullptr);
            for (auto view : mViews) vkDestroyImageView(mDevice, view, nullptr);
            for (auto semaphore : mPresentReady) vkDestroySemaphore(mDevice, semaphore, nullptr);
            mFrames.clear(); mViews.clear(); mPresentReady.clear();
            if (mPass) vkDestroyRenderPass(mDevice, mPass, nullptr);
            if (mSwapchain) vkDestroySwapchainKHR(mDevice, mSwapchain, nullptr);
            mPass = VK_NULL_HANDLE; mSwapchain = VK_NULL_HANDLE;
        }

        VkInstance mInstance = VK_NULL_HANDLE;
        VkSurfaceKHR mSurface = VK_NULL_HANDLE;
        VkPhysicalDevice mPhysical = VK_NULL_HANDLE;
        VkDevice mDevice = VK_NULL_HANDLE;
        VkQueue mQueue = VK_NULL_HANDLE;
        uint32_t mQueueFamily = 0;
        VkCommandPool mPool = VK_NULL_HANDLE;
        VkCommandBuffer mCommand = VK_NULL_HANDLE;
        VkSemaphore mAvailable = VK_NULL_HANDLE;
        VkFence mFence = VK_NULL_HANDLE;
        VkSwapchainKHR mSwapchain = VK_NULL_HANDLE;
        VkRenderPass mPass = VK_NULL_HANDLE;
        VkExtent2D mExtent{};
        std::vector<VkImageView> mViews;
        std::vector<VkFramebuffer> mFrames;
        std::vector<VkSemaphore> mPresentReady;
        uint32_t mRequestedWidth = 0, mRequestedHeight = 0;
        uint64_t mPresents = 0;
        bool mDirty = true;
    };
}

@interface SmokeView : UIView
@end
@implementation SmokeView
+ (Class)layerClass { return [CAMetalLayer class]; }
@end

@interface SmokeViewController : UIViewController
- (void)resumeRendering;
- (void)suspendRendering;
@end

@implementation SmokeViewController
{
    std::unique_ptr<Renderer> _renderer;
    CADisplayLink* _displayLink;
    UILabel* _status;
    BOOL _active;
    BOOL _failed;
    CFTimeInterval _epoch;
    CFTimeInterval _lastReport;
}
- (void)loadView
{
    self.view = [[SmokeView alloc] initWithFrame:CGRectZero];
    CAMetalLayer* layer = (CAMetalLayer*)self.view.layer;
    layer.opaque = YES;
    layer.framebufferOnly = YES;
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    _status = [[UILabel alloc] initWithFrame:CGRectZero];
    _status.text = @"Initializing direct Vulkan presentation…";
    _status.textColor = UIColor.whiteColor;
    _status.backgroundColor = [UIColor colorWithWhite:0 alpha:0.65];
    _status.numberOfLines = 0;
    _status.font = [UIFont monospacedSystemFontOfSize:13 weight:UIFontWeightRegular];
    [self.view addSubview:_status];
}
- (void)viewDidLayoutSubviews
{
    [super viewDidLayoutSubviews];
    CAMetalLayer* layer = (CAMetalLayer*)self.view.layer;
    CGFloat scale = self.view.window.windowScene.screen.scale;
    if (scale <= 0) scale = self.view.contentScaleFactor;
    layer.contentsScale = scale;
    layer.drawableSize = CGSizeMake(std::round(self.view.bounds.size.width * scale), std::round(self.view.bounds.size.height * scale));
    CGRect safe = UIEdgeInsetsInsetRect(self.view.bounds, self.view.safeAreaInsets);
    _status.frame = CGRectMake(safe.origin.x + 8, safe.origin.y + 8, std::max<CGFloat>(1, safe.size.width - 16), 100);
}
- (void)failWithMessage:(NSString*)message
{
    _failed = YES;
    [_displayLink invalidate];
    _displayLink = nil;
    _status.text = [@"BLOCKED — no rendering fallback\n" stringByAppendingString:message];
    logLine(std::string("BLOCKED: ") + message.UTF8String);
}
- (void)resumeRendering
{
    if (_failed || _active) return;
    _active = YES;
    [self loadViewIfNeeded];
    try
    {
        if (!_renderer)
        {
            NSString* documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
            if (logFile) std::fclose(logFile);
            logFile = std::fopen([documents stringByAppendingPathComponent:@"smoke.log"].fileSystemRepresentation, "w");
            logLine("BEGIN: standalone iOS Vulkan smoke; 30 Hz request; no Mesa; no performance claim");
            logLine(std::string("OS: ") + UIDevice.currentDevice.systemVersion.UTF8String);
            _renderer = std::make_unique<Renderer>();
            _renderer->initialize((CAMetalLayer*)self.view.layer);
        }
        _renderer->invalidateSurfaceSize();
        _epoch = CACurrentMediaTime();
        _lastReport = _epoch;
        _displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(draw:)];
        _displayLink.preferredFrameRateRange = CAFrameRateRangeMake(30, 30, 30);
        [_displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
        logLine("ACTIVE: display callback requested at 30 Hz");
    }
    catch (const std::exception& error) { [self failWithMessage:@(error.what())]; }
}
- (void)suspendRendering
{
    _active = NO;
    [_displayLink invalidate];
    _displayLink = nil;
    try
    {
        if (_renderer) _renderer->quiesce();
        logLine("INACTIVE: callbacks stopped; submitted device work idle");
    }
    catch (const std::exception& error) { [self failWithMessage:@(error.what())]; }
}
- (void)draw:(CADisplayLink*)link
{
    if (!_active || _failed) return;
    try
    {
        CAMetalLayer* layer = (CAMetalLayer*)self.view.layer;
        const double seconds = link.timestamp - _epoch;
        if (_renderer->render(static_cast<uint32_t>(layer.drawableSize.width), static_cast<uint32_t>(layer.drawableSize.height), seconds)
            && link.timestamp - _lastReport >= 1.0)
        {
            _lastReport = link.timestamp;
            const auto thermal = NSProcessInfo.processInfo.thermalState;
            NSString* message = [NSString stringWithFormat:@"Direct Vulkan swapchain → CAMetalLayer\nPresent calls: %llu; 30 Hz requested\nThermal state: %ld; inspect smoke.log + Metal capture",
                static_cast<unsigned long long>(_renderer->presents()), static_cast<long>(thermal)];
            _status.text = message;
            logLine(message.UTF8String);
        }
    }
    catch (const std::exception& error) { [self failWithMessage:@(error.what())]; }
}
- (void)dealloc { [_displayLink invalidate]; }
@end

@interface SmokeSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation SmokeSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options
{
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [[SmokeViewController alloc] init];
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene*)scene
{
    (void)scene;
    [(SmokeViewController*)self.window.rootViewController resumeRendering];
}
- (void)sceneWillResignActive:(UIScene*)scene
{
    (void)scene;
    [(SmokeViewController*)self.window.rootViewController suspendRendering];
}
- (void)sceneDidDisconnect:(UIScene*)scene
{
    (void)scene;
    [(SmokeViewController*)self.window.rootViewController suspendRendering];
    self.window = nil;
    if (logFile) { std::fclose(logFile); logFile = nullptr; }
}
@end

@interface SmokeAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation SmokeAppDelegate
@end

int main(int argc, char* argv[])
{
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(SmokeAppDelegate.class)); }
}
