import SwiftUI

@MainActor
final class HealthViewModel: ObservableObject {
    @Published var mantisHistory: [HealthEntry] = []
    @Published var localSnapshots: [DailyHealthSnapshot] = []
    @Published var isLoading = false
    @Published var isSyncing = false
    @Published var error: String?
    @Published var showManualEntry = false
    @Published var selectedMetric: HealthMetric = .steps

    enum HealthMetric: String, CaseIterable {
        case steps = "Schritte"
        case hrv = "HRV"
        case sleep = "Schlaf"
        case restingHR = "Ruhepuls"
    }

    func load() async {
        isLoading = true
        do {
            mantisHistory = try await HealthAPI.shared.fetchHistory(days: 30)
            OfflineCache.shared.save(mantisHistory, key: "cache_health")
        } catch {
            mantisHistory = OfflineCache.shared.load([HealthEntry].self, key: "cache_health") ?? []
        }
        isLoading = false
    }

    func loadLocalHealth() async {
        let hk = HealthKitManager.shared
        guard hk.isAuthorized else { return }
        localSnapshots = (try? await hk.fetchRecentData(days: 30)) ?? []
    }

    func syncNow() async {
        isSyncing = true
        do {
            try await HealthKitManager.shared.syncToday()
            await load()
        } catch { self.error = error.localizedDescription }
        isSyncing = false
    }

    var latestEntry: HealthEntry? { mantisHistory.first }

    func chartData(for metric: HealthMetric) -> [(String, Double)] {
        mantisHistory.reversed().compactMap { entry in
            let value: Double?
            switch metric {
            case .steps: value = entry.steps.map(Double.init)
            case .hrv: value = entry.hrv
            case .sleep: value = entry.sleepDuration
            case .restingHR: value = entry.restingHr
            }
            guard let v = value, v > 0 else { return nil }
            return (String(entry.date.suffix(5)), v)
        }
    }
}

struct HealthView: View {
    @StateObject private var vm = HealthViewModel()
    @StateObject private var hk = HealthKitManager.shared

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if !hk.isAuthorized { healthKitPrompt } else { syncCard }
                    metricsGrid
                    chartSection
                    historyList
                }
                .padding(.vertical)
            }
            .navigationTitle("Gesundheit")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { vm.showManualEntry = true } label: { Image(systemName: "square.and.pencil") }
                }
            }
            .task {
                await hk.requestAuthorization()
                await vm.load()
                await vm.loadLocalHealth()
            }
            .refreshable {
                await vm.syncNow()
                await vm.loadLocalHealth()
            }
            .sheet(isPresented: $vm.showManualEntry, onDismiss: { Task { await vm.load() } }) {
                ManualHealthEntry()
            }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
        }
    }

    private var healthKitPrompt: some View {
        VStack(spacing: 12) {
            Image(systemName: "heart.fill").font(.largeTitle).foregroundStyle(.red)
            Text("HealthKit Zugriff benötigt").font(.headline)
            Text("Erlaube BodyOS den Zugriff auf deine Gesundheitsdaten um sie mit Mantis zu synchronisieren")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("Zugriff erlauben") { Task { await hk.requestAuthorization() } }
                .buttonStyle(.borderedProminent).tint(.red)
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private var syncCard: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Label("HealthKit verbunden", systemImage: "checkmark.circle.fill")
                    .font(.subheadline.bold()).foregroundStyle(.green)
                if let last = hk.lastSync {
                    Text("Sync: \(last.formatted(.relative(presentation: .named)))")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("Noch nicht synchronisiert").font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                Task { await vm.syncNow() }
            } label: {
                if vm.isSyncing {
                    ProgressView().scaleEffect(0.8)
                } else {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .foregroundStyle(.blue)
                }
            }
            .frame(width: 40, height: 40)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }

    private var metricsGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            if let e = vm.latestEntry {
                metricCard("Schritte", value: e.steps.map { "\($0)" } ?? "—",
                           unit: "heute", icon: "figure.walk", color: .green)
                metricCard("HRV", value: e.hrv.map { String(format: "%.0f", $0) } ?? "—",
                           unit: "ms", icon: "waveform.path.ecg", color: .blue)
                metricCard("Schlaf", value: e.sleepDuration.map { String(format: "%.1fh", $0) } ?? "—",
                           unit: "letzte Nacht", icon: "moon.fill", color: .purple)
                metricCard("Ruhepuls", value: e.restingHr.map { String(format: "%.0f", $0) } ?? "—",
                           unit: "bpm", icon: "heart.fill", color: .red)
            }
        }
        .padding(.horizontal)
    }

    private func metricCard(_ title: String, value: String, unit: String, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon).foregroundStyle(color)
                Text(title).font(.caption).foregroundStyle(.secondary)
            }
            Text(value).font(.title2.bold().monospacedDigit())
            Text(unit).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var chartSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Verlauf (30 Tage)").font(.headline)
                Spacer()
                Picker("Metrik", selection: $vm.selectedMetric) {
                    ForEach(HealthViewModel.HealthMetric.allCases, id: \.self) { m in
                        Text(m.rawValue).tag(m)
                    }
                }
                .pickerStyle(.menu)
            }
            .padding(.horizontal)

            let data = vm.chartData(for: vm.selectedMetric)
            if data.isEmpty {
                Text("Keine Daten")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity).padding()
            } else {
                SimpleBarChart(data: data, color: metricColor(vm.selectedMetric))
                    .frame(height: 140)
                    .padding(.horizontal)
            }
        }
        .padding(.vertical, 12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private func metricColor(_ metric: HealthViewModel.HealthMetric) -> Color {
        switch metric {
        case .steps: return .green
        case .hrv: return .blue
        case .sleep: return .purple
        case .restingHR: return .red
        }
    }

    private var historyList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Einträge").font(.headline).padding(.horizontal)
            ForEach(vm.mantisHistory.prefix(14)) { entry in
                HealthEntryRow(entry: entry)
            }
        }
    }
}

