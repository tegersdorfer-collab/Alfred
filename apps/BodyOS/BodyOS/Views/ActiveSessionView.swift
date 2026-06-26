import SwiftUI

@MainActor
final class ActiveSessionViewModel: ObservableObject {
    @Published var session: ActiveSession
    @Published var currentExerciseIndex: Int = 0
    @Published var showRPE = false
    @Published var showRestTimer = false
    @Published var isSaving = false
    @Published var saveError: String?
    @Published var sessionNotes = ""

    let plan: TodayPlan
    let restTimer = RestTimer()
    private let onComplete: () -> Void

    init(session: ActiveSession, plan: TodayPlan, onComplete: @escaping () -> Void) {
        self.session = session
        self.plan = plan
        self.onComplete = onComplete
    }

    var currentExercise: PlannedExercise? {
        plan.exercises[safe: currentExerciseIndex]
    }

    var allExercisesComplete: Bool { currentExerciseIndex >= plan.exercises.count }

    func logSet(exerciseName: String, weight: Double, reps: Int, setIndex: Int, isWarmup: Bool) {
        let logged = LoggedSet(exerciseName: exerciseName, weight: weight, reps: reps, setIndex: setIndex, isWarmup: isWarmup)
        session.loggedSets.append(logged)
        if !isWarmup { showRestTimer = true; Task { @MainActor in restTimer.start(seconds: 90) } }
    }

    func recordRPE(_ rpe: Int, for exercise: String) {
        session.rpeByExercise[exercise] = rpe
        showRPE = false
        currentExerciseIndex += 1
    }

    func skipRPE() { showRPE = false; currentExerciseIndex += 1 }
    func exerciseComplete() { restTimer.stop(); showRestTimer = false; showRPE = true }

    func finishSession() async {
        isSaving = true
        let sets = session.loggedSets.filter { !$0.isWarmup }.map {
            LogSetPayload(exercise: $0.exerciseName, setIndex: $0.setIndex, reps: $0.reps,
                          weightKg: $0.weight > 0 ? $0.weight : nil, distanceKm: nil)
        }
        let avgRPE = session.rpeByExercise.values.isEmpty ? nil :
            session.rpeByExercise.values.reduce(0, +) / session.rpeByExercise.count
        let req = LogWorkoutRequest(
            title: session.dayLabel,
            type: plan.dayType,
            durationMin: session.elapsedSeconds / 60,
            notes: sessionNotes.isEmpty ? nil : sessionNotes,
            rpe: avgRPE, sets: sets
        )
        do {
            let resp = try await FitnessAPI.shared.logWorkout(req)
            for (exercise, rpe) in session.rpeByExercise {
                try? await FitnessAPI.shared.logRPE(LogRPERequest(workoutId: resp.id, exercise: exercise, rpe: rpe))
            }
            isSaving = false; onComplete()
        } catch {
            saveError = error.localizedDescription; isSaving = false
        }
    }
}

struct ActiveSessionView: View {
    @StateObject private var vm: ActiveSessionViewModel
    @State private var elapsedDisplay = ""
    let onComplete: () -> Void

    init(session: ActiveSession, plan: TodayPlan, onComplete: @escaping () -> Void) {
        _vm = StateObject(wrappedValue: ActiveSessionViewModel(session: session, plan: plan, onComplete: onComplete))
        self.onComplete = onComplete
    }

    var body: some View {
        NavigationStack {
            ZStack {
                if vm.allExercisesComplete {
                    sessionCompleteView
                } else if vm.showRPE, let ex = vm.plan.exercises[safe: vm.currentExerciseIndex - 1] {
                    RPESliderView(exerciseName: ex.name) { rpe in vm.recordRPE(rpe, for: ex.name) } onSkip: { vm.skipRPE() }
                } else if let exercise = vm.currentExercise {
                    VStack(spacing: 0) {
                        ExerciseSetLogView(exercise: exercise,
                            onSetLogged: { w, r, si, iw in vm.logSet(exerciseName: exercise.name, weight: w, reps: r, setIndex: si, isWarmup: iw) },
                            onExerciseDone: { vm.exerciseComplete() })
                        if vm.showRestTimer { RestTimerView(timer: vm.restTimer) { vm.showRestTimer = false } }
                    }
                }
            }
            .navigationTitle(vm.plan.dayLabel)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Text(elapsedDisplay).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Text("\(min(vm.currentExerciseIndex + 1, vm.plan.exercises.count))/\(vm.plan.exercises.count)")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .alert("Fehler", isPresented: .constant(vm.saveError != nil)) {
                Button("OK") { vm.saveError = nil }
            } message: { Text(vm.saveError ?? "") }
        }
        .onAppear { startTimer() }
    }

