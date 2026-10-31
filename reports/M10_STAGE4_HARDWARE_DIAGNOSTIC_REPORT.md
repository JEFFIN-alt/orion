# M10 Stage 4 — Windows memory diagnosis and inference recovery

**Decision: defer live synthesis.** Windows raised its low-physical-memory notification during a cold model load. The monitor stopped the dedicated Orion worker as instructed. At that point the machine still had 2,218 MiB of free VRAM and 8,808 MiB of commit headroom. Keep the system-managed pagefile and automatic GPU placement. The first opportunity is to free physical RAM by saving and closing user-selected applications. The isolated Orion database also needs a separately approved service restart and claim reset before another proposal can execute.

## Hardware and current memory

Snapshot on 2026-10-31 at approximately 12:11–12:12 IST. Windows 11 Home Single Language build 26300, Core i5-12450H, 8 GiB installed RAM, 7,832.5 MiB OS-visible, 139.4 GiB free on C:, RTX 2050 with 4,096 MiB VRAM and driver 616.92. Python 3.12.10, Ollama 0.40.13.

| Windows reading | Measured value | Interpretation |
|---|---:|---|
| Available physical RAM | 755 MiB at first performance-counter reading, 858–908 MiB over five subsequent samples | Below 1 GiB throughout these samples, with the model unloaded |
| Committed / limit / headroom | 14.22 / 24.65 / 10.43 GiB | Physical memory was much tighter than commit |
| Pagefile on C: | 17,408 MiB allocated, 1,200 MiB used, 1,497 MiB peak | Automatic management enabled, no explicit initial/maximum size returned |
| Kernel nonpaged pool | 969 MiB | Resident kernel allocations. One snapshot cannot identify a leak |
| Memory Compression working set | 602.3 MiB | Windows is maintaining a resident compression store. Its logical uncompressed size and compression ratio were unavailable. The management query did not return a policy flag |
| Paging activity | Five samples: 5,338 / 184 / 11 / 0 / 761 pages read in per second, 1,133 / 23 / 7 / 0 / 49 read operations per second | Bursty hard page-ins during diagnostics. Pages written out and page-write operations were zero in all five samples. Reads can include mapped files. These counters cannot attribute the traffic to pagefile reads or reconstruct the earlier failure |

**Pagefile decision.** Retain automatic management with the current allocation. No fixed minimum or maximum is proposed. The pagefile was enabled, had ample capacity, and the failed load retained several GiB of commit headroom. Enlarging it would not supply the resident RAM Windows was requesting.

## Largest processes

One process snapshot, sorted by working set. Private bytes measure committed private virtual memory and can exceed the resident working set. Shared resident pages can appear in several processes. Working-set totals are indicative footprints, not guaranteed RAM savings.

| Rank | Process | PID | Working set MiB | Private MiB | Role and potential impact of closing |
|---:|---|---:|---:|---:|---|
| 1 | Memory Compression | 4052 | 602.3 | 4.0 | Windows memory manager. Leave under OS control |
| 2 | ChatGPT | 12812 | 491.9 | 619.7 | User-facing desktop workflow. Closure could interrupt this session or lose drafts |
| 3 | ChatGPT Classic | 18156 | 314.3 | 432.6 | Separate user app. Candidate only if the CEO confirms its conversations and drafts are saved |
| 4 | ChatGPT | 19012 | 230.7 | 316.5 | Same application family. Closing a helper can disrupt active work |
| 5 | MsMpEng | 7012 | 212.1 | 344.1 | Windows antimalware service. Preserve protection |
| 6 | firefox | 13800 | 200.8 | 315.8 | Browser. Closing tabs/windows can interrupt sessions, forms or downloads |
| 7 | PhoneExperienceHost | 12788 | 148.0 | 85.6 | Windows phone integration. Optional for Orion, potentially in use for calls or notifications |
| 8 | codex | 19544 | 136.8 | 149.7 | Active engineering workflow. Closure could interrupt this task |
| 9 | firefox | 22512 | 114.2 | 348.2 | Browser process. Use the browser UI for any approved closure |
| 10 | explorer | 11896 | 113.9 | 174.6 | Windows desktop shell and file operations. Leave running |

