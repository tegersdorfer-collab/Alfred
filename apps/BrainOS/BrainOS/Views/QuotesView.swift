import SwiftUI

struct BrainQuote: Decodable, Identifiable {
    let id: Int
    let title: String
    let content: String
    let tags: [String]?
    let createdAt: String?
}

@MainActor
final class QuotesViewModel: ObservableObject {
    @Published var quotes: [BrainNote] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var showAddQuote = false
    @Published var randomQuote: BrainNote?

    func load() async {
        isLoading = true; error = nil
        do {
            quotes = try await BrainAPI.shared.fetchNotes(category: "quote")
            randomQuote = quotes.randomElement()
        } catch { self.error = error.localizedDescription }
        isLoading = false
    }

    func delete(_ note: BrainNote) async {
        try? await BrainAPI.shared.deleteNote(note.id)
        await load()
    }
}

struct QuotesView: View {
    @StateObject private var vm = QuotesViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if let q = vm.randomQuote { featuredQuote(q) }

                    if vm.isLoading {
                        ProgressView().padding()
                    } else if vm.quotes.isEmpty {
                        ContentUnavailableView("Keine Zitate", systemImage: "quote.bubble",
                                              description: Text("Füge dein erstes Zitat hinzu")).padding(.top, 20)
                    } else {
                        ForEach(vm.quotes) { quote in
                            NavigationLink { NoteEditorView(note: quote) } label: {
                                QuoteCard(note: quote)
                            }
                            .buttonStyle(.plain)
                            .contextMenu {
                                Button(role: .destructive) { Task { await vm.delete(quote) } } label: {
                                    Label("Löschen", systemImage: "trash")
                                }
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Zitate")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { vm.showAddQuote = true } label: { Image(systemName: "plus") }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button { vm.randomQuote = vm.quotes.randomElement() } label: {
                        Image(systemName: "shuffle")
                    }
                }
            }
            .sheet(isPresented: $vm.showAddQuote, onDismiss: { Task { await vm.load() } }) {
                AddQuoteView()
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
        }
    }

    private func featuredQuote(_ note: BrainNote) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: "quote.opening").font(.title).foregroundStyle(.purple.opacity(0.5))
            Text(note.content.prefix(200))
                .font(.body.italic())
                .lineSpacing(4)
            HStack {
                Spacer()
                Text("— \(note.title)").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(
            LinearGradient(colors: [Color.purple.opacity(0.08), Color.pink.opacity(0.05)],
                          startPoint: .topLeading, endPoint: .bottomTrailing)
        )
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

struct QuoteCard: View {
    let note: BrainNote

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "quote.opening").font(.title3).foregroundStyle(.purple.opacity(0.6)).padding(.top, 2)
            VStack(alignment: .leading, spacing: 6) {
                Text(note.content.prefix(120))
                    .font(.subheadline.italic())
                    .foregroundStyle(.primary)
                    .lineLimit(3)
                Text("— \(note.title)").font(.caption).foregroundStyle(.secondary)
                if let tags = note.tags, !tags.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(tags, id: \.self) { tag in
                            Text("#\(tag)").font(.caption2).foregroundStyle(.purple)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct AddQuoteView: View {
    @State private var attribution = ""
    @State private var content = ""
    @State private var tags = ""
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Zitat") {
                    TextField("Quelle / Autor", text: $attribution)
                    TextField("Text des Zitats", text: $content, axis: .vertical).lineLimit(4...10)
                }
                Section("Tags") {
                    TextField("Tags (kommagetrennt)", text: $tags)
                }
            }
            .navigationTitle("Neues Zitat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    if isSaving { ProgressView() }
                    else { Button("Sichern") { Task { await save() } }.fontWeight(.semibold) }
                }
            }
            .alert("Fehler", isPresented: .init(get: { error != nil }, set: { _ in error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(error ?? "") }
        }
    }

    private func save() async {
        guard !content.isEmpty, !attribution.isEmpty else { error = "Bitte Zitat und Quelle angeben"; return }
        isSaving = true
        let tagList = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let req = CreateNoteRequest(title: attribution, content: content, category: "quote", tags: tagList, pinned: false)
        do { _ = try await BrainAPI.shared.createNote(req); dismiss() }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }
}
