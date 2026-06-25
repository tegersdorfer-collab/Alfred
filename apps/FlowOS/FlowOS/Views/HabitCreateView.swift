import SwiftUI

struct HabitCreateView: View {
    @State private var name = ""
    @State private var description = ""
    @State private var frequency = "daily"
    @State private var selectedColor = "indigo"
    @State private var selectedIcon = "star"
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Gewohnheit") {
                    TextField("Name", text: $name)
                    TextField("Beschreibung (optional)", text: $description)
                }

                Section("Häufigkeit") {
                    Picker("Häufigkeit", selection: $frequency) {
                        Text("Täglich").tag("daily")
                        Text("Werktags").tag("weekdays")
                        Text("Wöchentlich").tag("weekly")
                    }
                    .pickerStyle(.segmented)
                }

                Section("Symbol") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 6), spacing: 12) {
                        ForEach(habitIcons, id: \.self) { icon in
                            Button {
                                selectedIcon = icon
                            } label: {
                                Image(systemName: icon)
                                    .font(.title2)
                                    .foregroundStyle(selectedIcon == icon ? habitAccentColor(selectedColor) : .secondary)
                                    .frame(width: 44, height: 44)
                                    .background(selectedIcon == icon ? habitAccentColor(selectedColor).opacity(0.15) : Color.clear)
                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section("Farbe") {
                    HStack(spacing: 12) {
                        ForEach(habitColors, id: \.self) { color in
                            Button {
                                selectedColor = color
                            } label: {
                                Circle()
                                    .fill(habitAccentColor(color))
                                    .frame(width: 32, height: 32)
                                    .overlay(
                                        Circle().stroke(Color.white, lineWidth: selectedColor == color ? 3 : 0)
                                    )
                                    .shadow(color: selectedColor == color ? habitAccentColor(color) : .clear, radius: 4)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            .navigationTitle("Neue Gewohnheit")
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
        guard !name.isEmpty else { error = "Name fehlt"; return }
        isSaving = true
        let req = CreateHabitRequest(name: name, description: description.isEmpty ? nil : description,
                                     frequency: frequency, color: selectedColor, icon: selectedIcon)
        do { try await FlowAPI.shared.createHabit(req); dismiss() }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }
}
