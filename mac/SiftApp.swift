import AppKit
import SwiftUI

@main
struct SiftApplication {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = SiftDelegate()
        app.delegate = delegate
        app.run()
        withExtendedLifetime(delegate) { }
    }
}

final class SiftDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem?
    private var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 720),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable],
                              backing: .buffered, defer: false)
        window.title = "Sift"
        window.contentView = NSHostingView(rootView: ReviewWindow())
        window.center()
        window.makeKeyAndOrderFront(nil)
        self.window = window
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Sift"
        let menu = NSMenu()
        let openItem = NSMenuItem(title: "Open Sift", action: #selector(openWindow), keyEquivalent: "o")
        openItem.target = self
        menu.addItem(openItem)
        menu.addItem(.separator())
        let quitItem = NSMenuItem(title: "Quit Sift", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)
        item.menu = menu
        statusItem = item
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openWindow()
        return true
    }

    @objc private func openWindow() {
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
        window?.orderFrontRegardless()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}

struct ProposalRow: Identifiable {
    let id: String
    let source: String
    let category: String
    let confidence: String
    let reason: String
    var destinationFolder: String
    var name: String
    var selected: Bool
}

struct SearchRow: Identifiable {
    let path: String
    let score: Int
    var id: String { path }
}

struct HistoryRow: Identifiable {
    let id: String
    let applied: Int
}

@MainActor
final class SiftModel: ObservableObject {
    @Published var source = UserDefaults.standard.string(forKey: "source") ?? ""
    @Published var destination = UserDefaults.standard.string(forKey: "destination") ?? ""
    @Published var useOllama = false
    @Published var rows: [ProposalRow] = []
    @Published var history: [HistoryRow] = []
    @Published var query = ""
    @Published var searchRows: [SearchRow] = []
    @Published var status = "Choose a source folder and destination, then scan. Nothing moves until you apply a reviewed plan."
    @Published var busy = false

    private var plan: [String: Any]?

    var categories: [String] { Array(Set(rows.map(\.category))).sorted() }
    var selectedCount: Int { rows.filter(\.selected).count }

    func chooseSource() {
        if let path = chooseFolder() {
            source = path
            UserDefaults.standard.set(path, forKey: "source")
        }
    }

    func chooseDestination() {
        if let path = chooseFolder() {
            destination = path
            UserDefaults.standard.set(path, forKey: "destination")
        }
    }

    private func chooseFolder() -> String? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    func scan() {
        guard !source.isEmpty, !destination.isEmpty else {
            status = "Choose both folders before scanning."
            return
        }
        busy = true
        status = "Scanning locally. OCR and the first model load can take time…"
        invoke(["command": "scan", "source": source, "destination": destination, "ollama": useOllama]) { response in
            self.busy = false
            guard let plan = response["plan"] as? [String: Any], let items = plan["items"] as? [[String: Any]] else { return }
            self.plan = plan
            self.rows = items.compactMap { item in
                guard let id = item["id"] as? String,
                      let source = item["source"] as? String,
                      let category = item["category"] as? String,
                      let confidence = item["confidence"] as? String,
                      let reason = item["reason"] as? String,
                      let folder = item["destination_folder"] as? String,
                      let name = item["name"] as? String else { return nil }
                return ProposalRow(id: id, source: source, category: category, confidence: confidence,
                                   reason: reason, destinationFolder: folder, name: name,
                                   selected: item["selected"] as? Bool ?? false)
            }
            self.status = "\(self.rows.count) proposals ready. \(self.selectedCount) selected; no files moved."
        }
    }

    func select(category: String, value: Bool) {
        for index in rows.indices where rows[index].category == category {
            rows[index].selected = value
        }
    }

    func applySelected() {
        guard var plan, let originals = plan["items"] as? [[String: Any]], selectedCount > 0 else { return }
        let edits = Dictionary(uniqueKeysWithValues: rows.map { ($0.id, $0) })
        plan["items"] = originals.map { original -> [String: Any] in
            var item = original
            if let id = item["id"] as? String, let row = edits[id] {
                item["destination_folder"] = row.destinationFolder
                item["name"] = row.name
                item["selected"] = row.selected
            }
            return item
        }
        let ids = rows.filter(\.selected).map(\.id)
        busy = true
        status = "Applying \(ids.count) reviewed moves…"
        invoke(["command": "apply", "plan": plan, "selected_ids": ids]) { response in
            self.busy = false
            let results = response["results"] as? [[String: Any]] ?? []
            let applied = results.filter { ($0["state"] as? String) == "applied" }.count
            let failed = results.filter { ($0["state"] as? String) == "failed" }.count
            self.status = "Applied \(applied) moves; \(failed) failed. Review history to undo."
            let appliedIDs = Set(results.compactMap { row -> String? in
                (row["state"] as? String) == "applied" ? row["id"] as? String : nil
            })
            self.rows.removeAll { appliedIDs.contains($0.id) }
            self.plan = self.rows.isEmpty ? nil : plan
            self.loadHistory()
        }
    }

    func loadHistory() {
        invoke(["command": "history"]) { response in
            self.history = (response["batches"] as? [[String: Any]] ?? []).compactMap { row in
                guard let id = row["id"] as? String else { return nil }
                return HistoryRow(id: id, applied: row["applied"] as? Int ?? 0)
            }
        }
    }

    func undo(_ id: String) {
        busy = true
        status = "Undoing batch \(id)…"
        invoke(["command": "undo", "id": id]) { response in
            self.busy = false
            let results = response["results"] as? [[String: Any]] ?? []
            let undone = results.filter { ($0["state"] as? String) == "undone" }.count
            let failed = results.filter { ($0["state"] as? String) == "failed" }.count
            self.status = "Undid \(undone) moves; \(failed) need attention."
            self.loadHistory()
        }
    }

