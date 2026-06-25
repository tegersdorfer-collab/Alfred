import SwiftUI

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var plan: TodayPlan?
    @Published var nutrition: TodayNutritionResponse?
    @Published var healthEntries: [HealthEntry] = []
    @Published var isLoading = false
    @Published var isOffline = false

    func load() async {
        isLoading = true
        isOffline = false
        async let planResult: TodayPlan? = {
            do { return try await FitnessAPI.shared.fetchTodayPlan() }
            catch { return nil }
        }()
        async let nutritionResult: TodayNutritionResponse? = {
            do { return try await NutritionAPI.shared.todayNutrition() }
            catch { return nil }
        }()
        async let healthResult: [HealthEntry]? = {
            do { return try await HealthAPI.shared.fetchHistory(days: 7) }
            catch { return nil }
        }()

        plan = await planResult
        nutrition = await nutritionResult
        healthEntries = (await healthResult) ?? []
        isOffline = plan == nil && nutrition == nil

        if let p = plan { OfflineCache.shared.save(p, key: "cache_plan") }
        if let n = nutrition { OfflineCache.shared.save(n, key: "cache_nutrition") }

        if plan == nil { plan = OfflineCache.shared.load(TodayPlan.self, key: "cache_plan"); isOffline = true }
        if nutrition == nil { nutrition = OfflineCache.shared.load(TodayNutritionResponse.self, key: "cache_nutrition") }
        isLoading = false
    }

    var todaySteps: Int { healthEntries.first?.steps ?? 0 }
    var todayHRV: Double? { healthEntries.first?.hrv }
    var todaySleep: Double? { healthEntries.first?.sleepDuration }
    var totalCalories: Double { nutrition?.totals?.totalCalories ?? 0 }
    var totalProtein: Double { nutrition?.totals?.totalProtein ?? 0 }
    var totalCarbs: Double { nutrition?.totals?.totalCarbs ?? 0 }
    var totalFat: Double { nutrition?.totals?.totalFat ?? 0 }
}

struct DashboardView: View {
    @Binding var tabSelection: Int
    @StateObject private var vm = DashboardViewModel()
    @StateObject private var hk = HealthKitManager.shared
    @State private var showSession = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if vm.isOffline {
                        offlineBanner
                    }

