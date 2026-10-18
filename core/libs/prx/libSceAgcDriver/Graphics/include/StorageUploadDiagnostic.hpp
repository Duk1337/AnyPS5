#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <vector>

namespace AgcDriver::Graphics::StorageUploadDiagnostic {
// Enable with APS5_STORAGE_UPLOAD_DIAGNOSTIC=1 (read once at process startup).
// Texture.cpp prints up to 20 identities and one overflow row every >=10 s of upload activity.
// Counts use existing transfer-site byte totals, including partial and alias copies, not allocation sizes.
// GPU clears have zero uploaded bytes; their logical surface extent remains in the descriptor identity.
// At >1024 identities the retained-only ranking is explicitly incomplete; overflow bytes stay exact.
// No additional guest-byte reads, collections, snapshots, GPU waits or cache changes are performed.
// Orthogonal observations, not inferred CPU modifications.
enum Evidence : std::uint32_t {
    Untracked = 1u << 0, MissingSnapshot = 1u << 1, PendingImage = 1u << 2,
    DccChanged = 1u << 3, AliasCandidate = 1u << 4, OverlapFlush = 1u << 5,
    BytesChanged = 1u << 6, BytesUnknown = 1u << 7, CpuStamped = 1u << 8,
    PendingRecorder = 1u << 9, CollectZero = 1u << 10, BytesEqual = 1u << 11
};
inline constexpr std::array<const char*, 12> EvidenceNames{
    "untracked", "missing-snapshot", "pending-image", "dcc-changed", "alias-candidate",
    "overlap-flush", "bytes-changed", "bytes-unknown", "cpu-stamped", "pending-recorder", "collect-zero", "bytes-equal"};
inline constexpr std::array<const char*, 9> ReasonNames{
    "first", "keys", "cpu", "untracked", "flushed", "store", "alias", "layer alias", "shadow"};
inline constexpr std::array<const char*, 4> PathNames{"clear", "direct", "cpu", "alias"};
// Descriptor identities coalesce recreated objects; no object pointers are retained.
using Key = std::array<std::uint64_t, 21>;
inline std::uint64_t UploadedBytes(std::size_t path, std::uint64_t bytes) { return path == 0 ? 0 : bytes; }
struct Traffic {
    std::uint64_t calls = 0, bytes = 0;
    void Add(std::uint64_t count) { ++calls; bytes += count; }
};
struct Totals {
    Traffic all;
    std::array<Traffic, PathNames.size()> paths{};
    std::array<Traffic, ReasonNames.size() + 1> reasons{};
    std::array<Traffic, EvidenceNames.size()> evidence{};
    void Add(std::size_t path, std::size_t reason, std::uint64_t bytes, std::uint32_t flags) {
        all.Add(bytes); paths.at(path).Add(bytes); reasons.at(reason).Add(bytes);
        for (std::size_t i = 0; i < evidence.size(); ++i)
            if ((flags & (1u << i)) != 0) evidence[i].Add(bytes);
    }
};
class Accounting {
public:
    static constexpr std::size_t Capacity = 1024, TopCount = 20;
    static constexpr double IntervalSeconds = 10.0;
    static bool Due(double elapsed) { return elapsed >= IntervalSeconds; }
    void Add(const Key& key, std::size_t path, std::size_t reason,
             std::uint64_t bytes, std::uint32_t flags) {
        if (path >= PathNames.size() || reason > ReasonNames.size())
            throw std::out_of_range("storage upload diagnostic category");
        total.Add(bytes);
        if (!rows.contains(key) && rows.size() == Capacity) {
            overflow.Add(path, reason, bytes, flags); return;
        }
        rows[key].Add(path, reason, bytes, flags);
    }
    std::vector<std::pair<Key, Totals>> Top() const {
        std::vector<std::pair<Key, Totals>> result(rows.begin(), rows.end());
        std::sort(result.begin(), result.end(), [](const auto& a, const auto& b) {
            return a.second.all.bytes != b.second.all.bytes
                ? a.second.all.bytes > b.second.all.bytes : a.first < b.first;
        });
        if (result.size() > TopCount) result.resize(TopCount);
        return result;
    }
    std::size_t Size() const { return rows.size(); }
    void Reset() { rows.clear(); total = {}; overflow = {}; }
    Traffic total;
    Totals overflow;
private:
    std::map<Key, Totals> rows;
};
}
