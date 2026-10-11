# Sift — product and technical plan

**Status:** working plan, 10 October 2026  
**Product:** private, local file organizer for macOS  
**First release:** safe catch-up for Downloads, Desktop, and selected folders

## 1. Product decision

Sift should earn trust before it attempts full automation. The first usable release scans folders the user selects, reads supported files locally, proposes names and destinations, and shows a reviewable plan. A user can approve groups, edit individual proposals, apply a batch, and undo it. Autopilot begins as a suggestion inbox. Automatic moves come only after the user enables them for specific categories.

The central promise is **private organization that remains under the user's control**. “Local” means classification, OCR, model inference, search, and logs operate on the Mac with no document content sent to a server. The app should work offline. Update checks, crash reporting, and model downloads, if offered later, must be separate opt-in features with clear data boundaries.

### Initial audience and job

Start with students and independent professionals whose Downloads folder has hundreds of mixed documents. Their first job is: “Help me make sense of this folder without risking my files.” Sensitive practices are a plausible later segment, but should not be a launch claim until access controls, encryption, data retention, and operational testing have been validated for their needs.

### Product principles

1. **Preview every change by default.** No scan has side effects on source files.
2. **Never delete.** Review and duplicate findings are suggestions, not cleanup actions.
3. **Undo is a product feature, not just a log.** A batch can be reversed safely after a restart.
4. **Uncertainty is visible.** Confidence explains the evidence and determines review priority; it does not hide mistakes.
5. **Respect the user's folders.** Suggest an existing destination when it fits; ask before creating a new top-level folder.
6. **Keep private data local.** Treat filenames, extracted text, embeddings, and logs as sensitive.

## 2. Scope and release order

| Release | User-visible scope | Exit criterion |
|---|---|---|
| **MVP: Catch-up** | Folder selection, scan progress, text/PDF extraction, OCR for image and scanned PDF, proposed rename and destination, grouped review, per-file edits, apply, batch/file undo, activity history | A user can organize a representative Downloads folder and reverse every successful move; interrupted batches recover cleanly |
| **V1: Suggestions** | Downloads watcher, stable-file detection, suggestion inbox, notifications, source URL signal, category-specific auto-move controls | New downloads appear once, with no processing of incomplete or temporary files |
| **V1.5: Find and learn** | Local content search, correction memory, exact duplicate detection, better folder matching | Search returns known documents; corrections improve later suggestions without silently changing policy |
| **Later** | Near duplicates, cleanup suggestions, receipts export, screenshots, photos, email, team edition, Windows | Separate discovery and privacy review for each area |

The brief's natural-language search is valuable, but it should follow a reliable index. Start with keyword/full-text search plus filters and document previews. Add local semantic search only when a test set shows it improves retrieval enough to justify disk, memory, and battery cost.

### Explicit MVP exclusions

No cloud integrations, email access, deletion, unattended auto-move, near-duplicate clustering, photo organization, or team controls. Archives and document packages are treated as indivisible files. Unsupported or password-protected documents remain in Review with a clear reason.

## 3. Core journeys

**First-run:** Explain local processing and access plainly. Ask the user to select a source folder and a destination root using a system picker. Save persistent access only for chosen folders. Show the number and types of files found before extracting content. Let the user stop or exclude a subfolder.

**Catch-up:** Scan selected roots. Show totals grouped by destination, plus a separate Review group. Each row shows original path/name, proposed path/name, category, confidence, and a short reason (“PDF text mentions invoice” or “installer file type”). A preview is read-only. Groups can be selected; a row can be deselected or edited. Before Apply, show the exact count and destination summary. Report successes, skips, and errors separately.

**Undo:** Activity shows each batch. Undo checks the current destination before moving anything back. If the original path is occupied or the organized file changed, stop that file and ask the user to choose a safe resolution. The rest of the batch can still be reversed. Never overwrite either copy.

**Autopilot suggestions:** Watch Downloads only at first. Wait until file identity, size, and modification time have remained stable across multiple checks, and ignore known temporary extensions. Queue a suggestion; do not move it until approved. Later, allow auto-move for categories whose precision has been measured and which the user explicitly enabled.

## 4. Classification design

Use one pipeline for catch-up and Autopilot. Every stage returns evidence, a candidate destination, a candidate filename, and a reason. The policy layer decides whether to show, preselect, or hold the item for Review.

```text
Folder scan / file event
  → eligibility and stability checks
  → metadata and provenance
  → text extraction / OCR
  → rules and folder similarity
  → local model only when needed
  → validated proposal + confidence
  → review queue
  → guarded move + journal
```

**Eligibility.** Skip symlinks, hidden/system directories, app bundles, nested Git projects, cloud placeholders not locally available, files the user excluded, and files already in sensible destinations. Do not recurse into package formats. Mark access errors explicitly instead of silently losing items.

