import SwiftUI
import SwiftData

@MainActor
final class WorkoutViewModel: ObservableObject {
    @Published var plan: TodayPlan?
    @Published var history: [WorkoutHistoryItem] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var activeSession: ActiveSession?
    @Published var selectedTab = 0

    func loadPlan() async {
        isLoading = true; error = nil
        do {
            plan = try await FitnessAPI.shared.fetchTodayPlan()
            OfflineCache.shared.save(plan!, key: "cache_plan")
        } catch {
            self.error = error.localizedDescription
            plan = OfflineCache.shared.load(TodayPlan.self, key: "cache_plan")
        }
        isLoading = false
    }

    func loadHistory() async {
        do {
            history = try await FitnessAPI.shared.fetchHistory(limit: 60)
            OfflineCache.shared.save(history, key: "cache_workout_history")
        } catch {
            history = OfflineCache.shared.load([WorkoutHistoryItem].self, key: "cache_workout_history") ?? []
        }
    }

    func startSession() {
        guard let plan else { return }
        activeSession = ActiveSession(dayType: plan.dayType, dayLabel: plan.dayLabel)
    }

    func markJogDone(auto: Bool, km: Double? = nil, min: Int? = nil) async {
        try? await FitnessAPI.shared.markJogDone(
            distanceKm: km, durationMin: min, source: auto ? "healthkit" : "manual")
        await loadPlan()
    }

    func markRestDay() async {
        try? await FitnessAPI.shared.markRestDay()
        await loadPlan()
    }

    /// Beim Öffnen des Jog-Tags HealthKit nach einem Lauf fragen und ggf. auto-abhaken.
    func autoDetectRun() async {
        guard let plan, plan.dayType == "jog", plan.doneToday != true else { return }
        if let run = await HealthKitManager.shared.fetchTodayRun(), run.distanceKm > 0.3 {
            await markJogDone(auto: true, km: run.distanceKm, min: run.durationMin)
        }
    }
}