    private var sessionCompleteView: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "checkmark.circle.fill").font(.system(size: 64)).foregroundStyle(.green)
            Text("Training abgeschlossen! 💪").font(.title2.bold())
            Text("\(vm.session.loggedSets.filter { !$0.isWarmup }.count) Sätze · \(vm.session.elapsedSeconds / 60) min")
                .foregroundStyle(.secondary)
            TextEditor(text: $vm.sessionNotes)
                .frame(height: 80).padding(8)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(alignment: .topLeading) {
                    if vm.sessionNotes.isEmpty {
                        Text("Notiz hinzufügen…").foregroundStyle(.tertiary).padding(12)
                    }
                }
                .padding(.horizontal)
            Button { Task { await vm.finishSession() } } label: {
                Group {
                    if vm.isSaving { ProgressView().tint(.white) }
                    else { HStack { Image(systemName: "square.and.arrow.up"); Text("Speichern & Beenden") } }
                }
                .frame(maxWidth: .infinity).padding()
                .background(Color.orange).foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            .disabled(vm.isSaving).padding(.horizontal)
            Spacer()
        }
    }

    private func startTimer() {
        let start = Date()
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            let e = Int(Date().timeIntervalSince(start))
            elapsedDisplay = String(format: "%d:%02d", e / 60, e % 60)
        }
    }
}

struct ExerciseSetLogView: View {
    let exercise: PlannedExercise
    let onSetLogged: (Double, Int, Int, Bool) -> Void
    let onExerciseDone: () -> Void

    @State private var currentPhase: Phase = .warmup
    @State private var currentSetIndex = 0
    @State private var weight: Double = 0
    @State private var reps: Int = 0

    enum Phase { case warmup, working }
    private var currentSets: [PlannedSet] { currentPhase == .warmup ? exercise.warmupSets : exercise.workingSets }
    private var currentSet: PlannedSet? { currentSets[safe: currentSetIndex] }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                VStack(spacing: 6) {
                    Text(exercise.name).font(.title2.bold())
                    Text(currentPhase == .warmup ? "Aufwärmen" : "Arbeitssätze")
                        .font(.subheadline).foregroundStyle(currentPhase == .warmup ? Color.secondary : Color.orange)
                }
                .padding(.top)

                HStack(spacing: 8) {
                    ForEach(Array(currentSets.enumerated()), id: \.offset) { i, _ in
                        Circle().fill(i < currentSetIndex ? Color.green : (i == currentSetIndex ? Color.orange : Color.gray.opacity(0.3)))
                            .frame(width: 10, height: 10)
                    }
                }

                if let set = currentSet { currentSetCard(set) }

                VStack(spacing: 16) {
                    adjuster(label: "Gewicht (kg)", value: $weight, step: 2.5, format: "%.1f")
                    adjuster(label: "Wiederholungen", value: Binding(get: { Double(reps) }, set: { reps = Int($0) }), step: 1, format: "%.0f")
                }
                .padding(.horizontal)