**Extraction.** Use PDFKit for embedded PDF text and Vision for OCR of images or image-only PDF pages; both have documented macOS APIs. Extract a bounded amount of text and keep a citation to the page/region where a signal came from. Add adapters for common Office documents after testing their local parsing behavior. OCR failures must not block the plan. Apple documents that are packages need a deliberate adapter rather than generic recursion. [PDFKit](https://developer.apple.com/documentation/pdfkit/pdfdocument/string), [Vision](https://developer.apple.com/documentation/vision/recognizing-text-in-images).

**Rules and similarity.** Rules handle unequivocal cases such as installers and screenshots. For documents, first use names, text, dates, source URL, and explicit user corrections. Compare to *approved* examples in existing folders; avoid learning from an unreviewed folder full of misfiled files. Store the provenance of each suggestion so users can understand it.

**Local model.** Evaluate model runtimes with representative Macs before committing. The model receives only a bounded excerpt, metadata, and an allowlisted destination catalog. Its result is a structured proposal, never a command or path to execute. Validate destination IDs, names, dates, extensions, Unicode normalization, reserved names, and path containment outside the model. Treat document text as untrusted instructions. The model is an optional classifier for ambiguous items; the app must still work if it is unavailable or too slow.

**Confidence.** Do not equate a model's self-reported score with probability. Build a labeled set and calibrate confidence from observed accuracy by category and signal type. Initially: high confidence is preselected in Catch-up, medium is shown for explicit review, low goes to Review. All proposals remain visible before a catch-up batch is applied. Autopilot's auto-move threshold should be stricter and per category.

**Naming.** Generate `date + document type + issuer/topic` only when fields have clear evidence. Preserve extension and useful original terms. If date or issuer is uncertain, use a shorter safe name rather than inventing details. Resolve collisions with a suffix; never overwrite.

## 5. macOS architecture

| Component | Proposed implementation | Responsibility |
|---|---|---|
| Menu bar and review window | SwiftUI with AppKit where needed | Folder selection, plan review, history, settings |
| Job engine | Swift actor/background task or bundled helper | Scan, extract, classify, move, recovery |
| File monitoring | FSEvents plus rescan reconciliation | Detect changed directories; avoid assuming an event means a complete download |
| Extraction | PDFKit, Vision, type-specific adapters | Bounded local text and metadata |
| Classification | Deterministic policy plus local model adapter | Candidate proposals with evidence |
| State | SQLite in app container | Jobs, fingerprints, proposals, corrections, move journal, search index |

FSEvents reports directory hierarchy changes and is suitable for triggering rescans; it is not a transaction record for individual downloads. Persist an event cursor when useful, but always reconcile against the current folder state after launch or watcher interruption. [Apple File System Events](https://developer.apple.com/documentation/coreservices/file_system_events).

Use the macOS sandbox if App Store distribution is a goal. Have the user choose source and destination folders with a system picker; persist security-scoped bookmarks for later sessions and handle stale bookmarks and denied access. A sandboxed app does not have general access to the user's home folder. Downloads has a dedicated entitlement, but user selection provides a consistent, explicit access flow for all chosen roots. [Apple App Sandbox file access](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox), [App Sandbox entitlements](https://developer.apple.com/documentation/security/app-sandbox).

Use coordinated file access where file providers or other apps may be editing documents, and do file I/O off the main thread. Treat iCloud Drive and external volumes as a later tested scope because availability, moves, and latency differ. [Apple file coordination](https://developer.apple.com/documentation/foundation/nsfilecoordinator), [file-system performance guidance](https://developer.apple.com/documentation/foundation/improving-performance-and-stability-when-accessing-the-file-system).

### Data model

```text
watched_roots(id, bookmark, role, exclusions, created_at)
file_records(id, current_url, resource_id, volume_id, size, mtime, hash?, source_url?, extraction_state)
extractions(file_id, version, text_ref, page_map, created_at)
proposals(id, file_id, destination_id, proposed_name, category, evidence, confidence, state)
batches(id, created_at, state, requested_count, completed_count)
move_journal(id, batch_id, file_id, from_url, to_url, before_fingerprint,
             after_fingerprint, state, prepared_at, completed_at, undone_at)
corrections(id, file_id, original_proposal, chosen_destination, chosen_name, created_at)
```

Keep full hashes optional and compute them only when needed for deduplication or stronger undo checks. Size, modification time, file resource identity, and content version can make rescans cheap, but must be rechecked immediately before a move. Apple notes that some URL resource values are unavailable on some volumes, so the app needs fallbacks. [URL resource values](https://developer.apple.com/documentation/foundation/urlresourcevalues).

### Move and recovery protocol

1. Revalidate source access, file identity/content version, destination containment, and available space. Reject symlink traversal and destination collisions.
2. Write a `prepared` journal entry before the move and durably commit it.
3. Perform a coordinated move. Prefer same-volume rename when available; for a cross-volume move, copy to a temporary destination, verify bytes/hash, atomically place the copy, then remove the source only after verification and journal progress are durable. This copy-and-remove path needs focused fault testing.
4. Mark the entry `applied`. At next launch, reconcile `prepared` entries against both paths; never guess or overwrite when state is ambiguous.
5. Undo revalidates the destination and original path, then records `undone`. Partial failures stay visible and retryable.

“Undo whole batch” is a sequence of guarded per-file reversals, not an all-or-nothing filesystem transaction. The UI should communicate partial completion accurately.

## 6. Privacy, security, and trust

- **No document egress:** make network behavior testable. Run scan/classification/search offline in automated checks; do not grant a network entitlement to the processing helper unless a later feature specifically requires it.
- **Local sensitive index:** keep extracted text, embeddings, search index, and logs inside the app container; set restrictive file permissions and a clear retention policy. FileVault protects a locked Mac's disk, but “encrypted at rest” for Sift's own index is a separate design choice. Decide whether application-level encryption with a Keychain-managed key is needed before claiming it.
- **Data minimization:** cap extracted text and retention. Allow “forget this file,” “clear index,” and “remove access to this folder.” Avoid logging document contents.
- **Prompt injection:** document text is data. The model cannot invoke tools or select arbitrary paths. Validate all output in deterministic code and keep an audit reason for every move.
- **Failure containment:** timeouts and memory caps for extraction/model tasks; malformed files cannot crash the review UI or force a move.
- **Transparency:** show local model size/download and disk use before installation, and distinguish “processed locally” from “no network activity of any kind.”

## 7. Success measures and validation

Build a consented test corpus across PDFs, scans, screenshots, invoices, school files, travel documents, duplicate names, empty files, nested projects, and cloud placeholders. Include adversarial filenames and document text. Do not use real user documents in CI.

| Measure | Initial target / gate |
|---|---|
| Unsafe overwrite or lost file | Zero in fault-injection tests before public beta |
| Batch undo | 100% of unchanged moved files restored to an available original path |
| Preview accuracy | Track destination and filename acceptance separately by category; set launch threshold after baseline testing |
| Review burden | Median edits/declines per 100 proposals; lower it over iterations |
| Performance | Measure files/minute, OCR time, model time, peak memory, and battery impact on entry and midrange supported Macs |
| Privacy | Offline processing tests and inspection of all network-capable code paths |

Do not commit to a single “95% accurate” claim across all document types. Precision for auto-moved categories matters more than overall classification accuracy. Validate with files from people outside the development team and record failure reasons.

## 8. Delivery plan and dependencies

**Milestone 0 — discovery (1–2 weeks):** Interview 8–12 target users, gather a consented anonymous file-type inventory, test the review UI on a mock plan, and choose a minimum supported macOS version and distribution channel. Decide whether the first release is direct download or Mac App Store; this affects sandbox and model packaging.

**Milestone 1 — safety core (2–3 weeks):** Folder selection, scan exclusions, proposal model, journal, guarded same-volume moves, undo, collision behavior, and crash recovery. Test with synthetic files and fault injection before adding AI.

**Milestone 2 — useful classification (3–5 weeks):** PDF/text extraction, Vision OCR, metadata/rules, existing-folder matching, evidence display, review UI. Establish a labeled evaluation corpus and baseline metrics.

**Milestone 3 — local AI evaluation (2–4 weeks):** Benchmark candidate local models on quality, latency, RAM, package size, battery, and prompt-injection robustness. Add the best one behind a fallback path if it materially improves ambiguous cases.

**Milestone 4 — beta (2–3 weeks):** Installer, permissions onboarding, logs/settings, accessibility pass, privacy audit, model packaging, signed/notarized distribution, and beta feedback. Revisit estimates after Milestone 0; these are planning ranges, not a delivery commitment.

**After beta:** Autopilot suggestion inbox, then measured per-category auto-move; search and correction learning follow once core safety is stable.

## 9. Decisions to resolve early

1. **Destination model:** one user-selected root, or multiple allowed roots with a map between sources and destinations? Start with one root; test whether that fits actual folder layouts.
2. **Packaging:** bundled model versus user-downloaded model. Bundling simplifies first run but increases app size; download requires a clearly separated network flow.
3. **Search protection:** OS disk protection only, or an app-encrypted index with a Keychain key? Decide before indexing sensitive beta documents.
4. **Supported document types and macOS versions:** choose after testing extraction quality and the hardware needed for local inference.
5. **Business model:** likely paid license or paid upgrade, but interview users before pricing. Avoid subscription assumptions based solely on the absence of cloud costs.

## 10. Immediate next step

Create a clickable review prototype with 30–50 representative synthetic files and test three things with prospective users: whether they understand each proposal, whether group approval feels safe, and whether undo is easy to find. In parallel, build the journal/move engine against a synthetic filesystem test suite. These two tracks will reveal the biggest product and engineering risks before model selection.
