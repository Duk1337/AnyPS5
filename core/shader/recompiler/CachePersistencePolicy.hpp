#pragma once
#include <cstdlib>
#include <cstring>
#include <stdexcept>
namespace ShaderRecompiler::CachePersistence {
// Persistence-only policy. This flag is not a shader-key or rendering option.
// Unset/0 retains the baseline; 1 reads existing caches without disk mutation.
inline bool ReadOnly() {
    static const bool enabled = [] {
        const char* value = std::getenv("ANYPS5_CACHE_READ_ONLY");
        if (!value || std::strcmp(value, "0") == 0) return false;
        if (std::strcmp(value, "1") == 0) return true;
        throw std::invalid_argument("ANYPS5_CACHE_READ_ONLY must be unset, 0 or 1");
    }();
    return enabled;
}
}
