#include "prx/libSceAgcDriver/Graphics/include/ShadowTransferProof.hpp"
#include <iostream>
#include <stdexcept>
using namespace AgcDriver::Graphics::ShadowTransferProof;
void Check(bool value) { if (!value) throw std::runtime_error("shadow proof assertion"); }
int main() {
 try {
    History h; Plan p{{1,0,65536,0,77,99}};
    Scope s{0,0,1,1,2,1,1,1,0};
    Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::First);
    ++s[0]; auto repeat=h.Observe(1,p,s,true,false,false,true);
    Check(repeat.outcome == Outcome::Equivalent && repeat.repeatedSource);
    ++s[0]; ++s[1];
    Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::DestinationChanged);
    ++s[0]; ++p[0][5]; // Same slab, rewritten in place.
    Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::SourceChanged);
    for (std::size_t i=2;i<s.size();++i) {
        ++s[0]; s[i]+=2;
        Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::ScopeChanged);
    }
    ++s[0]; Check(h.Observe(1,p,s,true,true,false,true).outcome == Outcome::Pending);
    ++s[0]; Check(h.Observe(1,p,s,true,false,true,true).outcome == Outcome::Discard);
    ++s[0]; p.push_back({3,0,0,0,1,0,0,1,0,0,0,64,64,1});
    Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::SourceChanged);
    ++s[0]; p[0][2]=32768; // Partial selection never stands in for a larger plan.
    Check(h.Observe(1,p,s,true,false,false,true).outcome == Outcome::SourceChanged);
    Check(h.Observe(1,p,s,false,false,false,true).outcome == Outcome::Mixed && h.Size()==0);
    Check(h.Observe(1,p,s,true,false,false,false).outcome == Outcome::Unknown);
    auto odd=s; odd[4]|=1;
    Check(h.Observe(1,p,odd,true,false,false,true).outcome == Outcome::Unknown);
    auto absent=s; absent[2]=0;
    Check(h.Observe(1,p,absent,true,false,false,true).outcome == Outcome::NoRecorder);
    absent=s; absent[3]=0;
    Check(h.Observe(1,p,absent,true,false,false,true).outcome == Outcome::NoRecorder);
    Plan big(History::MaxTokens+1);
    Check(h.Observe(1,big,s,true,false,false,true).outcome == Outcome::PlanLimit);
    for(std::uint64_t id=1;id<=History::MaxDestinations;++id) h.Observe(id,p,s,true,false,false,true);
    Check(h.Size()==History::MaxDestinations);
    Check(h.Observe(999,p,s,true,false,false,true).outcome == Outcome::TableLimit);
    h.Forget(1); Check(h.Size()==History::MaxDestinations-1);
    Check(h.Observe(999,p,s,true,false,false,true).outcome == Outcome::First);
    std::cout<<"shadow transfer proof metadata tests passed\n"; return 0;
 } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
