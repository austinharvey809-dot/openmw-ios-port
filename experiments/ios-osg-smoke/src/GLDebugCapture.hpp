#pragma once
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <array>
#include <atomic>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

// Temporary diagnostics only. Own this object until after its EGL context is
// destroyed. All GL entry/exit operations run on the existing rendering thread.
class GLDebugCapture {
public:
    enum class Phase { BeforeOSG, Initialization, Frame, ClearOnly };
    struct Record {
        GLenum source, type, severity;
        GLuint id;
        Phase phase;
        unsigned long long frame;
        size_t length;
    };
    static constexpr size_t RecordLimit = 64;
    static constexpr GLint MessageLimit = 16384;
private:
    PFNGLDEBUGMESSAGECALLBACKKHRPROC callbackProc = nullptr;
    EGLDisplay ownerDisplay = EGL_NO_DISPLAY;
    EGLContext ownerContext = EGL_NO_CONTEXT;
    bool configured = false, installed = false;
    GLboolean priorOutput = GL_FALSE, priorSynchronous = GL_FALSE;
    std::array<Record, RecordLimit> records{};
    std::vector<char> bytes;
    size_t stride = 0, count = 0, flushed = 0, dropped = 0, reportedDrops = 0;
    Phase phase = Phase::BeforeOSG;
    unsigned long long frame = 0;
    std::mutex mutex;
    std::atomic<unsigned> callbackFailures{0};
    unsigned reportedFailures = 0;

    static void GL_APIENTRY capture(GLenum source, GLenum type, GLuint id, GLenum severity,
                                   GLsizei length, const GLchar* message, const void* user) noexcept {
        auto* self = static_cast<GLDebugCapture*>(const_cast<void*>(user));
        if (!self) return;
        try {
            std::lock_guard<std::mutex> lock(self->mutex);
            if (!message || length < 0 || size_t(length) >= self->stride || self->count == RecordLimit) {
                ++self->dropped;
                return;
            }
            const size_t index = self->count;
            std::memcpy(self->bytes.data() + index * self->stride, message, size_t(length));
            self->records[index] = {source, type, severity, id, self->phase, self->frame, size_t(length)};
            ++self->count;
        } catch (...) {
            // Never unwind through the driver. No allocation, logging, GL or EGL
            // calls occur in this callback, including the exception path.
            self->callbackFailures.fetch_add(1, std::memory_order_relaxed);
        }
    }
    bool ownsCurrentContext() const {
        return ownerContext != EGL_NO_CONTEXT && eglGetCurrentContext() == ownerContext &&
               eglGetCurrentDisplay() == ownerDisplay;
    }
public:
    GLDebugCapture() = default;
    GLDebugCapture(const GLDebugCapture&) = delete;
    GLDebugCapture& operator=(const GLDebugCapture&) = delete;
    // No GL calls in the destructor: Renderer explicitly detaches while current,
    // or destroys the context before this member's callback storage is released.
    bool active() const { return installed; }

    std::string configure(bool advertised, EGLDisplay display, EGLContext context) {
        if (!advertised) return "KHR_debug skipped: runtime GL_KHR_debug is not advertised";
        ownerDisplay = display; ownerContext = context;
        if (!ownsCurrentContext()) return "KHR_debug skipped: owning ANGLE context is not current";
        callbackProc = reinterpret_cast<PFNGLDEBUGMESSAGECALLBACKKHRPROC>(eglGetProcAddress("glDebugMessageCallbackKHR"));
        if (!callbackProc) return "KHR_debug skipped: ANGLE glDebugMessageCallbackKHR is unavailable";
        GLint maximum = 0;
        glGetIntegerv(GL_MAX_DEBUG_MESSAGE_LENGTH_KHR, &maximum);
        if (maximum <= 0 || maximum > MessageLimit)
            return "KHR_debug skipped: driver message length exceeds the bounded capture budget or is invalid";
        stride = size_t(maximum) + 1;
        try { bytes.resize(RecordLimit * stride); }
        catch (...) { return "KHR_debug skipped: capture buffer allocation failed"; }
        configured = true;
        return attach();
    }
    std::string attach() {
        if (!configured || installed) return "";
        if (!ownsCurrentContext()) return "KHR_debug deferred: owning ANGLE context is not current";
        priorOutput = glIsEnabled(GL_DEBUG_OUTPUT_KHR);
        priorSynchronous = glIsEnabled(GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);
        glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);
        callbackProc(&capture, this);
        installed = true;
        glEnable(GL_DEBUG_OUTPUT_KHR);
        return "KHR_debug registered: synchronous capture; existing driver message filters retained";
    }
    std::string detach(const char* reason) {
        if (!installed) return "";
        if (!ownsCurrentContext())
            return "KHR_debug cleanup deferred to context destruction: owning context is not current";
        callbackProc(nullptr, nullptr);
        installed = false;
        if (priorSynchronous) glEnable(GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);
        else glDisable(GL_DEBUG_OUTPUT_SYNCHRONOUS_KHR);
        if (priorOutput) glEnable(GL_DEBUG_OUTPUT_KHR);
        else glDisable(GL_DEBUG_OUTPUT_KHR);
        return std::string("KHR_debug deregistered: ") + reason + "; prior debug enable states restored";
    }
    void setPhase(Phase value, unsigned long long number = 0) {
        std::lock_guard<std::mutex> lock(mutex);
        phase = value; frame = number;
    }
    static const char* phaseName(Phase value) {
        switch (value) {
            case Phase::BeforeOSG: return "before OSG construction";
            case Phase::Initialization: return "OSG initialization";
            case Phase::Frame: return "OSG rendered frame";
            case Phase::ClearOnly: return "clear-only (completed OSG frame count)";
        }
        return "unknown";
    }
    template<class Writer, class Status> void drain(Writer write, Status status, bool final = false) {
        size_t available, lost;
        {
            std::lock_guard<std::mutex> lock(mutex);
            available = count; lost = dropped;
        }
        // Published slots are immutable. Formatting/file I/O is outside both
        // the callback and its lock; subsequent callbacks only append new slots.
        while (flushed < available) {
            const size_t index = flushed++;
            write(records[index], bytes.data() + index * stride);
        }
        // Report loss once initially and update totals at detach, rather than
        // flooding the file every callback if clear-only rendering lasts longer.
        if (lost != reportedDrops && (reportedDrops == 0 || final)) {
            reportedDrops = lost;
            status("KHR_debug capture loss: " + std::to_string(lost) +
                   " messages dropped (64-record window limit or invalid/oversized message); OSG checks remain enabled");
        }
        const unsigned failures = callbackFailures.load(std::memory_order_relaxed);
        if (failures != reportedFailures && (reportedFailures == 0 || final)) {
            reportedFailures = failures;
            status("KHR_debug callback failures: " + std::to_string(failures));
        }
    }
};
