// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cstdint>

namespace smoke
{
    struct FrameSample
    {
        double start = 0, end = 0;
        double fenceMs = 0, acquireMs = 0, presentMs = 0;
        bool presented = false;
    };

    // CPU monotonic-clock measurements only. No GPU/scanout FPS is inferred.
    class FrameTiming
    {
    public:
        void reset(double now)
        {
            *this = FrameTiming{};
            mStart = now;
        }

        void add(const FrameSample& sample)
        {
            if (sample.start < mStart || sample.end < sample.start)
                return;
            if (mCallbacks)
            {
                const double interval = (sample.start - mLastCallback) * 1000.0;
                mIntervalSum += interval;
                mIntervalMax = std::max(mIntervalMax, interval);
                if (interval > 50.0) ++mSlowIntervals; // >1.5 requested 30 Hz periods
            }
            mLastCallback = sample.start;
            ++mCallbacks;
            const double cpu = (sample.end - sample.start) * 1000.0;
            mCpuSum += cpu;
            mCpuMax = std::max(mCpuMax, cpu);
            mFenceSum += sample.fenceMs;
            mAcquireSum += sample.acquireMs;
            mPresentSum += sample.presentMs;
            if (sample.presented)
            {
                if (mPresents)
                    mPresentIntervalMax = std::max(mPresentIntervalMax, (sample.end - mLastPresent) * 1000.0);
                mLastPresent = sample.end;
                ++mPresents;
            }
        }

        double elapsed(double now) const { return std::max(0.0, now - mStart); }
        double callbackHz(double now) const { return rate(mCallbacks, now); }
        double presentsPerSecond(double now) const { return rate(mPresents, now); }
        double cpuMeanMs() const { return mean(mCpuSum); }
        double cpuMaxMs() const { return mCpuMax; }
        double intervalMeanMs() const { return mCallbacks > 1 ? mIntervalSum / (mCallbacks - 1) : 0; }
        double intervalMaxMs() const { return mIntervalMax; }
        double presentIntervalMaxMs() const { return mPresentIntervalMax; }
        double fenceMeanMs() const { return mean(mFenceSum); }
        double acquireMeanMs() const { return mean(mAcquireSum); }
        double presentMeanMs() const { return mean(mPresentSum); }
        uint64_t skipped() const { return mCallbacks - mPresents; }
        uint64_t slowIntervals() const { return mSlowIntervals; }

    private:
        double rate(uint64_t count, double now) const { return elapsed(now) > 0 ? count / elapsed(now) : 0; }
        double mean(double sum) const { return mCallbacks ? sum / mCallbacks : 0; }
        double mStart = 0, mLastCallback = 0, mLastPresent = 0;
        double mCpuSum = 0, mCpuMax = 0, mIntervalSum = 0, mIntervalMax = 0, mPresentIntervalMax = 0;
        double mFenceSum = 0, mAcquireSum = 0, mPresentSum = 0;
        uint64_t mCallbacks = 0, mPresents = 0, mSlowIntervals = 0;
    };
}
