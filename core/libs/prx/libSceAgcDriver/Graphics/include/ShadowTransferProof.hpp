#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <vector>

namespace AgcDriver::Graphics::ShadowTransferProof {
// Metadata only. No guest reads, GPU queries, waits, or transfer decisions.
// Slab-wide mutation serials conservatively change on every granted destination
// and MarkShadowed; even a same-byte rewrite is a different provenance.
inline bool Enabled() {
    static const bool enabled = [] {
        const char* value = std::getenv("APS5_SHADOW_TRANSFER_PROOF");
        return value != nullptr && std::strcmp(value, "1") == 0;
    }();
    return enabled;
}
inline std::uint64_t NewId() {
    if (!Enabled()) return 0;
    static std::atomic<std::uint64_t> next{1};
    auto value = next.load(std::memory_order_relaxed);
    while (value != std::numeric_limits<std::uint64_t>::max()) {
        if (next.compare_exchange_weak(value, value + 1, std::memory_order_relaxed)) return value;
    }
    return 0; // Permanent fail-closed saturation, never recycle identities.
}
using Token = std::array<std::uint64_t, 16>;
using Plan = std::vector<Token>;
// Destination version, destination write serial, recorder identity, open batch identity,
// forget serial, allocation generation, unwatch serial, pending serial, DCC interpretation.
using Scope = std::array<std::uint64_t, 9>;
enum class Outcome : std::size_t {
    First, Equivalent, SourceChanged, DestinationChanged, ScopeChanged,
    Pending, Mixed, PlanLimit, TableLimit, Discard, NoRecorder, Unknown, Count
};
inline constexpr std::array<const char*, static_cast<std::size_t>(Outcome::Count)> Names{
    "first", "ordered-equivalent", "source-changed", "destination-changed", "scope-changed",
    "pending", "mixed-import", "plan-limit", "table-limit", "discard", "no-recorder", "unknown"};
struct Result { Outcome outcome; bool repeatedSource = false; };
class History {
public:
    static constexpr std::size_t MaxDestinations = 128, MaxTokens = 128;
    Result Observe(std::uint64_t image, const Plan& plan, const Scope& current,
                   bool allShadow, bool pending, bool discard, bool known) {
        const auto forget = [&](Outcome outcome) { entries.erase(image); return Result{outcome, false}; };
        if (!allShadow) return forget(Outcome::Mixed);
        if (plan.size() > MaxTokens) return forget(Outcome::PlanLimit);
        if (image == 0 || plan.empty() || !known || (current[4] & 1u) != 0) return forget(Outcome::Unknown);
        if (current[2] == 0 || current[3] == 0) return forget(Outcome::NoRecorder);
        const auto previous = entries.find(image);
        Result result{Outcome::First, false};
        if (previous != entries.end()) {
            result.repeatedSource = previous->second.plan == plan;
            if (!result.repeatedSource) result.outcome = Outcome::SourceChanged;
            else if (previous->second.scope[0] != current[0] || previous->second.scope[1] != current[1]) result.outcome = Outcome::DestinationChanged;
            else if (!std::equal(current.begin() + 2, current.end(), previous->second.scope.begin() + 2)) result.outcome = Outcome::ScopeChanged;
            else result.outcome = Outcome::Equivalent;
        }
        if (pending) result.outcome = Outcome::Pending;
        if (discard) result.outcome = Outcome::Discard;
        if (previous == entries.end() && entries.size() == MaxDestinations) return {Outcome::TableLimit, result.repeatedSource};
        if (current[0] == std::numeric_limits<std::uint64_t>::max()) return forget(Outcome::Unknown);
        auto next = current;
        ++next[0]; // uploadWindows' caller increments version after the real upload.
        entries[image] = {plan, next};
        return result;
    }
    void Forget(std::uint64_t image) { entries.erase(image); }
    std::size_t Size() const { return entries.size(); }
private:
    struct Entry { Plan plan; Scope scope; };
    std::map<std::uint64_t, Entry> entries;
};
}
