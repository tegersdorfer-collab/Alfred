import SwiftUI

@MainActor
final class DailyNoteViewModel: ObservableObject {
    @Published var note: BrainNote?
    @Published var isLoading = false
    @Published var error: String?

    func load() async {
        isLoading = true; error = nil
        do { note = try await BrainAPI.shared.fetchDailyNote() }
        catch {
            // If no daily note, create one
            do {
                let today = todayTitle()
                let template = dailyTemplate()
                note = try await BrainAPI.shared.createNote(CreateNoteRequest(
                    title: today, content: template, category: "daily", tags: ["daily"], pinned: false
                ))
            } catch { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    private func todayTitle() -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "de_DE")
        let df = DateFormatter(); df.dateStyle = .full; df.locale = Locale(identifier: "de_DE")
        return "\(f.string(from: Date())) — \(df.string(from: Date()))"
    }

    private func dailyTemplate() -> String {
        """
## Tagesnotiz

### Heute fokussieren
-

### Dankbarkeit
-

### Gedanken
"""
    }
}

struct DailyNoteView: View {
    @StateObject private var vm = DailyNoteViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading {
                    VStack(spacing: 16) {
                        ProgressView()
                        Text("Tagesnotiz laden…").foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let note = vm.note {
                    NoteEditorView(note: note)
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.orange)
                        Text("Konnte Tagesnotiz nicht laden").font(.headline)
                        if let err = vm.error { Text(err).font(.caption).foregroundStyle(.secondary) }
                        Button("Erneut") { Task { await vm.load() } }.buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .navigationTitle("Heute")
            .navigationBarTitleDisplayMode(.large)
            .task { await vm.load() }
        }
    }
}
