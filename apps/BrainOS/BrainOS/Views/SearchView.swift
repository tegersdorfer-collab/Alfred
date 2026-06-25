import SwiftUI

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var query = ""
    @Published var results: [BrainNote] = []
    @Published var isSearching = false

    private var searchTask: Task<Void, Never>?

    func search() async {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { results = []; return }
        searchTask?.cancel()
        isSearching = true
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            do { results = try await BrainAPI.shared.search(query) }
            catch { results = [] }
            isSearching = false
        }
        await searchTask?.value
    }
}

struct SearchView: View {
    @StateObject private var vm = SearchViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField("Notizen durchsuchen…", text: $vm.query)
                        .textFieldStyle(.plain)
                        .onChange(of: vm.query) { _, _ in Task { await vm.search() } }
                    if !vm.query.isEmpty {
                        Button { vm.query = ""; vm.results = [] } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(12)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .padding()

                if vm.isSearching {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if vm.query.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass").font(.system(size: 48)).foregroundStyle(.tertiary)
                        Text("Suche in deinen Notizen").font(.headline).foregroundStyle(.secondary)
                        Text("Titel, Inhalt und Tags").font(.subheadline).foregroundStyle(.tertiary)
                    }
                    Spacer()
                } else if vm.results.isEmpty {
                    Spacer()
                    ContentUnavailableView.search(text: vm.query)
                    Spacer()
                } else {
                    List(vm.results) { note in
                        NavigationLink {
                            NoteEditorView(note: note)
                        } label: {
                            SearchResultRow(note: note, query: vm.query)
                        }
                        .listRowBackground(Color.clear)
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Suche")
        }
    }
}

struct SearchResultRow: View {
    let note: BrainNote
    let query: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(note.title).font(.subheadline.bold()).lineLimit(1)
                Spacer()
                Text(note.category).font(.caption2.bold())
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Color.forCategory(note.category).opacity(0.15))
                    .foregroundStyle(Color.forCategory(note.category))
                    .clipShape(Capsule())
            }
            Text(note.content)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            if let tags = note.tags, !tags.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        ForEach(tags, id: \.self) { tag in
                            Text("#\(tag)").font(.caption2).foregroundStyle(.purple)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
