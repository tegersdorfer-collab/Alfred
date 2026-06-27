import SwiftUI

@MainActor
final class WorkoutDetailViewModel: ObservableObject {
    @Published var title = ""
    @Published var groups: [SessionExercise] = []
    @Published var loading = true
    @Published var saving = false
    @Published var error: String?

    let workoutId: Int
    init(workoutId: Int) { self.workoutId = workoutId }

    func load() async {
        loading = true
        if let w = try? await FitnessAPI.shared.fetchWorkout(workoutId) {
            title = w.title
            var byName: [String: [SessionSet]] = [:]
            var order: [String] = []
            for s in w.sets {
                let name = s.exercise ?? "Übung"
                if byName[name] == nil { byName[name] = []; order.append(name) }
                byName[name]?.append(SessionSet(weight: s.weightKg ?? 0, reps: s.reps ?? 0,
                    rpe: s.rpe, isWarmup: s.isWarmup, isFailure: s.isFailure, done: true))
            }
            groups = order.map { SessionExercise(name: $0, sets: byName[$0] ?? []) }
        }
        loading = false
    }

    func addSet(_ i: Int) {
        guard groups.indices.contains(i) else { return }
        let last = groups[i].sets.last
        groups[i].sets.append(SessionSet(weight: last?.weight ?? 0, reps: last?.reps ?? 0, done: true))
    }

    func deleteSet(_ i: Int, _ j: Int) {
        guard groups.indices.contains(i), groups[i].sets.indices.contains(j) else { return }
        groups[i].sets.remove(at: j)
    }

    func save() async -> Bool {
        saving = true
        var payload: [LogSetPayload] = []
        for ex in groups {
            var idx = 0
            for s in ex.sets {
                idx += 1
                payload.append(LogSetPayload(exercise: ex.name, setIndex: idx, reps: s.reps,
                    weightKg: s.weight > 0 ? s.weight : nil, rpe: s.rpe,
                    isWarmup: s.isWarmup, isFailure: s.isFailure))
            }
        }
        do {
            try await FitnessAPI.shared.updateWorkout(workoutId,
                body: UpdateWorkoutRequest(title: nil, notes: nil, rpe: nil, sets: payload))
            saving = false; return true
        } catch {
            self.error = error.localizedDescription; saving = false; return false
        }
    }

    func delete() async -> Bool {
        do { try await FitnessAPI.shared.deleteWorkout(workoutId); return true }
        catch { self.error = error.localizedDescription; return false }
    }
}

struct WorkoutDetailView: View {
    @StateObject private var vm: WorkoutDetailViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showDeleteConfirm = false
    let onChange: () -> Void

    init(workoutId: Int, onChange: @escaping () -> Void) {
        _vm = StateObject(wrappedValue: WorkoutDetailViewModel(workoutId: workoutId))
        self.onChange = onChange
    }

    var body: some View {
        Group {
            if vm.loading {
                ProgressView()
            } else {
                List {
                    ForEach(Array(vm.groups.enumerated()), id: \.element.id) { i, ex in
                        Section(ex.name) {
                            ForEach(Array(ex.sets.enumerated()), id: \.element.id) { j, _ in
                                SetRow(set: $vm.groups[i].sets[j], number: j + 1, onDone: {}, onChange: {})
                                    .swipeActions(edge: .trailing) {
                                        Button(role: .destructive) { vm.deleteSet(i, j) } label: {
                                            Label("Löschen", systemImage: "trash")
                                        }
                                    }
                            }
                            Button { vm.addSet(i) } label: { Label("Satz", systemImage: "plus").font(.subheadline) }
                        }
                    }
                    Section {
                        Button(role: .destructive) { showDeleteConfirm = true } label: {
                            Label("Training löschen", systemImage: "trash")
                        }
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle(vm.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { if await vm.save() { onChange(); dismiss() } }
                } label: {
                    if vm.saving { ProgressView() } else { Text("Speichern").fontWeight(.semibold) }
                }
                .disabled(vm.saving || vm.loading)
            }
        }
        .confirmationDialog("Training löschen?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Löschen", role: .destructive) {
                Task { if await vm.delete() { onChange(); dismiss() } }
            }
            Button("Abbrechen", role: .cancel) {}
        }
        .alert("Fehler", isPresented: .constant(vm.error != nil)) {
            Button("OK") { vm.error = nil }
        } message: { Text(vm.error ?? "") }
        .task { await vm.load() }
    }
}