    func search() {
        guard !destination.isEmpty, !query.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        busy = true
        status = "Searching locally…"
        invoke(["command": "search", "source": destination, "query": query]) { response in
            self.busy = false
            self.searchRows = (response["results"] as? [[String: Any]] ?? []).compactMap { row in
                guard let path = row["path"] as? String, let score = row["score"] as? Int else { return nil }
                return SearchRow(path: path, score: score)
            }
            self.status = "\(self.searchRows.count) search results. No files changed."
        }
    }

    private func invoke(_ request: [String: Any], completion: @escaping ([String: Any]) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let resources = Bundle.main.resourceURL!
                let helper = resources.appendingPathComponent("sift-helper/sift-helper")
                let process = Process()
                if FileManager.default.isExecutableFile(atPath: helper.path) {
                    process.executableURL = helper
                } else {
                    let project = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
                    let python = ProcessInfo.processInfo.environment["SIFT_PYTHON"] ?? project.appendingPathComponent(".venv/bin/python").path
                    process.executableURL = URL(fileURLWithPath: python)
                    process.arguments = ["-m", "sift.bridge"]
                    var environment = ProcessInfo.processInfo.environment
                    environment["PYTHONPATH"] = ProcessInfo.processInfo.environment["SIFT_PROJECT_ROOT"] ?? project.path
                    process.environment = environment
                }
                let input = Pipe(), output = Pipe(), errors = Pipe()
                process.standardInput = input
                process.standardOutput = output
                process.standardError = errors
                try process.run()
                let bytes = try JSONSerialization.data(withJSONObject: request)
                input.fileHandleForWriting.write(bytes)
                input.fileHandleForWriting.closeFile()
                let responseData = output.fileHandleForReading.readDataToEndOfFile()
                let errorData = errors.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let response = try JSONSerialization.jsonObject(with: responseData) as? [String: Any]
                guard let response, response["ok"] as? Bool == true else {
                    let message = (response?["error"] as? String) ?? String(data: errorData, encoding: .utf8) ?? "Unknown helper error"
                    throw NSError(domain: "Sift", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
                }
                DispatchQueue.main.async { completion(response) }
            } catch {
                DispatchQueue.main.async {
                    self.busy = false
                    self.status = "Sift error: \(error.localizedDescription)"
                }
            }
        }
    }
}

struct ReviewWindow: View {
    @StateObject private var model = SiftModel()
    @State private var confirmApply = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Group {
            HStack {
                Text("Sift").font(.largeTitle).bold()
                Spacer()
                Text("Local file organizer").foregroundStyle(.secondary)
            }
            HStack {
                Text("Source").frame(width: 80, alignment: .leading)
                TextField("Choose a folder", text: $model.source)
                Button("Choose…") { model.chooseSource() }
            }
            HStack {
                Text("Destination").frame(width: 80, alignment: .leading)
                TextField("Choose a folder", text: $model.destination)
                Button("Choose…") { model.chooseDestination() }
            }
            HStack {
                Toggle("Use local Ollama for uncertain files", isOn: $model.useOllama)
                Spacer()
                Button("Scan") { model.scan() }.disabled(model.busy)
            }
            Text(model.status).font(.callout).foregroundStyle(.secondary)
            HStack {
                Text("Review: \(model.rows.count) files, \(model.selectedCount) selected").bold()
                Spacer()
                Button("Apply Selected…") { confirmApply = true }
                    .disabled(model.busy || model.selectedCount == 0)
            }
            List {
                ForEach(model.categories, id: \.self) { category in
                    Section {
                        ForEach(model.rows.indices.filter { model.rows[$0].category == category }, id: \.self) { index in
                            HStack(alignment: .top) {
                                Toggle("", isOn: $model.rows[index].selected).labelsHidden()
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(model.rows[index].source).lineLimit(1).truncationMode(.middle)
                                    Text("\(model.rows[index].confidence) · \(model.rows[index].reason)")
                                        .font(.caption).foregroundStyle(.secondary)
                                    HStack {
                                        TextField("New name", text: $model.rows[index].name)
                                        TextField("Destination folder", text: $model.rows[index].destinationFolder)
                                    }
                                }
                            }
                            .padding(.vertical, 3)
                        }
                    } header: {
                        HStack {
                            Text(category)
                            Spacer()
                            Button("All") { model.select(category: category, value: true) }
                            Button("None") { model.select(category: category, value: false) }
                        }
                    }
                }
            }
            .frame(minHeight: 190)
            }
            Group {
            Divider()
            HStack {
                TextField("Search organized files", text: $model.query)
                Button("Search") { model.search() }.disabled(model.busy)
            }
            List(model.searchRows) { row in
                HStack {
                    Text(row.path).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Reveal") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: row.path)]) }
                }
            }
            .frame(height: 90)
            HStack {
                Text("Recent batches").bold()
                Spacer()
                Button("Refresh") { model.loadHistory() }.disabled(model.busy)
            }
            ForEach(model.history.prefix(3)) { batch in
                HStack {
                    Text("\(batch.id) · \(batch.applied) applied")
                    Spacer()
                    Button("Undo…") { model.undo(batch.id) }.disabled(model.busy || batch.applied == 0)
                }
            }
            }
        }
        .padding(18)
        .onAppear { model.loadHistory() }
        .alert("Apply \(model.selectedCount) selected moves?", isPresented: $confirmApply) {
            Button("Apply", role: .destructive) { model.applySelected() }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Sift checks each source and destination again before moving. You can undo unchanged files from Recent batches.")
        }
    }
}
