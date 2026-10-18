#include "prx/libSceAgcDriver/Graphics/include/StorageUploadDiagnostic.hpp"
#include <iostream>
#include <stdexcept>
using namespace AgcDriver::Graphics::StorageUploadDiagnostic;
void Check(bool value) { if (!value) throw std::runtime_error("diagnostic accounting assertion"); }
int main() {
    try {
        Check(UploadedBytes(0, 1ull << 33) == 0);
        Check(UploadedBytes(1, 65536) == 65536 && UploadedBytes(3, 4096) == 4096);
        Accounting a;
        Key k{}; k[0] = 0x1238ba0000ull; k[3] = 1024;
        a.Add(k, 1, 3, 65536, Untracked | MissingSnapshot | BytesUnknown);
        a.Add(k, 3, 6, 4096, AliasCandidate | PendingImage);
        auto other = k; other[3] = 2048;
        a.Add(other, 2, 2, 1ull << 33, BytesChanged | CpuStamped);
        auto top = a.Top();
        Check(top.size() == 2 && top[0].first == other && top[1].second.all.bytes == 69632);
        Check(top[1].second.paths[1].bytes == 65536 && top[1].second.paths[3].bytes == 4096);
        Check(top[1].second.reasons[3].calls == 1 && top[1].second.evidence[0].bytes == 65536);
        Check(top[1].second.evidence[6].calls == 0 && top[1].second.evidence[7].calls == 1);
        Check(top[0].second.evidence[6].calls == 1 && top[0].second.evidence[7].calls == 0);
        // A zero collection over covered memory is distinct from an uncovered range.
        auto failed = k; failed[2] = 123;
        a.Add(failed, 1, 3, 1, CollectZero | BytesUnknown);
        Check(a.Top().back().second.evidence[0].calls == 0);
        Check(a.Top().back().second.evidence[10].calls == 1);
        // Every identity field matters, including view and component swizzle.
        for (std::size_t i = 1; i < k.size(); ++i) {
            auto distinct = k; distinct[i] += 777;
            a.Add(distinct, 0, 9, 1, BytesEqual);
        }
        Check(a.Size() == 23);
        a.Reset();
        Check(a.Size() == 0 && a.total.calls == 0 && a.Top().empty());
        for (std::size_t i = 0; i < Accounting::Capacity; ++i) {
            Key row{}; row[0] = i;
            a.Add(row, i % 4, i % 10, i + 1, (1u << EvidenceNames.size()) - 1);
        }
        Key excess{}; excess[0] = 9000;
        a.Add(excess, 1, 3, 999999, Untracked);
        Key retained{}; retained[0] = 0;
        a.Add(retained, 1, 0, 20000, DccChanged | PendingRecorder);
        Check(a.Size() == 1024 && a.overflow.all.calls == 1 && a.overflow.all.bytes == 999999);
        Check(a.total.bytes == (1024ull * 1025 / 2) + 999999 + 20000);
        Check(a.total.calls == 1026 && a.Top().size() == 20 && a.Top()[0].first == retained);
        Check(a.Top()[0].second.evidence[9].calls == 2);
        const auto before = a.total.calls;
        try { a.Add(k, 4, 0, 1, 0); Check(false); } catch (const std::out_of_range&) {}
        Check(a.total.calls == before);
        Check(!Accounting::Due(9.999) && Accounting::Due(10.0));
        a.Reset();
        Check(a.overflow.all.bytes == 0 && a.total.bytes == 0);
        a.Add(other, 0, 0, 42, 0); a.Add(k, 0, 0, 42, 0);
        Check(a.Top()[0].first == k);
        std::cout << "storage upload diagnostic accounting: passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
