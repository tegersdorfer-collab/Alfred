import SwiftUI

@MainActor
final class ActiveSessionViewModel: ObservableObject {
    @Published var session: ActiveSession
    @Published var isSaving = false
    @Published var saveError: String?

    let plan: TodayPlan
    let restTimer = RestTimer()
    static let cacheKey = "active_session"
    private let onComplete: () -> Void

    init(session: ActiveSession, plan: TodayPlan, onComplete: @escaping () -> Void) {
        self.session = session
        self.plan = plan
        self.onComplete = onComplete
    }

    func persist() { OfflineCache.shared.save(session, key: Self.cacheKey) }

    func addSet(_ exIdx: Int) {
        guard session.exercises.indices.contains(exIdx) else { return }
        let last = session.exercises[exIdx].sets.last
        session.exercises[exIdx].sets.append(SessionSet(weight: last?.weight ?? 0, reps: last?.reps ?? 0))
        persist()
    }

    func deleteSet(_ exIdx: Int, _ setIdx: Int) {
        guard session.exercises.indices.contains(exIdx),
              session.exercises[exIdx].sets.indices.contains(setIdx) else { return }
        session.exercises[exIdx].sets.remove(at: setIdx)
        persist()
    }

    func toggleDone(_ exIdx: Int, _ setIdx: Int) {
        guard session.exercises.indices.contains(exIdx),
              session.exercises[exIdx].sets.indices.contains(setIdx) else { return }
        session.exercises[exIdx].sets[setIdx].done.toggle()
        let s = session.exercises[exIdx].sets[setIdx]
        if s.done && !s.isWarmup { restTimer.start(seconds: 90) }
        persist()
    }

    func addExercise(_ name: String) {
        session.exercises.append(SessionExercise(name: name, sets: [SessionSet()]))
        persist()
    }

    func removeExercise(_ exIdx: Int) {
        guard session.exercises.indices.contains(exIdx) else { return }
        session.exercises.remove(at: exIdx)
        persist()
    }

    func swapExercise(_ exIdx: Int, _ name: String) {
        guard session.exercises.indices.contains(exIdx) else { return }
        session.exercises[exIdx].name = name
        persist()
    }

    var doneSetCount: Int {
        session.exercises.reduce(0) { $0 + $1.sets.filter { $0.done }.count }
    }

    func finish() async {
        isSaving = true
        var payload: [LogSetPayload] = []
        for ex in session.exercises {
            var idx = 0
            for s in ex.sets where s.done {
                idx += 1
                payload.append(LogSetPayload(
                    exercise: ex.name, setIndex: idx,
                    reps: s.reps, weightKg: s.weight > 0 ? s.weight : nil,
                    rpe: s.rpe, isWarmup: s.isWarmup, isFailure: s.isFailure))
            }
        }
        let req = LogWorkoutRequest(
            title: session.dayLabel, type: plan.dayType,
            durationMin: session.elapsedSeconds / 60,
            notes: session.notes.isEmpty ? nil : session.notes,
            rpe: nil, sets: payload)
        do {
            _ = try await FitnessAPI.shared.logWorkout(req)
            OfflineCache.shared.clear(Self.cacheKey)
            isSaving = false
            onComplete()
        } catch {
            saveError = error.localizedDescription
            isSaving = false
        }
    }

    func cancel() {
        restTimer.stop()
        OfflineCache.shared.clear(Self.cacheKey)
        onComplete()
    }
}

struct ActiveSessionView: View {
    @StateObject private var vm: ActiveSessionViewModel
    @State private var elapsedDisplay = ""
    @State private var showCancelConfirm = false
    @State private var pickerTarget: PickerTarget?
    let onComplete: () -> Void

    enum PickerTarget: Identifiable {
        case add
        case swap(Int)
        var id: String { switch self { case .add: return "add"; case .swap(let i): return "swap\(i)" } }
    }

