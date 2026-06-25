import SwiftUI

@MainActor
final class NoteListViewModel: ObservableObject {
    @Published var notes: [BrainNote] = []
    @Published var selectedCategory: String = "all"
    @Published var searchText: String = ""
    @Published var isLoading = false
    @Published var error: String?

    func load() async {
        isLoading = true; error = nil
        do {
            let cat = selectedCategory == "all" ? nil : selectedCategory
            notes = try await BrainAPI.shared.fetchNotes(category: cat)
        } catch { self.error = error.localizedDescription }
        isLoading = false
    }

    var filtered: [BrainNote] {
        guard !searchText.isEmpty else { return notes }
        let q = searchText.lowercased()
        return notes.filter { $0.title.lowercased().contains(q) || $0.content.lowercased().contains(q) }
    }
}

struct NoteListView: View {
    @StateObject private var vm = NoteListViewModel()
    @State private var showCreate = false
    @State private var selectedNote: BrainNote?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                categoryScroll
                if vm.isLoading {
                    Spacer(); ProgressView(); Spacer()
                } else if vm.filtered.isEmpty {
                    Spacer()
                    ContentUnavailableView("Keine Notizen", systemImage: "note.text", description: Text(vm.searchText.isEmpty ? "Erstelle deine erste Notiz" : "Keine Treffer für \"\(vm.searchText)\""))
                    Spacer()
                } else {
                    noteList
                }
            }
            .navigationTitle("BrainOS")
            .searchable(text: $vm.searchText, prompt: "Suchen…")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $showCreate, onDismiss: { Task { await vm.load() } }) {
                NoteEditorView(note: nil)
            }
            .sheet(item: $selectedNote, onDismiss: { Task { await vm.load() } }) { note in
                NoteEditorView(note: note)
            }
            .task { await vm.load() }
            .onChange(of: vm.selectedCategory) { _, _ in Task { await vm.load() } }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
        }
    }

    private var categoryScroll: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                categoryChip("all", label: "Alle")
                ForEach(brainCategories, id: \.self) { cat in
                    categoryChip(cat, label: cat.capitalized)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
    }

    private func categoryChip(_ cat: String, label: String) -> some View {
        let selected = vm.selectedCategory == cat
        return Button {
            vm.selectedCategory = cat
        } label: {
            Text(label)
                .font(.subheadline.weight(.medium))
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(selected ? Color.forCategory(cat == "all" ? "inbox" : cat) : Color(.secondarySystemBackground))
                .foregroundColor(selected ? .white : .primary)
                .clipShape(Capsule())
        }
    }

    private var noteList: some View {
        List {
            ForEach(vm.filtered) { note in
                NoteRowView(note: note)
                    .contentShape(Rectangle())
                    .onTapGesture { selectedNote = note }
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) {
                            Task {
                                try? await BrainAPI.shared.deleteNote(note.id)
                                await vm.load()
                            }
                        } label: { Label("Löschen", systemImage: "trash") }
                    }
            }
        }
        .listStyle(.plain)
    }
}

struct NoteRowView: View {
    let note: BrainNote

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Circle()
                    .fill(Color.forCategory(note.category))
                    .frame(width: 8, height: 8)
                Text(note.title)
                    .font(.headline)
                Spacer()
                if note.pinned == true {
                    Image(systemName: "pin.fill")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
            if !note.content.isEmpty {
                Text(note.content.prefix(100))
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
            if let tags = note.tags, !tags.isEmpty {
                HStack(spacing: 4) {
                    ForEach(tags.prefix(3), id: \.self) { tag in
                        Text("#\(tag)")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color(.tertiarySystemBackground))
                            .clipShape(Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
