#pragma once
// CPU-only observation. No GPU queries; no rendering decisions depend on this state.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <mutex>
#include <memory>
#include <string>
#include <span>
#include <thread>
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
namespace CpuCost {
using U = std::uint64_t;
inline bool Enabled() noexcept { static const bool value = [] { const char* p=std::getenv("APS5_CPU_COSTS"); return p && p[0]=='1'; }(); return value; }
inline U Now() noexcept { return static_cast<U>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count()); }
struct Key { U lo=0,hi=0,bytes=0; bool operator==(const Key&) const = default; };
inline Key Digest(std::span<const std::byte> bytes) noexcept { Key k{14695981039346656037ull,7809847782465536322ull,bytes.size()}; for(auto b:bytes){auto v=std::to_integer<unsigned char>(b);k.lo=(k.lo^v)*1099511628211ull;k.hi=(k.hi^v)*14029467366897019727ull;} return k; }
template<class T> Key Digest(std::span<const T> values) noexcept { return Digest(std::as_bytes(values)); }
struct Origin { U present=0,submission=0,work=0,draw=0,shader=0,stage=0,phase=0; Key key{},runtimeKey{}; std::uint32_t queue=0xffffffffu; };
// Keep diagnostic context out of MinGW emulated TLS and its destructor machinery.
// Slots are process-lifetime and never reused: no thread-exit callback or allocator on the hot path.
inline std::atomic<U> presentEpoch{0},submissionEpoch{0},workSequence{0},contextDrops{0};
inline Origin* ThreadOrigin() noexcept {
    if(!Enabled())return nullptr;
    static const DWORD index=TlsAlloc();
    if(index==TLS_OUT_OF_INDEXES){contextDrops.fetch_add(1,std::memory_order_relaxed);return nullptr;}
    if(auto* p=static_cast<Origin*>(TlsGetValue(index)))return p;
    static std::array<Origin,512> slots{};
    static std::atomic<unsigned> used{0};
    const auto n=used.fetch_add(1,std::memory_order_relaxed);
    if(n>=slots.size()){contextDrops.fetch_add(1,std::memory_order_relaxed);return nullptr;}
    if(!TlsSetValue(index,&slots[n])){contextDrops.fetch_add(1,std::memory_order_relaxed);return nullptr;}
    return &slots[n];
}
inline Origin Capture() noexcept { Origin x{};if(auto* p=ThreadOrigin())x=*p;if(!x.work){x.present=presentEpoch.load(std::memory_order_relaxed);x.submission=submissionEpoch.load(std::memory_order_relaxed);}return x; }
struct Context { Origin old{};Origin* slot=nullptr;explicit Context(Origin x) noexcept {if(auto* p=ThreadOrigin()){slot=p;old=*p;*p=x;}}~Context(){if(slot)*slot=old;} };
inline Origin Work(std::uint32_t queue,U identity=0) noexcept {if(!Enabled())return {};auto x=Capture();x.present=presentEpoch.load(std::memory_order_relaxed);x.submission=submissionEpoch.load(std::memory_order_relaxed);x.work=identity?identity:workSequence.fetch_add(1,std::memory_order_relaxed)+1;x.queue=queue;return x;}
inline void SetQueue(std::uint32_t queue) noexcept {if(auto* p=ThreadOrigin())p->queue=queue;}
inline void SetShader(U shader) noexcept {if(auto* p=ThreadOrigin())p->shader=shader;}
enum class Op:std::uint32_t { DispatchPacket,ComputePrepare,ComputeCommit,ComputeRecipe,ComputeRecord,DrawPacket,DrawCommit,PrepJob,CommitJob,RecorderCommand,RecorderSubmit,QueueSubmit,QueuePresent,GraphicsLookup,GraphicsHit,GraphicsMiss,GraphicsPending,GraphicsPrivate,GraphicsCreate,ComputeCreate,ModuleLookup,ModuleMemoryHit,ModuleDiskHit,ModuleDiskMiss,ModuleBuild,ModuleWrite,ModuleWriteFail,PipelineLoad,PipelineSave,PipelineSaveFail,GpuAcquire,GpuWait,PresentReturn,TextureFailure,SamplerFailure,PrepareKey,PrepareFind,PreparePrecollect,PreparePresync,PrepareStageA,ResourceStageA,ResourceStageB,MemoryCompare,DescriptorCandidate,WarmReplayDone,DrawCommand,DispatchCommand,Count };
inline constexpr const char* Names[]={"dispatch_packet","compute_prepare","compute_commit","compute_recipe","compute_record","draw_packet","draw_commit","prep_job","commit_job","queue_submit_driver","recorder_submit","submission_epoch","queue_present","graphics_lookup","graphics_hit","graphics_miss","graphics_pending","graphics_private","graphics_create","compute_create","module_lookup","module_memory_hit","module_disk_hit","module_disk_miss","module_build","module_write","module_write_fail","pipeline_load","pipeline_save","pipeline_save_fail","gpu_acquire","gpu_wait","present_return","texture_failure","sampler_failure","prepare_key","prepare_find","prepare_precollect","prepare_presync","prepare_stage_a","resource_stage_a","resource_stage_b","memory_compare","descriptor_candidate","warm_replay_done","draw_command","dispatch_command"};
static_assert(std::size(Names)==static_cast<std::size_t>(Op::Count));
struct Row { bool used=false,dirty=false; Op op{}; std::uint32_t tid=0,queue=0; U count=0,total=0,max=0,failed=0,crossP=0,crossS=0,first=0,last=0; };
struct Event { Op op{}; std::uint32_t tid=0; Origin from{}; U start=0,end=0,pEnd=0,sEnd=0,failed=0,a=0,b=0,pStart=0,sStart=0; };
struct State {
 static constexpr std::size_t Slots=2048,Events=8192; static constexpr U ByteCap=16ull<<20;
 std::mutex mutex; std::array<Row,Slots> rows{}; std::array<Event,Events> events{}; std::array<Row,Slots> snapshot{}; std::array<Event,Events> pending{}; std::size_t begin=0,size=0; U rowDrops=0,eventDrops=0,bytes=0; bool capped=false; std::FILE* file=nullptr;
 void Line(const char* data,std::size_t n) noexcept { if(!file||capped)return; if(bytes+n>ByteCap-1024){const char* end="LIMIT output_cap_reached; subsequent records omitted; reject incomplete diagnostic interval\n";std::fputs(end,file);std::fflush(file);capped=true;return;}const auto written=std::fwrite(data,1,n,file);bytes+=written;if(written!=n){capped=true;std::fprintf(stderr,"[cpu-costs] output write failed; diagnostic data incomplete\n");} }
 State() { const char* path=std::getenv("APS5_CPU_COSTS_FILE"); if(!path||!*path)return; file=std::fopen(path,"wx"); if(!file)return; const char* h="CPU_COSTS v1 units=ns clock=steady wall_not_cpu; epochs=CPU_path_not_GPU_completion; fingerprints=dual64_not_shader_contents; cap=16777216\n";Line(h,std::char_traits<char>::length(h)); LARGE_INTEGER q{},f{};FILETIME utc{};QueryPerformanceCounter(&q);QueryPerformanceFrequency(&f);GetSystemTimePreciseAsFileTime(&utc);char anchor[256];int n=std::snprintf(anchor,sizeof(anchor),"ANCHOR steady_ns=%llu qpc=%llu frequency=%llu utc_filetime=%llu\n",Now(),static_cast<U>(q.QuadPart),static_cast<U>(f.QuadPart),(U(utc.dwHighDateTime)<<32)|utc.dwLowDateTime);Line(anchor,n);std::thread([this]{Run();}).detach(); }
 void Run() noexcept { SetThreadDescription(GetCurrentThread(),L"AgcCpuCosts"); for(;;){std::this_thread::sleep_for(std::chrono::seconds(1));std::size_t n=0;U rd=0,ed=0;{std::lock_guard lock(mutex);snapshot=rows;for(auto& r:rows)r.dirty=false;while(size){pending[n++]=events[begin];begin=(begin+1)%Events;--size;}rd=rowDrops;ed=eventDrops;} char line[768];const U at=Now();int len=std::snprintf(line,sizeof(line),"SNAP t=%llu present=%llu submission=%llu row_drops=%llu event_drops=%llu context_drops=%llu\n",at,presentEpoch.load(),submissionEpoch.load(),rd,ed,contextDrops.load());Line(line,std::min<std::size_t>(std::max(len,0),sizeof(line)-1));for(const auto& r:snapshot){if(!r.used||!r.dirty)continue;len=std::snprintf(line,sizeof(line),"SUM t=%llu op=%s tid=%u queue=%u count=%llu wall_ns=%llu max_ns=%llu failed=%llu cross_present=%llu cross_submit=%llu first=%llu last=%llu\n",at,Names[static_cast<unsigned>(r.op)],r.tid,r.queue,r.count,r.total,r.max,r.failed,r.crossP,r.crossS,r.first,r.last);Line(line,std::min<std::size_t>(std::max(len,0),sizeof(line)-1));}for(std::size_t i=0;i<n;++i){const auto&e=pending[i];len=std::snprintf(line,sizeof(line),"EVENT op=%s tid=%u queue=%u work=%llu key=%016llx%016llx key_bytes=%llu runtime=%016llx%016llx draw=%llu shader=%llu stage=%llu phase=%llu start=%llu end=%llu p_origin=%llu p_start=%llu p_end=%llu s_origin=%llu s_start=%llu s_end=%llu failed=%llu a=%llu b=%llu\n",Names[static_cast<unsigned>(e.op)],e.tid,e.from.queue,e.from.work,e.from.key.lo,e.from.key.hi,e.from.key.bytes,e.from.runtimeKey.lo,e.from.runtimeKey.hi,e.from.draw,e.from.shader,e.from.stage,e.from.phase,e.start,e.end,e.from.present,e.pStart,e.pEnd,e.from.submission,e.sStart,e.sEnd,e.failed,e.a,e.b);Line(line,std::min<std::size_t>(std::max(len,0),sizeof(line)-1));}if(file)std::fflush(file);if(capped)return;}}
};
inline State* Get() noexcept {static State* state=[]() noexcept -> State* {try{return new State;}catch(...){return nullptr;}}();return state;}
inline void Record(Op op,U start,U end,Origin from,bool failed=false,bool detail=false,U a=0,U b=0,U pStart=~U{0},U sStart=~U{0}) noexcept {
 if(!Enabled())return;auto* s=Get();if(!s)return;const auto tid=static_cast<std::uint32_t>(GetCurrentThreadId());const U pe=presentEpoch.load(std::memory_order_relaxed),se=submissionEpoch.load(std::memory_order_relaxed);std::lock_guard lock(s->mutex);const auto hash=(U(tid)*2654435761ull+U(from.queue)*97+static_cast<unsigned>(op))%State::Slots;bool found=false;for(std::size_t i=0;i<State::Slots;++i){auto&r=s->rows[(hash+i)%State::Slots];if(!r.used||(r.tid==tid&&r.queue==from.queue&&r.op==op)){if(!r.used){r.used=true;r.op=op;r.tid=tid;r.queue=from.queue;r.first=start;}r.dirty=true;++r.count;r.total+=end-start;r.max=std::max(r.max,end-start);r.last=end;r.failed+=failed;r.crossP+=from.present!=pe;r.crossS+=from.submission!=se;found=true;break;}}if(!found)++s->rowDrops;// Only these two output categories aggregate fast successes; missing detail is not missing activity.
 const bool submissionDetail = op==Op::RecorderCommand || op==Op::QueueSubmit;
 const bool emitDetail = submissionDetail ? (failed || end-start>=50000000ull) : detail;
 if(emitDetail){if(s->size<State::Events){s->events[(s->begin+s->size)%State::Events]={op,tid,from,start,end,pe,se,failed,a,b,pStart==~U{0}?pe:pStart,sStart==~U{0}?se:sStart};++s->size;}else ++s->eventDrops;}
}
struct Scope { Op op; Origin from{}; U start=0,pStart=0,sStart=0; int exceptions=0; bool detail=false; explicit Scope(Op op,bool detail=false):op(op),detail(detail){if(Enabled()){from=Capture();start=Now();pStart=presentEpoch.load(std::memory_order_relaxed);sStart=submissionEpoch.load(std::memory_order_relaxed);exceptions=std::uncaught_exceptions();}} ~Scope() noexcept {if(start){const auto end=Now();Record(op,start,end,from,std::uncaught_exceptions()>exceptions,detail || end-start>=50000000ull,0,0,pStart,sStart);}} Scope(const Scope&)=delete; Scope&operator=(const Scope&)=delete; };
inline void Note(Op op,bool detail=false,U a=0,U b=0) noexcept {if(!Enabled())return;const auto now=Now();Record(op,now,now,Capture(),false,detail,a,b);}
inline void KeyNote(Op op,Key key,bool detail=true,U a=0,U b=0) noexcept {if(!Enabled())return;auto x=Capture();x.key=key;const auto now=Now();Record(op,now,now,x,false,detail,a,b);}
struct Present {int exceptions=std::uncaught_exceptions(); ~Present() noexcept {if(Enabled()&&exceptions==std::uncaught_exceptions()){presentEpoch.fetch_add(1,std::memory_order_relaxed);Note(Op::PresentReturn,true);}}};
inline void Submitted(U serial,U queue) noexcept {if(!Enabled())return;submissionEpoch.fetch_add(1,std::memory_order_relaxed);Note(Op::QueueSubmit,true,serial,queue);}
inline void Descriptor(Op op,std::span<const std::uint32_t> words,U decodedA,U decodedB) noexcept {if(!Enabled())return;static std::atomic<unsigned> emitted{0};const bool detail=emitted.fetch_add(1,std::memory_order_relaxed)<64;KeyNote(op,Digest(words),detail,decodedA,decodedB);}
}