The ten largest **by private MiB**, in order, were ChatGPT 12812 (619.7), msedgewebview2 16488 (601.6), ChatGPT Classic 18156 (432.6), firefox 22512 (348.2), MsMpEng 7012 (344.1), firefox 24688 (331.7), ChatGPT 19012 (316.5), firefox 13800 (315.8), ChatGPT 19376 (299.7), and dwm 1960 (273.2). WebView2 can belong to several apps. Neither a private-byte ranking nor a process name establishes which windows the user can safely close.

Grouped working sets were about 1,315 MiB for 14 ChatGPT processes, 1,261 MiB for 90 Windows service hosts, 781 MiB for 13 Firefox processes, 604 MiB for 18 WebView2 processes, and 560 MiB for six ChatGPT Classic processes. These are **current** observations. No equivalent process snapshot exists for the instant of the failed load, so attributing that failure to a particular app would be speculative.

## GPU, model and failure timeline

The current GPU snapshot showed 482 MiB used, 3,481 MiB free and 16% utilization. The driver reserves part of the 4,096 MiB total. Windows exposed no numeric per-process VRAM figures in the NVIDIA query. Ollama's server was reachable. Its model list showed the installed Q4_K_M tag and `ollama ps` returned no loaded models. Server PID 9796 used 33.9 MiB resident / 70.3 MiB private and tray app PID 9120 used 25.4 / 51.4 MiB. No Ollama model runner was visible. The small service processes persist independently of model residency.

| Failed attempt measurement | Immediately before | At stop | Immediately after |
|---|---:|---:|---:|
| Available host RAM, MiB | 651.7 | 262.4 | 798.2 |
| Free system commit, MiB | 10,940.0 | 8,808.3 | 10,111.5 |
| Free VRAM, MiB | 3,484 | 2,218 | 3,486 |
| GPU utilization | 18% | 16% | 16% |
| Windows low-memory signal | Off | **On** | Off |

The host was already short of RAM before the **model load**. Records do not establish the memory state before the Ollama *service* originally started. The monitor saw the OS signal at 262.4 MiB, just above its separate 256 MiB guard. It stopped the worker. Ollama logged the client disconnect while loading tensors, aborted the load, and recorded HTTP 499 after 5.9 seconds. Orion's wall time was 6.43 seconds. Zero response bytes arrived. No evidence points to the 60-second deadline, an exhausted GPU, or an exhausted commit limit as the trigger. Failure-time page-in/page-out rates were not captured. A complete synthesis quality or throughput measurement is unavailable.

## How much memory the model needs

