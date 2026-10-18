#ifndef CORE_LIBS_PRX_LIBSCEAGCDRIVER_EXECUTION_INCLUDE_DRIVER_WORKERAFFINITY_HPP
#define CORE_LIBS_PRX_LIBSCEAGCDRIVER_EXECUTION_INCLUDE_DRIVER_WORKERAFFINITY_HPP

#include <cstdint>

namespace AgcDriver::DriverDetail {

std::uint64_t WorkerAffinityMask();

void PinWorkerThread(const char* role);

// A thread name (ASCII) the in-process sampler (APS5_SAMPLE_THREADS) and debuggers select the thread by.
void NameWorkerThread(const char* name);

}

#endif