    init(session: ActiveSession, plan: TodayPlan, onComplete: @escaping () -> Void) {
        _vm = StateObject(wrappedValue: ActiveSessionViewModel(session: session, plan: plan, onComplete: onComplete))
        self.onComplete = onComplete
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(Array(vm.session.exercises.enumerated()), id: \.element.id) { exIdx, _ in
                    exerciseSection(exIdx)
                }
                Section {
                    Button { pickerTarget = .add } label: {
                        Label("Übung hinzufügen", systemImage: "plus.circle.fill")
                    }
                    notesField
                }
            }
            .listStyle(.insetGrouped)
            .safeAreaInset(edge: .bottom) {
                if vm.restTimer.isRunning {
                    RestTimerView(timer: vm.restTimer) { vm.restTimer.stop() }
                        .background(.ultraThinMaterial)
                }
            }
            .navigationTitle(vm.session.dayLabel)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Abbrechen", role: .destructive) { showCancelConfirm = true }
                        .font(.subheadline).tint(.red)
                }
                ToolbarItem(placement: .principal) {
                    Text(elapsedDisplay).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await vm.finish() }
                    } label: {
                        if vm.isSaving { ProgressView() } else { Text("Fertig").fontWeight(.semibold) }
                    }
                    .disabled(vm.isSaving || vm.doneSetCount == 0)
                }
            }
            .confirmationDialog("Training abbrechen?", isPresented: $showCancelConfirm, titleVisibility: .visible) {
                Button("Training verwerfen", role: .destructive) { vm.cancel() }
                Button("Weiter trainieren", role: .cancel) {}
            } message: { Text("Der bisherige Fortschritt geht verloren.") }
            .alert("Fehler", isPresented: .constant(vm.saveError != nil)) {
                Button("OK") { vm.saveError = nil }
            } message: { Text(vm.saveError ?? "") }
            .sheet(item: $pickerTarget) { target in
                ExercisePickerView { name in
                    switch target {
                    case .add: vm.addExercise(name)
                    case .swap(let i): vm.swapExercise(i, name)
                    }
                    pickerTarget = nil
                }
            }
        }
        .onAppear { startTimer() }
    }

    @ViewBuilder
    private func exerciseSection(_ exIdx: Int) -> some View {
        let ex = vm.session.exercises[exIdx]
        Section {
            ForEach(Array(ex.sets.enumerated()), id: \.element.id) { setIdx, _ in
                SetRow(set: $vm.session.exercises[exIdx].sets[setIdx],
                       number: setIdx + 1,
                       onDone: { vm.toggleDone(exIdx, setIdx); vm.persist() },
                       onChange: { vm.persist() })
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) { vm.deleteSet(exIdx, setIdx) } label: {
                            Label("Löschen", systemImage: "trash")
                        }
                    }
            }
            Button { vm.addSet(exIdx) } label: {
                Label("Satz", systemImage: "plus").font(.subheadline)
            }
        } header: {
            ExerciseHeader(name: ex.name,
                           onSwap: { pickerTarget = .swap(exIdx) },
                           onRemove: { vm.removeExercise(exIdx) })
        }
    }

    private var notesField: some View {
        TextField("Notiz zum Training…", text: $vm.session.notes, axis: .vertical)
            .onChange(of: vm.session.notes) { _, _ in vm.persist() }
    }

    private func startTimer() {
        let start = vm.session.startTime
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            let e = Int(Date().timeIntervalSince(start))
            elapsedDisplay = String(format: "%d:%02d", e / 60, e % 60)
        }
    }
}

// MARK: - Exercise Header (Name + letztes Mal + Menü)

struct ExerciseHeader: View {
    let name: String
    let onSwap: () -> Void
    let onRemove: () -> Void
    @State private var lastHint: String?
    @State private var showRemoveConfirm = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(.subheadline.bold()).textCase(nil).foregroundStyle(.primary)
                if let hint = lastHint {
                    Text(hint).font(.caption2).textCase(nil).foregroundStyle(.secondary)
                }
            }
            Spacer()
            Menu {
                Button { onSwap() } label: { Label("Übung tauschen", systemImage: "arrow.left.arrow.right") }
                Button(role: .destructive) { showRemoveConfirm = true } label: { Label("Übung entfernen", systemImage: "trash") }
            } label: {
                Image(systemName: "ellipsis.circle").foregroundStyle(.secondary)
            }
        }
        .task { await loadLast() }
        .confirmationDialog("Übung entfernen?", isPresented: $showRemoveConfirm, titleVisibility: .visible) {
            Button("Entfernen", role: .destructive) { onRemove() }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private func loadLast() async {
        guard let sets = try? await FitnessAPI.shared.lastSets(exercise: name), !sets.isEmpty,
              let top = sets.max(by: { ($0.weightKg ?? 0) < ($1.weightKg ?? 0) }) else { return }
        let kg = top.weightKg.map { String(format: "%.1f kg", $0) } ?? "–"
        lastHint = "Letztes Mal: \(kg) × \(top.reps ?? 0)"
    }
}