struct WorkoutView: View {
    @StateObject private var vm = WorkoutViewModel()
    @State private var showSession = false
    @State private var selectedTab = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $selectedTab) {
                    Text("Heute").tag(0)
                    Text("Verlauf").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()

                if selectedTab == 0 {
                    todayContent
                } else {
                    historyContent
                }
            }
            .navigationTitle("Training")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await vm.loadPlan() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task {
                await vm.loadPlan()
                await vm.loadHistory()
                if !showSession,
                   let saved = OfflineCache.shared.load(ActiveSession.self, key: ActiveSessionViewModel.cacheKey) {
                    vm.activeSession = saved
                    showSession = true
                }
            }
            .fullScreenCover(isPresented: $showSession) {
                if let session = vm.activeSession, let plan = vm.plan {
                    ActiveSessionView(session: session, plan: plan) {
                        vm.activeSession = nil
                        showSession = false
                        Task { await vm.loadPlan(); await vm.loadHistory() }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var todayContent: some View {
        if vm.isLoading {
            Spacer()
            ProgressView("Alfred denkt nach…")
            Spacer()
        } else if let plan = vm.plan {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    dayHeaderCard(plan)
                    if let week = plan.planWeek, plan.planSource == "alfred" {
                        Text("Plan: Woche \(week)/6 · von Alfred")
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal)
                    }
                    if plan.doneToday == true {
                        doneCard(plan)
                    } else if plan.dayType == "jog" {
                        jogCard(plan)
                    } else {
                        if !plan.alfredMessage.isEmpty { alfredCard(plan.alfredMessage) }
                        if let health = plan.health { healthCard(health) }
                        exerciseList(plan)
                        startButton
                        restButton
                    }
                    Button {
                        Task { try? await FitnessAPI.shared.generatePlan(); await vm.loadPlan() }
                    } label: {
                        Label("Neuen Plan generieren", systemImage: "sparkles")
                            .font(.caption).frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                    .padding(.horizontal)
                }
                .padding(.bottom, 32)
            }
            .task { await vm.autoDetectRun() }
        } else {
            Spacer()
            errorView
            Spacer()
        }
    }

    private func doneCard(_ plan: TodayPlan) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill").font(.largeTitle).foregroundStyle(.green)
            Text("\(plan.dayLabel) erledigt").font(.headline)
            if let next = plan.nextLabel {
                Text("Morgen: \(next)").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 32)
        .background(Color.green.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)
    }

    private func jogCard(_ plan: TodayPlan) -> some View {
        VStack(spacing: 16) {
            VStack(spacing: 8) {
                Image(systemName: "figure.run").font(.largeTitle).foregroundStyle(.orange)
                Text("Heute: Joggen").font(.headline)
                Text("Läuft über Strava / Coros — wird automatisch erkannt.")
                    .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            Button { Task { await vm.markJogDone(auto: false) } } label: {
                Label("Joggen erledigt", systemImage: "checkmark")
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.orange).foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            restButton
        }
        .padding().background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)
    }

    private var restButton: some View {
        Button { Task { await vm.markRestDay() } } label: {
            Label("Restday einlegen", systemImage: "moon.zzz")
                .frame(maxWidth: .infinity).padding()
                .foregroundStyle(.secondary)
                .background(Color(.tertiarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .padding(.horizontal)
    }

    private var historyContent: some View {
        Group {
            if vm.history.isEmpty {
                VStack {
                    Spacer()
                    ContentUnavailableView("Kein Verlauf", systemImage: "calendar")
                    Spacer()
                }
            } else {
                ScrollView {
                    VStack(spacing: 12) {
                        streakCard
                        heatmapView
                        LazyVStack(spacing: 8) {
                            ForEach(vm.history) { item in
                                WorkoutHistoryCard(item: item)
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            }
        }
    }

    private var streakCard: some View {
        let streak = computeStreak(vm.history)
        return HStack(spacing: 16) {
            VStack(spacing: 4) {
                HStack(spacing: 4) {
                    Text("\(streak)").font(.system(size: 36, weight: .bold, design: .rounded))
                    Text("🔥").font(.title)
                }
                Text("Streak").font(.caption).foregroundStyle(.secondary)
            }
            Divider().frame(height: 44)
            VStack(alignment: .leading, spacing: 4) {
                Text("\(vm.history.count) Trainings").font(.subheadline.bold())
                Text("letzten 60 Tage").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding()
        .background(streak > 0 ? Color.orange.opacity(0.08) : Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private func computeStreak(_ history: [WorkoutHistoryItem]) -> Int {
        let fmt = DateFormatter(); fmt.dateFormat = "yyyy-MM-dd"
        let dates = Set(history.compactMap { fmt.date(from: String($0.date.prefix(10))) }
                                .map { Calendar.current.startOfDay(for: $0) })
        var streak = 0
        var current = Calendar.current.startOfDay(for: Date())
        while dates.contains(current) || (streak == 0 && dates.contains(Calendar.current.date(byAdding: .day, value: -1, to: current)!)) {
            if dates.contains(current) { streak += 1 }
            guard let prev = Calendar.current.date(byAdding: .day, value: -1, to: current) else { break }
            current = prev
            if !dates.contains(current) { break }
        }
        return streak
    }

    private func dayHeaderCard(_ plan: TodayPlan) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(plan.dayLabel).font(.title2.bold())
                Text(dayTypeEmoji(plan.dayType) + " " + plan.dayType.capitalized)
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            intensityBadge(plan.intensityFactor)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private func alfredCard(_ msg: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "brain.head.profile").font(.title2).foregroundStyle(.orange)
            Text(msg).font(.subheadline)
        }
        .padding()
        .background(Color.orange.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }

    private func healthCard(_ h: HealthSnapshot) -> some View {
        HStack(spacing: 24) {
            if let hrv = h.hrv {
                healthMetric(String(format: "%.0f ms", hrv), label: "HRV", icon: "waveform.path.ecg")
            }
            if let sleep = h.sleepHours {
                healthMetric(String(format: "%.1fh", sleep), label: "Schlaf", icon: "moon.fill")
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }

    private func healthMetric(_ value: String, label: String, icon: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(value).font(.headline)
                Text(label).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func exerciseList(_ plan: TodayPlan) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Heutiger Plan").font(.headline).padding(.horizontal)
            ForEach(plan.exercises) { exercise in
                ExercisePreviewCard(exercise: exercise)
            }
        }
    }

    private var startButton: some View {
        Button {
            vm.startSession()
            showSession = true
        } label: {
            HStack {
                Image(systemName: "play.fill")
                Text("Training starten").fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.orange)
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .padding(.horizontal)
    }

    private var errorView: some View {
        VStack(spacing: 16) {
            Image(systemName: "wifi.slash").font(.largeTitle).foregroundStyle(.secondary)
            Text("Alfred nicht erreichbar").font(.headline)
            if let err = vm.error { Text(err).font(.caption).foregroundStyle(.secondary) }
            Button("Erneut") { Task { await vm.loadPlan() } }.buttonStyle(.bordered)
        }
    }

    private var heatmapView: some View {
        let last90 = last90Days()
        let workoutDates = Set(vm.history.map { String($0.date.prefix(10)) })
        return VStack(alignment: .leading, spacing: 8) {
            Text("90-Tage Verlauf").font(.headline).padding(.horizontal)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 13), spacing: 4) {
                ForEach(last90, id: \.self) { day in
                    let hasWorkout = workoutDates.contains(day)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(hasWorkout ? Color.orange : Color.gray.opacity(0.2))
                        .aspectRatio(1, contentMode: .fit)
                }
            }
            .padding(.horizontal)
        }
    }

    private func last90Days() -> [String] {
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withFullDate]
        return (0..<90).reversed().compactMap { Calendar.current.date(byAdding: .day, value: -$0, to: Date()) }
            .map { iso.string(from: $0) }
    }

    private func dayTypeEmoji(_ type: String) -> String {
        switch type {
        case "upper": return "💪"
        case "lower": return "🦵"
        case "jog": return "🏃"
        default: return "🏋️"
        }
    }

    private func intensityBadge(_ factor: Double) -> some View {
        let color: Color = factor >= 1.0 ? .green : (factor <= 0.88 ? .red : .orange)
        return VStack(spacing: 4) {
            Text(String(format: "×%.2f", factor)).font(.headline.monospacedDigit()).foregroundStyle(color)
            Text("Intensität").font(.caption2).foregroundStyle(.secondary)
        }
    }
}

struct WorkoutHistoryCard: View {
    let item: WorkoutHistoryItem

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 4)
                .fill(typeColor)
                .frame(width: 5)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(item.title).font(.subheadline.bold())
                    Spacer()
                    Text(formatDate(item.date)).font(.caption).foregroundStyle(.secondary)
                }
                HStack(spacing: 16) {
                    if let dur = item.durationMin {
                        Label("\(dur) min", systemImage: "clock")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let rpe = item.rpe {
                        Label("RPE \(rpe)", systemImage: "gauge.medium")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let sets = item.sets {
                        Label("\(sets.count) Sätze", systemImage: "list.bullet")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var typeColor: Color {
        switch item.type {
        case "run": return .green
        case "upper": return .orange
        case "lower": return .blue
        default: return .orange
        }
    }

    private func formatDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        guard let d = f.date(from: iso) else { return iso }
        let df = DateFormatter(); df.dateStyle = .short; df.locale = Locale(identifier: "de_DE")
        return df.string(from: d)
    }
}

struct ExercisePreviewCard: View {
    let exercise: PlannedExercise

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 6) {
                Text(exercise.name).font(.subheadline.bold())
                HStack(spacing: 12) {
                    if let w = exercise.workingSets.first?.weight {
                        Label(String(format: "%.1f kg", w), systemImage: "scalemass")
                            .font(.caption).foregroundStyle(.orange)
                    }
                    if let r = exercise.workingSets.first?.reps {
                        Text("\(exercise.workingSets.count)×\(r) Wdh")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let km = exercise.workingSets.first?.distanceKm {
                        Label(String(format: "%.1f km", km), systemImage: "figure.run")
                            .font(.caption).foregroundStyle(.orange)
                    }
                }
            }
            Spacer()
            if let rpe = exercise.workingSets.first?.rpeTarget {
                Text("RPE \(rpe)")
                    .font(.caption.bold())
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Color.orange.opacity(0.12))
                    .foregroundStyle(.orange)
                    .clipShape(Capsule())
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }
}
