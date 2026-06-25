import SwiftUI

@MainActor
final class QuickCaptureViewModel: ObservableObject {
    @Published var text: String = ""
    @Published var category: String = "inbox"
    @Published var isSaving = false
    @Published var savedNote: BrainNote?
    @Published var error: String?

    func save() async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        isSaving = true; error = nil
        let lines = text.split(separator: "\n", maxSplits: 1)
        let title = String(lines.first ?? "Quick Capture")
        let body = lines.count > 1 ? String(lines[1]) : ""
        let req = CreateNoteRequest(title: title, content: body, category: category, tags: ["capture"], pinned: false)
        do {
            savedNote = try await BrainAPI.shared.createNote(req)
            text = ""
        } catch { self.error = error.localizedDescription }
        isSaving = false
    }
}

struct QuickCaptureView: View {
    @StateObject private var vm = QuickCaptureViewModel()
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Big text field
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Gedanke oder Notiz", systemImage: "lightbulb")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(.secondary)

                        ZStack(alignment: .topLeading) {
                            if vm.text.isEmpty {
                                Text("Erste Zeile = Titel\nRest = Inhalt…")
                                    .foregroundColor(.secondary)
                                    .padding(12)
                            }
                            TextEditor(text: $vm.text)
                                .frame(minHeight: 180)
                                .focused($focused)
                        }
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .padding(.horizontal)

                    // Category
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Kategorie", systemImage: "tag")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(.secondary)
                            .padding(.horizontal)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(brainCategories, id: \.self) { cat in
                                    Button {
                                        vm.category = cat
                                    } label: {
                                        Text(cat.capitalized)
                                            .font(.subheadline)
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 8)
                                            .background(vm.category == cat ? Color.forCategory(cat) : Color(.secondarySystemBackground))
                                            .foregroundColor(vm.category == cat ? .white : .primary)
                                            .clipShape(Capsule())
                                    }
                                }
                            }
                            .padding(.horizontal)
                        }
                    }

                    // Save button
                    Button {
                        Task { await vm.save() }
                    } label: {
                        HStack {
                            if vm.isSaving {
                                ProgressView().tint(.white)
                            } else {
                                Image(systemName: "arrow.up.circle.fill")
                                Text("Sichern")
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(vm.text.isEmpty ? Color.gray : Color.purple)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                    }
                    .disabled(vm.text.isEmpty || vm.isSaving)
                    .padding(.horizontal)

                    // Success feedback
                    if let saved = vm.savedNote {
                        HStack {
                            Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                            Text("\"\(saved.title)\" gespeichert")
                                .font(.subheadline)
                        }
                        .padding()
                        .background(Color.green.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .padding(.horizontal)
                        .transition(.scale.combined(with: .opacity))
                    }
                }
                .padding(.top, 20)
            }
            .navigationTitle("Capture")
            .onAppear { focused = true }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
            .animation(.spring(), value: vm.savedNote?.id)
        }
    }
}
