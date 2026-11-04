// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <vulkan/vulkan.h>
#include "SceneMath.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

namespace smoke
{
    // Device resources are independent of UIKit and of the swapchain's color images.
    // The owner must idle the device before destroyTargets()/destroy().
    class CubeResources
    {
    public:
        CubeResources() = default;
        CubeResources(const CubeResources&) = delete;
        CubeResources& operator=(const CubeResources&) = delete;

        void initialize(VkPhysicalDevice physical, VkDevice device, VkQueue queue, uint32_t queueFamily,
            VkCommandPool pool, const uint8_t* pixels, size_t bytes)
        {
            if (mDevice) throw std::runtime_error("Cube resources already initialized");
            if (!pixels || bytes != textureSize * textureSize * 4)
                throw std::runtime_error("Cube requires the 32x32 RGBA checkerboard resource");
            mDevice = device;
            mPhysical = physical;
            vkGetPhysicalDeviceMemoryProperties(physical, &mMemoryProperties);
            for (VkFormat candidate : {VK_FORMAT_D16_UNORM, VK_FORMAT_D32_SFLOAT})
            {
                VkFormatProperties properties{};
                vkGetPhysicalDeviceFormatProperties(physical, candidate, &properties);
                if (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT)
                { mDepthFormat = candidate; break; }
            }
            if (mDepthFormat == VK_FORMAT_UNDEFINED)
                throw std::runtime_error("No supported D16/D32 depth attachment format");
            VkFormatProperties textureProperties{};
            vkGetPhysicalDeviceFormatProperties(physical, VK_FORMAT_R8G8B8A8_UNORM, &textureProperties);
            const VkFormatFeatureFlags textureFeatures = VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT | VK_FORMAT_FEATURE_TRANSFER_DST_BIT;
            if ((textureProperties.optimalTilingFeatures & textureFeatures) != textureFeatures)
                throw std::runtime_error("RGBA8 optimal sampled/transfer-destination images unavailable");

            createBuffer(sizeof(cubeVertices), VK_BUFFER_USAGE_VERTEX_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0, mVertices);
            createBuffer(sizeof(cubeIndices), VK_BUFFER_USAGE_INDEX_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0, mIndices);
            createImage({textureSize, textureSize}, VK_FORMAT_R8G8B8A8_UNORM,
                VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT, VK_IMAGE_ASPECT_COLOR_BIT, 0, mTexture);
            upload(queue, queueFamily, pool, pixels, bytes);

            VkSamplerCreateInfo sampler{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
            sampler.magFilter = VK_FILTER_NEAREST;
            sampler.minFilter = VK_FILTER_NEAREST;
            sampler.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
            sampler.addressModeU = sampler.addressModeV = sampler.addressModeW = VK_SAMPLER_ADDRESS_MODE_REPEAT;
            sampler.maxLod = 0;
            sampler.maxAnisotropy = 1;
            cubeCheck(vkCreateSampler(mDevice, &sampler, nullptr, &mSampler), "vkCreateSampler");
            VkDescriptorSetLayoutBinding binding{};
            binding.binding = 0;
            binding.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
            binding.descriptorCount = 1;
            binding.stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT;
            VkDescriptorSetLayoutCreateInfo layout{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
            layout.bindingCount = 1; layout.pBindings = &binding;
            cubeCheck(vkCreateDescriptorSetLayout(mDevice, &layout, nullptr, &mSetLayout), "vkCreateDescriptorSetLayout");
            VkDescriptorPoolSize size{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1};
            VkDescriptorPoolCreateInfo descriptorPool{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
            descriptorPool.maxSets = 1; descriptorPool.poolSizeCount = 1; descriptorPool.pPoolSizes = &size;
            cubeCheck(vkCreateDescriptorPool(mDevice, &descriptorPool, nullptr, &mDescriptorPool), "vkCreateDescriptorPool");
            VkDescriptorSetAllocateInfo allocation{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
            allocation.descriptorPool = mDescriptorPool; allocation.descriptorSetCount = 1; allocation.pSetLayouts = &mSetLayout;
            cubeCheck(vkAllocateDescriptorSets(mDevice, &allocation, &mDescriptorSet), "vkAllocateDescriptorSets");
            VkDescriptorImageInfo image{mSampler, mTexture.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
            VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
            write.dstSet = mDescriptorSet; write.dstBinding = 0; write.descriptorCount = 1;
            write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER; write.pImageInfo = &image;
            vkUpdateDescriptorSets(mDevice, 1, &write, 0, nullptr);
            VkPushConstantRange transform{VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(float) * 16};
            VkPipelineLayoutCreateInfo pipelineLayout{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
            pipelineLayout.setLayoutCount = 1; pipelineLayout.pSetLayouts = &mSetLayout;
            pipelineLayout.pushConstantRangeCount = 1; pipelineLayout.pPushConstantRanges = &transform;
            cubeCheck(vkCreatePipelineLayout(mDevice, &pipelineLayout, nullptr, &mPipelineLayout), "vkCreatePipelineLayout(cube)");
        }

        VkFormat depthFormat() const { return mDepthFormat; }
        VkImageView depthView(uint32_t image) const { return mDepth.at(image).view; }

        void createTargets(VkRenderPass pass, VkExtent2D extent, uint32_t imageCount,
            const std::function<VkShaderModule(const char*)>& loadShader)
        {
            if (mPipeline || !mDepth.empty()) throw std::runtime_error("Cube targets must be destroyed before recreation");
            mDepth.resize(imageCount);
            for (auto& depth : mDepth)
                createImage(extent, mDepthFormat,
                    VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSIENT_ATTACHMENT_BIT,
                    VK_IMAGE_ASPECT_DEPTH_BIT, VK_MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT, depth);

            VkShaderModule vertex = VK_NULL_HANDLE, fragment = VK_NULL_HANDLE;
            try
            {
                vertex = loadShader("cube.vert");
                fragment = loadShader("cube.frag");
                VkPipelineShaderStageCreateInfo stages[2]{};
                for (auto& stage : stages) { stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; stage.pName = "main"; }
                stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT; stages[0].module = vertex;
                stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT; stages[1].module = fragment;
                VkVertexInputBindingDescription binding{0, sizeof(CubeVertex), VK_VERTEX_INPUT_RATE_VERTEX};
                const VkVertexInputAttributeDescription attributes[]{
                    {0, 0, VK_FORMAT_R32G32B32_SFLOAT, static_cast<uint32_t>(offsetof(CubeVertex, position))},
                    {1, 0, VK_FORMAT_R32G32_SFLOAT, static_cast<uint32_t>(offsetof(CubeVertex, uv))}};
                VkPipelineVertexInputStateCreateInfo input{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
                input.vertexBindingDescriptionCount = 1; input.pVertexBindingDescriptions = &binding;
                input.vertexAttributeDescriptionCount = 2; input.pVertexAttributeDescriptions = attributes;
                VkPipelineInputAssemblyStateCreateInfo assembly{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
                assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
                VkPipelineViewportStateCreateInfo viewport{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
                viewport.viewportCount = 1; viewport.scissorCount = 1;
                VkPipelineRasterizationStateCreateInfo raster{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
                raster.polygonMode = VK_POLYGON_MODE_FILL; raster.cullMode = VK_CULL_MODE_NONE;
                raster.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE; raster.lineWidth = 1.0f;
                VkPipelineMultisampleStateCreateInfo samples{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
                samples.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
                VkPipelineDepthStencilStateCreateInfo depth{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
                depth.depthTestEnable = VK_TRUE; depth.depthWriteEnable = VK_TRUE; depth.depthCompareOp = VK_COMPARE_OP_LESS;
                VkPipelineColorBlendAttachmentState attachment{};
                attachment.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
                VkPipelineColorBlendStateCreateInfo blend{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
                blend.attachmentCount = 1; blend.pAttachments = &attachment;
                const VkDynamicState states[]{VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
                VkPipelineDynamicStateCreateInfo dynamic{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
                dynamic.dynamicStateCount = 2; dynamic.pDynamicStates = states;
                VkGraphicsPipelineCreateInfo pipeline{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
                pipeline.stageCount = 2; pipeline.pStages = stages;
                pipeline.pVertexInputState = &input; pipeline.pInputAssemblyState = &assembly;
                pipeline.pViewportState = &viewport; pipeline.pRasterizationState = &raster;
                pipeline.pMultisampleState = &samples; pipeline.pDepthStencilState = &depth;
                pipeline.pColorBlendState = &blend; pipeline.pDynamicState = &dynamic;
                pipeline.layout = mPipelineLayout; pipeline.renderPass = pass; pipeline.subpass = 0;
                cubeCheck(vkCreateGraphicsPipelines(mDevice, VK_NULL_HANDLE, 1, &pipeline, nullptr, &mPipeline), "vkCreateGraphicsPipelines(cube)");
            }
            catch (...)
            {
                if (fragment) vkDestroyShaderModule(mDevice, fragment, nullptr);
                if (vertex) vkDestroyShaderModule(mDevice, vertex, nullptr);
                throw;
            }
            vkDestroyShaderModule(mDevice, fragment, nullptr);
            vkDestroyShaderModule(mDevice, vertex, nullptr);
        }

        void record(VkCommandBuffer command, const std::array<float, 16>& mvp) const
        {
            const VkDeviceSize offset = 0;
            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, mPipeline);
            vkCmdBindVertexBuffers(command, 0, 1, &mVertices.buffer, &offset);
            vkCmdBindIndexBuffer(command, mIndices.buffer, 0, VK_INDEX_TYPE_UINT16);
            vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_GRAPHICS, mPipelineLayout, 0, 1, &mDescriptorSet, 0, nullptr);
            vkCmdPushConstants(command, mPipelineLayout, VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(float) * 16, mvp.data());
            vkCmdDrawIndexed(command, static_cast<uint32_t>(cubeIndices.size()), 1, 0, 0, 0);
        }

        void destroyTargets()
        {
            if (!mDevice) return;
            if (mPipeline) vkDestroyPipeline(mDevice, mPipeline, nullptr);
            mPipeline = VK_NULL_HANDLE;
            for (auto& depth : mDepth) destroyImage(depth);
            mDepth.clear();
        }

        void destroy()
        {
            if (!mDevice) return;
            destroyTargets();
            releaseUpload(); // owner has quiesced, including any timed-out initialization submit
            if (mPipelineLayout) vkDestroyPipelineLayout(mDevice, mPipelineLayout, nullptr);
            if (mDescriptorPool) vkDestroyDescriptorPool(mDevice, mDescriptorPool, nullptr);
            if (mSetLayout) vkDestroyDescriptorSetLayout(mDevice, mSetLayout, nullptr);
            if (mSampler) vkDestroySampler(mDevice, mSampler, nullptr);
            mPipelineLayout = VK_NULL_HANDLE; mDescriptorPool = VK_NULL_HANDLE;
            mSetLayout = VK_NULL_HANDLE; mDescriptorSet = VK_NULL_HANDLE; mSampler = VK_NULL_HANDLE;
            destroyImage(mTexture); destroyBuffer(mIndices); destroyBuffer(mVertices);
            mDevice = VK_NULL_HANDLE; mPhysical = VK_NULL_HANDLE; mDepthFormat = VK_FORMAT_UNDEFINED;
        }

    private:
        static constexpr uint32_t textureSize = 32;
        struct Buffer { VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; VkMemoryPropertyFlags flags = 0; };
        struct Image { VkImage image = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; VkImageView view = VK_NULL_HANDLE; };

        static void cubeCheck(VkResult result, const char* operation)
        {
            if (result != VK_SUCCESS)
                throw std::runtime_error(std::string(operation) + " returned VkResult " + std::to_string(result));
        }

        uint32_t memoryType(uint32_t bits, VkMemoryPropertyFlags required, VkMemoryPropertyFlags preferred) const
        {
            for (int pass = 0; pass != 2; ++pass)
                for (uint32_t i = 0; i != mMemoryProperties.memoryTypeCount; ++i)
                {
                    const auto flags = mMemoryProperties.memoryTypes[i].propertyFlags;
                    if ((bits & (1u << i)) && (flags & required) == required && (pass || (flags & preferred) == preferred)) return i;
                }
            throw std::runtime_error("No compatible Vulkan memory type for cube resource");
        }

        void createBuffer(VkDeviceSize size, VkBufferUsageFlags usage, VkMemoryPropertyFlags required,
            VkMemoryPropertyFlags preferred, Buffer& result)
        {
            VkBufferCreateInfo buffer{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
            buffer.size = size; buffer.usage = usage; buffer.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            cubeCheck(vkCreateBuffer(mDevice, &buffer, nullptr, &result.buffer), "vkCreateBuffer(cube)");
            VkMemoryRequirements requirements{};
            vkGetBufferMemoryRequirements(mDevice, result.buffer, &requirements);
            VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
            allocation.allocationSize = requirements.size; allocation.memoryTypeIndex = memoryType(requirements.memoryTypeBits, required, preferred);
            result.flags = mMemoryProperties.memoryTypes[allocation.memoryTypeIndex].propertyFlags;
            cubeCheck(vkAllocateMemory(mDevice, &allocation, nullptr, &result.memory), "vkAllocateMemory(cube buffer)");
            cubeCheck(vkBindBufferMemory(mDevice, result.buffer, result.memory, 0), "vkBindBufferMemory(cube)");
        }

        void createImage(VkExtent2D extent, VkFormat format, VkImageUsageFlags usage, VkImageAspectFlags aspect,
            VkMemoryPropertyFlags preferred, Image& result)
        {
            VkImageCreateInfo image{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
            image.imageType = VK_IMAGE_TYPE_2D; image.extent = {extent.width, extent.height, 1};
            image.mipLevels = 1; image.arrayLayers = 1; image.format = format;
            image.tiling = VK_IMAGE_TILING_OPTIMAL; image.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
            image.usage = usage; image.samples = VK_SAMPLE_COUNT_1_BIT; image.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            cubeCheck(vkCreateImage(mDevice, &image, nullptr, &result.image), "vkCreateImage(cube)");
            VkMemoryRequirements requirements{};
            vkGetImageMemoryRequirements(mDevice, result.image, &requirements);
            VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
            allocation.allocationSize = requirements.size;
            allocation.memoryTypeIndex = memoryType(requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, preferred);
            cubeCheck(vkAllocateMemory(mDevice, &allocation, nullptr, &result.memory), "vkAllocateMemory(cube image)");
            cubeCheck(vkBindImageMemory(mDevice, result.image, result.memory, 0), "vkBindImageMemory(cube)");
            VkImageViewCreateInfo view{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
            view.image = result.image; view.viewType = VK_IMAGE_VIEW_TYPE_2D; view.format = format;
            view.subresourceRange = {aspect, 0, 1, 0, 1};
            cubeCheck(vkCreateImageView(mDevice, &view, nullptr, &result.view), "vkCreateImageView(cube)");
        }

        void destroyBuffer(Buffer& buffer)
        {
            if (buffer.buffer) vkDestroyBuffer(mDevice, buffer.buffer, nullptr);
            if (buffer.memory) vkFreeMemory(mDevice, buffer.memory, nullptr);
            buffer = {};
        }
        void destroyImage(Image& image)
        {
            if (image.view) vkDestroyImageView(mDevice, image.view, nullptr);
            if (image.image) vkDestroyImage(mDevice, image.image, nullptr);
            if (image.memory) vkFreeMemory(mDevice, image.memory, nullptr);
            image = {};
        }

        void releaseUpload()
        {
            if (mUploadFence) vkDestroyFence(mDevice, mUploadFence, nullptr);
            if (mUploadCommand) vkFreeCommandBuffers(mDevice, mUploadPool, 1, &mUploadCommand);
            destroyBuffer(mUploadStaging);
            mUploadFence = VK_NULL_HANDLE; mUploadCommand = VK_NULL_HANDLE; mUploadPool = VK_NULL_HANDLE;
        }

        void upload(VkQueue queue, uint32_t queueFamily, VkCommandPool pool, const uint8_t* pixels, size_t bytes)
        {
            // A single initialization-only staging allocation/submit. The retained geometry and
            // texture are device-local; steady frames only update a 64-byte push constant.
            const VkDeviceSize vertexBytes = sizeof(cubeVertices), indexBytes = sizeof(cubeIndices);
            const VkDeviceSize textureOffset = (vertexBytes + indexBytes + 3) & ~VkDeviceSize(3);
            mUploadPool = pool;
            auto& staging = mUploadStaging;
            auto& command = mUploadCommand;
            auto& fence = mUploadFence;
            bool submitted = false;
            try
            {
                createBuffer(textureOffset + bytes, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT,
                    VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, staging);
                void* mapping = nullptr;
                cubeCheck(vkMapMemory(mDevice, staging.memory, 0, VK_WHOLE_SIZE, 0, &mapping), "vkMapMemory(upload only)");
                std::memcpy(mapping, cubeVertices.data(), static_cast<size_t>(vertexBytes));
                std::memcpy(static_cast<uint8_t*>(mapping) + vertexBytes, cubeIndices.data(), static_cast<size_t>(indexBytes));
                std::memcpy(static_cast<uint8_t*>(mapping) + textureOffset, pixels, bytes);
                VkResult flushed = VK_SUCCESS;
                if (!(staging.flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))
                {
                    VkMappedMemoryRange range{VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE};
                    range.memory = staging.memory; range.offset = 0; range.size = VK_WHOLE_SIZE;
                    flushed = vkFlushMappedMemoryRanges(mDevice, 1, &range);
                }
                vkUnmapMemory(mDevice, staging.memory);
                cubeCheck(flushed, "vkFlushMappedMemoryRanges(upload)");
                VkCommandBufferAllocateInfo allocation{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
                allocation.commandPool = pool; allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY; allocation.commandBufferCount = 1;
                cubeCheck(vkAllocateCommandBuffers(mDevice, &allocation, &command), "vkAllocateCommandBuffers(upload)");
                VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
                begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
                cubeCheck(vkBeginCommandBuffer(command, &begin), "vkBeginCommandBuffer(upload)");
                VkImageMemoryBarrier texture{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
                texture.srcQueueFamilyIndex = texture.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
                texture.image = mTexture.image; texture.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
                texture.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED; texture.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
                texture.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
                vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0,
                    0, nullptr, 0, nullptr, 1, &texture);
                const VkBufferCopy vertexCopy{0, 0, vertexBytes}, indexCopy{vertexBytes, 0, indexBytes};
                vkCmdCopyBuffer(command, staging.buffer, mVertices.buffer, 1, &vertexCopy);
                vkCmdCopyBuffer(command, staging.buffer, mIndices.buffer, 1, &indexCopy);
                VkBufferImageCopy imageCopy{};
                imageCopy.bufferOffset = textureOffset;
                imageCopy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
                imageCopy.imageExtent = {textureSize, textureSize, 1};
                vkCmdCopyBufferToImage(command, staging.buffer, mTexture.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &imageCopy);
                VkBufferMemoryBarrier buffers[2]{};
                for (auto& barrier : buffers)
                {
                    barrier.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER;
                    barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
                    barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; barrier.offset = 0; barrier.size = VK_WHOLE_SIZE;
                }
                buffers[0].buffer = mVertices.buffer; buffers[0].dstAccessMask = VK_ACCESS_VERTEX_ATTRIBUTE_READ_BIT;
                buffers[1].buffer = mIndices.buffer; buffers[1].dstAccessMask = VK_ACCESS_INDEX_READ_BIT;
                texture.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; texture.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
                texture.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; texture.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
                vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT,
                    VK_PIPELINE_STAGE_VERTEX_INPUT_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0,
                    0, nullptr, 2, buffers, 1, &texture);
                cubeCheck(vkEndCommandBuffer(command), "vkEndCommandBuffer(upload)");
                VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
                cubeCheck(vkCreateFence(mDevice, &fenceInfo, nullptr, &fence), "vkCreateFence(upload)");
                VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
                submit.commandBufferCount = 1; submit.pCommandBuffers = &command;
                (void)queueFamily; // All upload resources remain on the caller's graphics queue.
                cubeCheck(vkQueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit(upload)");
                submitted = true;
                cubeCheck(vkWaitForFences(mDevice, 1, &fence, VK_TRUE, 1000000000ull), "vkWaitForFences(initial upload, 1s)");
            }
            catch (...)
            {
                // A timed-out submit still owns these resources. Retain them until the
                // owner quiesces the device and calls destroy(); no unbounded recovery wait.
                if (!submitted) releaseUpload();
                throw;
            }
            releaseUpload();
        }

        VkPhysicalDevice mPhysical = VK_NULL_HANDLE;
        VkDevice mDevice = VK_NULL_HANDLE;
        VkPhysicalDeviceMemoryProperties mMemoryProperties{};
        VkFormat mDepthFormat = VK_FORMAT_UNDEFINED;
        Buffer mVertices, mIndices;
        Buffer mUploadStaging;
        VkCommandBuffer mUploadCommand = VK_NULL_HANDLE;
        VkCommandPool mUploadPool = VK_NULL_HANDLE;
        VkFence mUploadFence = VK_NULL_HANDLE;
        Image mTexture;
        VkSampler mSampler = VK_NULL_HANDLE;
        VkDescriptorSetLayout mSetLayout = VK_NULL_HANDLE;
        VkDescriptorPool mDescriptorPool = VK_NULL_HANDLE;
        VkDescriptorSet mDescriptorSet = VK_NULL_HANDLE;
        VkPipelineLayout mPipelineLayout = VK_NULL_HANDLE;
        VkPipeline mPipeline = VK_NULL_HANDLE;
        std::vector<Image> mDepth;
    };
}
