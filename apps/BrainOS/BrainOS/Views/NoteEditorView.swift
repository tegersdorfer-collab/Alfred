import SwiftUI

@MainActor
final class NoteEditorViewModel: ObservableObject {
    @Published var title: String
    @Published var content: String
    @Published var category: String
    @Published var tags: String
    @Published var pinned: Bool
    @Published var backlinks: [BacklinkItem] = []
    @Published var isSaving = false
    @Published var error: String?
    @Published var showWikiSuggestions = false
    @Published var wikiSuggestions: [BrainNote] = []
    @Published var allNotes: [BrainNote] = []

    let existingNote: BrainNote?

    init(note: BrainNote?) {
        self.existingNote = note
        title = note?.title ?? ""
        content = note?.content ?? ""
        category = note?.category ?? "inbox"
        tags = note?.tags?.joined(separator: ", ") ?? ""
        pinned = note?.pinned ?? false
    }

    func loadBacklinks() async {
        guard let id = existingNote?.id else { return }
        backlinks = (try? await BrainAPI.shared.fetchBacklinks(id)) ?? []
    }

    func loadAllNotes() async {
        allNotes = (try? await BrainAPI.shared.fetchNotes(limit: 500)) ?? []
    }

    func checkWikiSuggestions(text: String) {
        // Find the last [[ sequence to suggest completions
        let pattern = #"\[\[([^\[\]]*)$"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let qRange = Range(match.range(at: 1), in: text) else {
            showWikiSuggestions = false
            return
        }
        let query = String(text[qRange]).lowercased()
        if query.isEmpty {
            wikiSuggestions = Array(allNotes.prefix(8))
        } else {
            wikiSuggestions = allNotes.filter { $0.title.lowercased().hasPrefix(query) }.prefix(8).map { $0 }
        }
        showWikiSuggestions = !wikiSuggestions.isEmpty
    }

    func insertWikiLink(_ note: BrainNote) {
        // Replace the partial [[text with [[title]]
        let pattern = #"\[\[([^\[\]]*)$"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: content, range: NSRange(content.startIndex..., in: content)),
              let mRange = Range(match.range, in: content) else { return }
        content.replaceSubrange(mRange, with: "[[\(note.title)]]")
        showWikiSuggestions = false
    }

    func save(dismiss: () -> Void) async {
        guard !title.isEmpty else { error = "Titel fehlt"; return }
        isSaving = true; error = nil
        let tagList = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        do {
            if let id = existingNote?.id {
                let req = UpdateNoteRequest(title: title, content: content, category: category, tags: tagList, pinned: pinned)
                _ = try await BrainAPI.shared.updateNote(id, req)
            } else {
                let req = CreateNoteRequest(title: title, content: content, category: category, tags: tagList, pinned: pinned)
                _ = try await BrainAPI.shared.createNote(req)
            }
            dismiss()
        } catch { self.error = error.localizedDescription }
        isSaving = false
    }
}

struct NoteEditorView: View {
    let note: BrainNote?
    @StateObject private var vm: NoteEditorViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showPreview = false

    init(note: BrainNote?) {
        self.note = note
        _vm = StateObject(wrappedValue: NoteEditorViewModel(note: note))
    }

    var body: some View {
        NavigationStack {
            Group {
                if showPreview {
                    previewView
                } else {
                    editorForm
                }
            }
            .navigationTitle(note == nil ? "Neue Notiz" : vm.title.isEmpty ? "Bearbeiten" : vm.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) { showPreview.toggle() }
                    } label: {
                        Label(showPreview ? "Bearbeiten" : "Vorschau",
                              systemImage: showPreview ? "pencil" : "eye")
                    }
                }
                ToolbarItem(placement: .primaryAction) {
                    if vm.isSaving {
                        ProgressView()
                    } else {
                        Button("Sichern") {
                            Task { await vm.save { dismiss() } }
                        }.fontWeight(.semibold)
                    }
                }
            }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
            .task {
                await vm.loadAllNotes()
                await vm.loadBacklinks()
            }
        }
    }

    private var previewView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(vm.title)
                    .font(.largeTitle.bold())
                    .frame(maxWidth: .infinity, alignment: .leading)

                HStack(spacing: 8) {
                    Text(vm.category.capitalized)
                        .font(.caption.bold())
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.purple.opacity(0.12))
                        .foregroundStyle(.purple)
                        .clipShape(Capsule())
                    ForEach(vm.tags.split(separator: ",").map { String($0.trimmingCharacters(in: .whitespaces)) }.filter { !$0.isEmpty }, id: \.self) { tag in
                        Text("#\(tag)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()

                if let attr = try? AttributedString(markdown: vm.content) {
                    Text(attr)
                        .font(.body)
                        .lineSpacing(4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text(vm.content)
                        .font(.body)
                        .lineSpacing(4)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if !vm.backlinks.isEmpty {
                    Divider()
                    Text("Backlinks").font(.headline)
                    ForEach(vm.backlinks) { bl in
                        Label(bl.title, systemImage: "arrow.backward").foregroundStyle(.secondary)
                    }
                }
            }
            .padding()
        }
    }

    private var editorForm: some View {
        Form {
            Section("Inhalt") {
                TextField("Titel", text: $vm.title)
                    .font(.headline)
                ZStack(alignment: .topLeading) {
                    if vm.content.isEmpty {
                        Text("Notiz schreiben…")
                            .foregroundColor(.secondary)
                            .padding(.top, 8)
                            .padding(.leading, 4)
                    }
                    TextEditor(text: $vm.content)
                        .frame(minHeight: 200)
                        .onChange(of: vm.content) { _, new in
                            vm.checkWikiSuggestions(text: new)
                        }
                }
                if vm.showWikiSuggestions {
                    wikiSuggestionList
                }
            }

                Section("Metadaten") {
                    Picker("Kategorie", selection: $vm.category) {
                        ForEach(brainCategories, id: \.self) { cat in
                            Label(cat.capitalized, systemImage: categoryIcon(cat))
                                .tag(cat)
                        }
                    }
                    TextField("Tags (kommasepariert)", text: $vm.tags)
                    Toggle("Angeheftet", isOn: $vm.pinned)
                }

                if !vm.backlinks.isEmpty {
                    Section("Backlinks (\(vm.backlinks.count))") {
                        ForEach(vm.backlinks) { bl in
                            Label(bl.title, systemImage: "arrow.backward")
                                .foregroundColor(.secondary)
                        }
                    }
                }

                let outbound = WikiLinkParser.extractLinks(from: vm.content)
                if !outbound.isEmpty {
                    Section("Outbound Links (\(outbound.count))") {
                        ForEach(outbound, id: \.self) { link in
                            Label(link, systemImage: "arrow.forward")
                                .foregroundColor(.purple)
                        }
                    }
                }
            }
        }

    private var wikiSuggestionList: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(vm.wikiSuggestions) { suggestion in
                Button {
                    vm.insertWikiLink(suggestion)
                } label: {
                    HStack {
                        Circle()
                            .fill(Color.forCategory(suggestion.category))
                            .frame(width: 8, height: 8)
                        Text(suggestion.title)
                            .foregroundColor(.primary)
                        Spacer()
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 4)
                }
                Divider()
            }
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func categoryIcon(_ cat: String) -> String {
        switch cat {
        case "inbox": return "tray"
        case "project": return "folder"
        case "area": return "mappin"
        case "resource": return "bookmark"
        case "daily": return "calendar"
        case "quote": return "quote.bubble"
        default: return "note.text"
        }
    }
}
