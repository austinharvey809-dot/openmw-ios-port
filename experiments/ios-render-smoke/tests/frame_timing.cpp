// SPDX-License-Identifier: GPL-3.0-or-later
#include "../src/FrameTiming.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>

void require(bool condition)
{
    if (!condition) { std::fputs("FrameTiming test failed\n", stderr); std::exit(1); }
}
bool near(double a, double b) { return std::abs(a - b) < 0.00001; }

int main()
{
    smoke::FrameTiming timing;
    timing.reset(10);
    require(near(timing.callbackHz(10), 0) && near(timing.cpuMeanMs(), 0));
    timing.add({10.0, 10.004, 1, 2, 0.5, true});
    timing.add({10.04, 10.046, 2, 3, 1, false});
    timing.add({10.10, 10.108, 3, 4, 1.5, true});
    require(near(timing.callbackHz(10.2), 15));
    require(near(timing.presentsPerSecond(10.2), 10));
    require(near(timing.cpuMeanMs(), 6) && near(timing.cpuMaxMs(), 8));
    require(near(timing.intervalMeanMs(), 50) && near(timing.intervalMaxMs(), 60));
    require(near(timing.presentIntervalMaxMs(), 104));
    require(timing.slowIntervals() == 1 && timing.skipped() == 1);
    require(near(timing.fenceMeanMs(), 2) && near(timing.acquireMeanMs(), 3) && near(timing.presentMeanMs(), 1));
    // Suspension/reset excludes the background interval; invalid samples add nothing.
    timing.reset(100);
    timing.add({99, 100, 0, 0, 0, true});
    timing.add({100, 99, 0, 0, 0, true});
    require(near(timing.callbackHz(101), 0));
    timing.add({100, 100.002, 0, 0, 0, true});
    require(near(timing.intervalMaxMs(), 0) && timing.slowIntervals() == 0);
    require(near(timing.cpuMeanMs(), 2) && near(timing.presentsPerSecond(101), 1));
    std::puts("FrameTiming tests passed");
}