struct HealthEntryRow: View {
    let entry: HealthEntry

    var body: some View {
        HStack(spacing: 16) {
            Text(shortDate(entry.date)).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 50)
            VStack(spacing: 2) {
                HStack(spacing: 12) {
                    if let s = entry.steps { metricBadge("\(s)", "figure.walk", .green) }
                    if let h = entry.hrv { metricBadge(String(format: "%.0fms", h), "waveform.path.ecg", .blue) }
                    if let sl = entry.sleepDuration { metricBadge(String(format: "%.1fh", sl), "moon.fill", .purple) }
                }
            }
            Spacer()
            if let w = entry.weight {
                Text(String(format: "%.1f kg", w)).font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal)
    }

    private func metricBadge(_ value: String, _ icon: String, _ color: Color) -> some View {
        HStack(spacing: 3) {
            Image(systemName: icon).font(.caption2).foregroundStyle(color)
            Text(value).font(.caption2).foregroundStyle(.primary)
        }
    }

    private func shortDate(_ iso: String) -> String {
        String(iso.suffix(5))
    }
}

struct SimpleBarChart: View {
    let data: [(String, Double)]
    let color: Color

    var body: some View {
        let maxVal = data.map(\.1).max() ?? 1
        GeometryReader { geo in
            HStack(alignment: .bottom, spacing: 2) {
                ForEach(data.indices, id: \.self) { i in
                    let (label, value) = data[i]
                    VStack(spacing: 2) {
                        Spacer()
                        RoundedRectangle(cornerRadius: 3)
                            .fill(color.opacity(0.8))
                            .frame(height: max(4, geo.size.height * CGFloat(value / maxVal) * 0.85))
                        if data.count <= 14 {
                            Text(label).font(.system(size: 7)).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }
}

struct ManualHealthEntry: View {
    @State private var date = Date()
    @State private var hrv = ""
    @State private var restingHR = ""
    @State private var weight = ""
    @State private var sleep = ""
    @State private var steps = ""
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Datum") {
                    DatePicker("Datum", selection: $date, displayedComponents: .date)
                }
                Section("Messwerte") {
                    numericRow("HRV (ms)", $hrv)
                    numericRow("Ruhepuls (bpm)", $restingHR)
                    numericRow("Gewicht (kg)", $weight)
                    numericRow("Schlaf (Stunden)", $sleep)
                    numericRow("Schritte", $steps)
                }
            }
            .navigationTitle("Manuell erfassen")
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

    private func numericRow(_ label: String, _ binding: Binding<String>) -> some View {
        HStack {
            Text(label)
            Spacer()
            TextField("—", text: binding).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 80)
        }
    }

    private func save() async {
        isSaving = true
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withFullDate]
        let payload = HealthPushPayload(
            date: iso.string(from: date),
            hrv: Double(hrv), restingHr: Double(restingHR),
            weight: Double(weight), sleepDuration: Double(sleep),
            steps: Int(steps)
        )
        do { try await HealthAPI.shared.manualEntry(payload); dismiss() }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }
}