                Button { logCurrentSet() } label: {
                    Text("Satz abschließen ✓").frame(maxWidth: .infinity).padding()
                        .background(Color.orange).foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                .padding(.horizontal)

                if currentPhase == .warmup {
                    Button("Aufwärmen überspringen") {
                        currentPhase = .working; currentSetIndex = 0; applyDefaults()
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .onAppear { applyDefaults() }
    }

    private func adjuster(label: String, value: Binding<Double>, step: Double, format: String) -> some View {
        HStack {
            Text(label).font(.subheadline)
            Spacer()
            HStack(spacing: 16) {
                Button { value.wrappedValue = max(0, value.wrappedValue - step) } label: {
                    Image(systemName: "minus.circle.fill").font(.title2).foregroundStyle(.orange)
                }
                Text(String(format: format, value.wrappedValue))
                    .font(.title3.bold().monospacedDigit()).frame(minWidth: 60)
                Button { value.wrappedValue += step } label: {
                    Image(systemName: "plus.circle.fill").font(.title2).foregroundStyle(.orange)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func currentSetCard(_ set: PlannedSet) -> some View {
        VStack(spacing: 8) {
            Text(currentPhase == .warmup ? "Aufwärmsatz \(currentSetIndex + 1)" : "Satz \(currentSetIndex + 1)")
                .font(.caption.bold()).foregroundStyle(.secondary)
            HStack(spacing: 24) {
                if let w = set.weight {
                    VStack { Text(String(format: "%.1f", w)).font(.title.bold().monospacedDigit()); Text("kg").font(.caption2).foregroundStyle(.secondary) }
                }
                if let r = set.reps {
                    VStack { Text("\(r)").font(.title.bold().monospacedDigit()); Text("Wdh").font(.caption2).foregroundStyle(.secondary) }
                }
            }
            if let rpe = set.rpeTarget {
                Text("RPE Ziel: \(rpe)").font(.caption).foregroundStyle(.orange)
            }
        }
        .padding().frame(maxWidth: .infinity)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }

    private func logCurrentSet() {
        onSetLogged(weight, reps, currentSetIndex + 1, currentPhase == .warmup)
        let next = currentSetIndex + 1
        if next < currentSets.count {
            currentSetIndex = next; applyDefaults()
        } else if currentPhase == .warmup && !exercise.workingSets.isEmpty {
            currentPhase = .working; currentSetIndex = 0; applyDefaults()
        } else {
            onExerciseDone()
        }
    }

    private func applyDefaults() {
        if let set = currentSet { weight = set.weight ?? weight; reps = set.reps ?? reps }
    }
}

struct RestTimerView: View {
    @ObservedObject var timer: RestTimer
    let onSkip: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Pause").font(.headline)
                Spacer()
                Button("Überspringen", action: onSkip).font(.subheadline).foregroundStyle(.orange)
            }
            ZStack {
                Circle().stroke(Color.gray.opacity(0.2), lineWidth: 6)
                Circle().trim(from: 0, to: timer.progress)
                    .stroke(Color.orange, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.linear(duration: 1), value: timer.progress)
                Text("\(timer.secondsRemaining)s").font(.title2.bold().monospacedDigit())
            }
            .frame(width: 80, height: 80)
        }
        .padding().background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)
    }
}

struct RPESliderView: View {
    let exerciseName: String
    let onSubmit: (Int) -> Void
    let onSkip: () -> Void
    @State private var rpe: Double = 7

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "figure.strengthtraining.functional").font(.system(size: 48)).foregroundStyle(.orange)
            VStack(spacing: 8) {
                Text("Wie war \(exerciseName)?").font(.title2.bold())
                Text("Rate of Perceived Exertion").font(.caption).foregroundStyle(.secondary)
            }
            VStack(spacing: 8) {
                Text("\(Int(rpe))").font(.system(size: 72, weight: .bold, design: .rounded)).foregroundStyle(rpeColor)
                Text(rpeLabel).font(.headline).foregroundStyle(rpeColor)
            }
            Slider(value: $rpe, in: 1...10, step: 1).tint(rpeColor).padding(.horizontal, 32)
            HStack {
                Text("1\nLeicht").font(.caption2).multilineTextAlignment(.center)
                Spacer()
                Text("10\nMaximal").font(.caption2).multilineTextAlignment(.center)
            }
            .foregroundStyle(.secondary).padding(.horizontal, 32)
            Spacer()
            VStack(spacing: 12) {
                Button { onSubmit(Int(rpe)) } label: {
                    Text("RPE \(Int(rpe)) bestätigen").frame(maxWidth: .infinity).padding()
                        .background(rpeColor).foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                Button("Überspringen", action: onSkip).foregroundStyle(.secondary).font(.subheadline)
            }
            .padding(.horizontal).padding(.bottom, 32)
        }
    }

    private var rpeColor: Color {
        switch Int(rpe) {
        case 1...4: return .green
        case 5...7: return .orange
        default: return .red
        }
    }

    private var rpeLabel: String {
        switch Int(rpe) {
        case 1...3: return "Sehr leicht"
        case 4...5: return "Leicht"
        case 6...7: return "Mittel"
        case 8: return "Schwer"
        case 9: return "Sehr schwer"
        default: return "Maximal"
        }
    }
}