                    greeting
                    healthRing
                    weightTrendCard
                    workoutCard
                    nutritionCard
                    quickActions
                }
                .padding(.vertical)
            }
            .navigationTitle("BodyOS")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await vm.load() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task {
                await hk.requestAuthorization()
                await vm.load()
                if hk.isAuthorized { try? await hk.syncToday() }
            }
            .refreshable {
                await vm.load()
                if hk.isAuthorized { try? await hk.syncToday() }
            }
            .fullScreenCover(isPresented: $showSession) {
                if let plan = vm.plan {
                    let session = ActiveSession(dayType: plan.dayType, dayLabel: plan.dayLabel)
                    ActiveSessionView(session: session, plan: plan) {
                        showSession = false
                        Task { await vm.load() }
                    }
                }
            }
        }
    }

    private var greeting: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(greetingText)
                    .font(.title2.bold())
                Text(formattedDate)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if vm.isLoading {
                ProgressView()
            }
        }
        .padding(.horizontal)
    }

    private var healthRing: some View {
        HStack(spacing: 16) {
            healthMetricCard(
                value: vm.todaySteps > 0 ? "\(vm.todaySteps)" : "—",
                label: "Schritte",
                icon: "figure.walk",
                color: .green,
                progress: min(Double(vm.todaySteps) / 10000, 1.0)
            )
            healthMetricCard(
                value: vm.todayHRV.map { String(format: "%.0f ms", $0) } ?? "—",
                label: "HRV",
                icon: "waveform.path.ecg",
                color: .blue,
                progress: vm.todayHRV.map { min($0 / 80, 1.0) } ?? 0
            )
            healthMetricCard(
                value: vm.todaySleep.map { String(format: "%.1fh", $0) } ?? "—",
                label: "Schlaf",
                icon: "moon.fill",
                color: .purple,
                progress: vm.todaySleep.map { min($0 / 8, 1.0) } ?? 0
            )
        }
        .padding(.horizontal)
    }

    private func healthMetricCard(value: String, label: String, icon: String, color: Color, progress: Double) -> some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .stroke(color.opacity(0.15), lineWidth: 5)
                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(color, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.easeOut, value: progress)
                Image(systemName: icon)
                    .font(.caption)
                    .foregroundStyle(color)
            }
            .frame(width: 52, height: 52)
            Text(value)
                .font(.caption.bold().monospacedDigit())
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var workoutCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Training heute", systemImage: "dumbbell.fill")
                    .font(.headline)
                    .foregroundStyle(.orange)
                Spacer()
                if let plan = vm.plan {
                    intensityBadge(plan.intensityFactor)
                }
            }
            if let plan = vm.plan {
                Text(plan.dayLabel)
                    .font(.title3.bold())
                Text("\(plan.exercises.count) Übungen · \(dayTypeEmoji(plan.dayType)) \(plan.dayType.capitalized)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                if !plan.alfredMessage.isEmpty {
                    Text(plan.alfredMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Button {
                    showSession = true
                } label: {
                    HStack {
                        Image(systemName: "play.fill")
                        Text("Training starten")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(Color.orange)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
            } else {
                Text("Kein Plan verfügbar")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private var nutritionCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Ernährung heute", systemImage: "fork.knife")
                    .font(.headline)
                    .foregroundStyle(.green)
                Spacer()
                Button { tabSelection = 2 } label: {
                    Text("Details").font(.caption).foregroundStyle(.green)
                }
            }

            let kcal = vm.totalCalories
            let protein = vm.totalProtein
            let carbs = vm.nutrition?.totals?.totalCarbs ?? 0
            let fat = vm.nutrition?.totals?.totalFat ?? 0
            let kcalTarget: Double = 2800
            let proteinTarget: Double = 180
            let carbsTarget: Double = 300
            let fatTarget: Double = 80

            HStack(spacing: 20) {
                calorieRing(kcal: kcal, target: kcalTarget)
                VStack(spacing: 8) {
                    macroProgressBar(label: "Protein", value: protein, target: proteinTarget, color: .blue)
                    macroProgressBar(label: "Kohlenhydrate", value: carbs, target: carbsTarget, color: .orange)
                    macroProgressBar(label: "Fett", value: fat, target: fatTarget, color: .yellow)
                }
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private func calorieRing(kcal: Double, target: Double) -> some View {
        let progress = min(kcal / target, 1.0)
        return ZStack {
            Circle()
                .stroke(Color.green.opacity(0.15), lineWidth: 8)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(Color.green, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut, value: progress)
            VStack(spacing: 2) {
                Text(String(format: "%.0f", kcal))
                    .font(.headline.monospacedDigit())
                Text("kcal")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 80, height: 80)
    }

    private func macroProgressBar(label: String, value: Double, target: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(label).font(.caption)
                Spacer()
                Text(String(format: "%.0f / %.0f", value, target)).font(.caption2).foregroundStyle(.secondary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(color.opacity(0.15)).frame(height: 6)
                    RoundedRectangle(cornerRadius: 3).fill(color)
                        .frame(width: geo.size.width * min(value / target, 1.0), height: 6)
                        .animation(.easeOut, value: value)
                }
            }
            .frame(height: 6)
        }
    }

    private var weightTrendCard: some View {
        let entries = vm.healthEntries.prefix(14).reversed() as Array
        let weights = entries.compactMap { $0.weight }
        guard !weights.isEmpty else { return AnyView(EmptyView()) }
        let latest = weights.last ?? 0
        let first = weights.first ?? 0
        let delta = latest - first
        let color: Color = delta <= 0 ? .green : .orange
        return AnyView(
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("Körpergewicht", systemImage: "scalemass.fill")
                        .font(.headline).foregroundStyle(.blue)
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(String(format: "%.1f kg", latest)).font(.subheadline.bold())
                        if weights.count > 1 {
                            Text(String(format: "%+.1f kg", delta))
                                .font(.caption2).foregroundStyle(color)
                        }
                    }
                }
                SparklineChart(values: weights, color: .blue)
                    .frame(height: 40)
            }
            .padding()
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .padding(.horizontal)
        )
    }

    private var quickActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Schnellaktionen").font(.headline).padding(.horizontal)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    quickActionButton("Training", icon: "dumbbell.fill", color: .orange) { tabSelection = 1 }
                    quickActionButton("Foto-Analyse", icon: "camera.fill", color: .green) { tabSelection = 2 }
                    quickActionButton("Gesundheit", icon: "heart.fill", color: .red) { tabSelection = 3 }
                    quickActionButton("Health sync", icon: "arrow.triangle.2.circlepath", color: .purple) {
                        Task { try? await hk.syncToday() }
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    private func quickActionButton(_ label: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(color)
                    .frame(width: 44, height: 44)
                    .background(color.opacity(0.12))
                    .clipShape(Circle())
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }
            .frame(width: 80)
        }
    }

    private var offlineBanner: some View {
        HStack {
            Image(systemName: "wifi.slash")
            Text("Offline — zeige gecachte Daten")
        }
        .font(.caption)
        .padding(8)
        .frame(maxWidth: .infinity)
        .background(Color.red.opacity(0.12))
        .foregroundStyle(.red)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.horizontal)
    }

    private var greetingText: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12: return "Guten Morgen 🌅"
        case 12..<17: return "Guten Mittag ☀️"
        case 17..<22: return "Guten Abend 🌆"
        default: return "Gute Nacht 🌙"
        }
    }

    private var formattedDate: String {
        let f = DateFormatter()
        f.dateStyle = .full
        f.locale = Locale(identifier: "de_DE")
        return f.string(from: Date())
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
        return Text(String(format: "×%.2f", factor))
            .font(.caption.bold().monospacedDigit())
            .foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.12))
            .clipShape(Capsule())
    }
}