// MARK: - Set Row

struct SetRow: View {
    @Binding var set: SessionSet
    let number: Int
    let onDone: () -> Void
    let onChange: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Text("\(number)").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 16)

            Button { set.isWarmup.toggle(); onChange() } label: {
                Text("W").font(.caption2.bold())
                    .frame(width: 22, height: 22)
                    .background(set.isWarmup ? Color.orange.opacity(0.25) : Color(.tertiarySystemFill))
                    .foregroundStyle(set.isWarmup ? .orange : .secondary)
                    .clipShape(Circle())
            }.buttonStyle(.plain)

            TextField("kg", value: $set.weight, format: .number)
                .keyboardType(.decimalPad).multilineTextAlignment(.center)
                .frame(width: 56).textFieldStyle(.roundedBorder)
                .onChange(of: set.weight) { _, _ in onChange() }
            Text("×").foregroundStyle(.secondary)
            TextField("Wdh", value: $set.reps, format: .number)
                .keyboardType(.numberPad).multilineTextAlignment(.center)
                .frame(width: 44).textFieldStyle(.roundedBorder)
                .onChange(of: set.reps) { _, _ in onChange() }

            Menu {
                Button("Kein RPE") { set.rpe = nil; onChange() }
                ForEach(6...10, id: \.self) { v in Button("RPE \(v)") { set.rpe = v; onChange() } }
            } label: {
                Text(set.rpe.map { "\($0)" } ?? "–").font(.caption.bold())
                    .frame(width: 26, height: 22)
                    .background(Color(.tertiarySystemFill)).clipShape(RoundedRectangle(cornerRadius: 6))
                    .foregroundStyle(set.rpe == nil ? Color.secondary : Color.orange)
            }

            Button { set.isFailure.toggle(); onChange() } label: {
                Text("F").font(.caption2.bold())
                    .frame(width: 22, height: 22)
                    .background(set.isFailure ? Color.red.opacity(0.2) : Color(.tertiarySystemFill))
                    .foregroundStyle(set.isFailure ? .red : .secondary)
                    .clipShape(Circle())
            }.buttonStyle(.plain)

            Button { onDone() } label: {
                Image(systemName: set.done ? "checkmark.circle.fill" : "circle")
                    .font(.title3).foregroundStyle(set.done ? .green : .secondary)
            }.buttonStyle(.plain)
        }
        .listRowBackground(set.done ? Color.green.opacity(0.06) : nil)
    }
}

// MARK: - Exercise Picker

struct ExercisePickerView: View {
    let onPick: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var exercises: [ExerciseItem] = []
    @State private var query = ""
    @State private var custom = ""

    private var filtered: [ExerciseItem] {
        query.isEmpty ? exercises : exercises.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            List {
                if !custom.trimmingCharacters(in: .whitespaces).isEmpty {
                    Button { onPick(custom); dismiss() } label: {
                        Label("Hinzufügen: \(custom)", systemImage: "plus")
                    }
                }
                ForEach(filtered) { ex in
                    Button(ex.name) { onPick(ex.name); dismiss() }
                        .foregroundStyle(.primary)
                }
            }
            .searchable(text: $query, prompt: "Übung suchen")
            .navigationTitle("Übung wählen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
            }
            .safeAreaInset(edge: .bottom) {
                HStack {
                    TextField("Eigene Übung…", text: $custom).textFieldStyle(.roundedBorder)
                }.padding()
            }
            .task {
                exercises = (try? await FitnessAPI.shared.fetchExercises()) ?? []
            }
        }
    }
}

// MARK: - Rest Timer (wiederverwendet)

struct RestTimerView: View {
    @ObservedObject var timer: RestTimer
    let onSkip: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            Image(systemName: "timer").foregroundStyle(.orange)
            Text("Pause").font(.subheadline.bold())
            Spacer()
            Text("\(timer.secondsRemaining)s").font(.title3.bold().monospacedDigit())
            Button("Überspringen", action: onSkip).font(.subheadline).foregroundStyle(.orange)
        }
        .padding()
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }
}