* **Installed size.** The local model listing reports 1,945,781,358 bytes (1.81 GiB) for the tag. Model metadata identifies 1.9B language-model parameters, Q4_K_M, and a vision projector. A disk package size does not determine simultaneous physical occupancy.
* **Failed load.** Ollama logged 25/25 layers offloaded, a 1,204.91 MiB CUDA model buffer and a 397.85 MiB CUDA host buffer. These figures describe loader buffers, not a completed context or total peak. Other processes and Windows also moved memory during the 6.43-second window.
* **Earlier local 4096-context loads.** The archived runner log shows 48.00 MiB GPU KV cache, 19.27 MiB recurrent state, 56.02 MiB GPU compute and 20.02 MiB host compute for one reservation. A separate reservation logged 223.30 MiB GPU and 24.93 MiB CPU compute. These reservations describe different allocations/phases and should not be added as a measured peak. A fit estimate in that log totaled 1,328 MiB device and 417 MiB host. Neither figure includes every driver, mapping, file-cache, temporary buffer or Windows allocation.
* **Practical feasibility.** Two earlier 4096-context Qwen calls on this machine returned in 35.53 and 10.52 seconds. The hardware can run this model. The failed cold load shows that an 8 GiB Windows desktop with less than 1 GiB available cannot be relied upon for this workload. The exact completed peak for **this** synthesis remains unknown. [Earlier live measurements](M10_STAGE2_LIVE_EVALUATION.md)
* **Placement and context.** Keep automatic GPU offload. A CPU-heavy split would move more weight into the constrained host and could slow a 60-second task. Orion exposes context and output but has no per-operation GPU-layer control. A smaller context may save cache memory, particularly on GPU, while leaving weight staging largely intact. Even halving a proportional 48 MiB KV allocation would save only about 24 MiB there. The approved prompt estimated 1,774 input tokens plus 256 for framing. At context 2,048 that leaves 18 tokens for output before any safety margin. Reducing output alone does not reduce a fixed context allocation. Preserve 4,096/1,536 for these passages unless a separately reviewed preview supports a different task. [Ollama placement and concurrency](https://docs.ollama.com/faq) · [Context memory](https://docs.ollama.com/context-length)

## Proposed optimizations in priority order

| Priority and action | Expected benefit | Risk to work | Admin / Windows settings / reversibility |
|---|---|---|---|
| 1. Save work, then close only CEO-selected idle Firefox tabs/windows and unused ChatGPT Classic windows through their apps | Largest plausible first gain outside the active engineering session. Whole-family working sets are ~781 and ~560 MiB respectively | Unsaved forms, messages or active downloads. Measure actual RAM after each closure | No / no / apps reopen, unsaved work may not return |
| 2. Inspect browser task managers and avoid running duplicate chat/development sessions during inference | Targets heavy tabs or duplicate frontends. The ChatGPT family occupies ~1,315 MiB | Keep the active controller and monitoring terminal. No evidence an additional IDE can be discarded. Never kill individual helpers on a guess | No / no / reopen saved sessions |
| 3. If confirmed idle, consider Phone Link (~148 MiB) and NVIDIA Overlay (~136 MiB grouped) through normal session controls | Smaller incremental gains | Interrupts phone integrations or captures. Preserve GPU driver services | Usually no / no for session-only closure / relaunch |
| 4. Keep one loaded model and one request machine-wide | Avoids duplicated buffers and parallel contexts. Current loaded count is zero | Other clients would have to wait. Orion's lock covers only one database | No for operator scheduling / no / reversible |
| 5. Review startup apps with the CEO at a later maintenance window | May reduce persistent background demand after sign-in. WMI enumerated 15 startup entries, which does not establish that all are enabled or unnecessary | Disabling a wanted integration affects future sessions. Review before choosing any entry | Review needs no admin or change. Per-user disable changes Windows settings, generally without admin; machine-wide entries may need admin. Re-enable to reverse |
| 6. Retain automatic pagefile management and GPU placement | Preserves measured commit capacity and keeps model weights primarily on GPU | Continued low physical RAM calls for workload reduction. A fixed pagefile or more CPU layers offers little benefit here | No action, privilege or setting change |
| 7. Consider a smaller-context experiment only for a different, explicitly bounded prompt | May lower the context-cache footprint | Can lose passages, output capacity or verification validity. Must preview budget, rebind parameters and obtain a fresh approval | No admin / no Windows change for per-request settings / reversible by restoring the previous configuration |

Application closure requires the CEO to identify the app or window and confirm work is saved. Re-measure available RAM after each approved closure. The first two candidate families together have ~1.31 GiB of summed working sets, and actual reclamation may be lower. If that is insufficient, defer the attempt. Shared pages, background helpers and changing workloads prevent a guaranteed recovery amount.

## Orion state and recovery

Read-only inspection used the application's execution, verification, approval and status interfaces, read-only SQLite queries for ownership, and Windows PID liveness checks. The isolated validation database file digest matched before and after the grouped inspection. The normal `recovery inspect` command appends an event even for a terminal execution, so it was excluded from this diagnostic.

| Record | Finding |
|---|---|
| Execution | `21a04b45-f0bd-4cac-a91f-1e2a76ff9977`, failed, attempt 1 |
| Task | `de4cca0b-ba2f-43ba-8281-93a0d508c300`, failed |
| Approval | `4e502cb1-c761-4f57-8072-c2e2de5ee549`, granted and consumed by this execution |
| Ownership | Phase stopped. Orion parent/claim owner PID 7836 and worker PID 21828 both checked stopped. No executions running in this database |
| Artifact and verifier | Synthesis binding retained, artifact digest null, managed output absent. Independent verification `1e97bf78-7ef6-4cc0-b51a-945f1c8846ef` failed on the missing file after the operation digest passed |
| Inference slot | Slot 1 retains the execution token with `uncertain=1`. The server is up with an empty loaded-model list. This database remains blocked for new inference |

**Recovery plan, pending CEO permission**

1. Preserve the failed records. No running task needs execution recovery. Before work resumes, coordinate with other Ollama users, confirm there is no active caller, and obtain explicit approval for the Ollama restart and the isolated database claim reset. Application closure is a separate decision.
2. In an approved maintenance window, stop/restart the intended local Ollama service. Verify that the old service instance ended, the replacement responds, the old Orion caller and worker are gone, and no synthesis is running. Check `ollama ps` and inspect `ai-status` against the validation database. A worker exit or an empty model list alone cannot attest to a restart.
3. **Only after those prerequisites and approval**, run this command from the repository root:

   ```powershell
   .\.venv\Scripts\python.exe -m orion --database data/m10-stage3-retry/validation.sqlite3 --log-dir data/m10-stage4/logs ai-reset --confirm-service-restarted --reason "CEO authorized reset after verified Ollama restart and confirmed exit of the previous caller and worker for 21a04b45-f0bd-4cac-a91f-1e2a76ff9977"
   ```

4. Re-read `ai-status` against the same database and confirm a null inference claim. Confirm attempt 1, its failed verification and its consumed approval remain intact. This administrative reset requires operator authorization and database write access. Elevation depends on the service account used for the restart. [Orion recovery procedure](../README.md)
5. Consider a **new** task and approval only once the following resource gate passes. Its fingerprint must bind the current verified evidence, settings and dependency. Restoring the slot grants no execution authority.

## Proposed launch and cancellation policy

| Before a future cold load | Proposed operational minimum or maximum |
|---|---|
| Available host RAM | **2.5 GiB minimum**, sustained across 30 seconds of samples. The failed run began at 0.64 GiB. This policy allows roughly 2 GiB for a variable loading/runtime footprint and 0.5 GiB as a stop reserve. It is a planning allowance, not a measured peak |
| Free commit | **4 GiB minimum**. Observed headroom fell by about 2.08 GiB during the failed load. The extra reserve permits other Windows allocations |
| Free VRAM | **2.5 GiB minimum**. The earlier device fit projection was about 1.30 GiB. The remainder allows staging, graphics, driver and allocation variability |
| Concurrency and configuration | Zero loaded models before a cold launch, maximum one loaded model and one request across all clients. Existing Qwen tag, automatic GPU placement, context at most 4,096, output at most 1,536, deadline at most 60 seconds, one separately approved attempt |
| Cancellation | Monitor from before load until worker exit. Stop the dedicated worker on a Windows low-memory signal, available host RAM below 512 MiB, free commit or VRAM below 512 MiB, loss of telemetry, system unresponsiveness, or the deadline. On provider failure or disconnection, preserve failure evidence and the uncertainty gate. No automatic retry |

At the diagnostic snapshot the RAM gate alone was short by about **1.76 GiB**. The thresholds are proposed operating policy, not a proven safe minimum or a change to Orion's source. The actionable sequence is CEO-selected workload reduction, measurement, authorized service/claim recovery, and a separate decision on a concrete new synthesis proposal. No live inference or system/recovery changes occurred in Stage 4.

Raw diagnostic snapshots reside under ignored `data/m10-stage4/`. The Stage 4 checkpoint contains this report alone. The existing Stage 3.4 approval report remains a separate local document.
