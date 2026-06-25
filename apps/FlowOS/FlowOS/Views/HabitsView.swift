import SwiftUI

@MainActor
final class HabitsViewModel: ObservableObject {
    @Published var habits: [Habit] = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var showCreate = false
    @Published var selectedHabit: Habit?
    @Published var habitHistory: [String: [HabitLog]] = [:]

    var doneCount: Int { habits.filter { $0.completedToday == true }.count }

    func load() async {
        isLoading = true; error = nil
        do {
            habits = try await FlowAPI.shared.fetchHabits()
            OfflineCache.shared.save(habits, key: "cache_habits")
        } catch {
            self.error = error.localizedDescription
            habits = OfflineCache.shared.load([Habit].self, key: "cache_habits") ?? []
        }
        isLoading = false
    }

    func toggle(_ habit: Habit) async {
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withFullDate]
        if habit.completedToday == true {
            try? await FlowAPI.shared.unlogHabit(habit.id)
        } else {
            let req = LogHabitRequest(date: iso.string(from: Date()), completed: true, note: nil)
            try? await FlowAPI.shared.logHabit(habit.id, req)
        }
        await load()
    }

    func delete(_ habit: Habit) async {
        try? await FlowAPI.shared.deleteHabit(habit.id)
        await load()
    }
}

struct HabitsView: View {
    @StateObject private var vm = HabitsViewModel()
    @State private var selectedTab = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $selectedTab) {
                    Text("Heute").tag(0)
                    Text("Statistik").tag(1)
                }
                .pickerStyle(.segmented).padding()

                if selectedTab == 0 { todayView } else { statsView }
            }
            .navigationTitle("Gewohnheiten")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { vm.showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $vm.showCreate, onDismiss: { Task { await vm.load() } }) {
                HabitCreateView()
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
        }
    }

    private var todayView: some View {
        ScrollView {
            VStack(spacing: 16) {
                progressHeader
                if vm.isLoading { ProgressView().padding() }
                else if vm.habits.isEmpty {
                    ContentUnavailableView("Keine Gewohnheiten", systemImage: "circle.dotted",
                                          description: Text("Erstelle deine erste Gewohnheit")).padding(.top, 40)
                } else { habitGrid }
            }
            .padding()
        }
    }

    private var statsView: some View {
        ScrollView {
            VStack(spacing: 16) {
                ForEach(vm.habits) { habit in
                    HabitStatsCard(habit: habit)
                }
            }
            .padding()
        }
    }

    private var progressHeader: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle().stroke(Color.indigo.opacity(0.15), lineWidth: 12)
                Circle()
                    .trim(from: 0, to: vm.habits.count > 0 ? CGFloat(vm.doneCount) / CGFloat(vm.habits.count) : 0)
                    .stroke(Color.indigo, style: StrokeStyle(lineWidth: 12, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.spring(), value: vm.doneCount)
                VStack(spacing: 2) {
                    Text("\(vm.doneCount)/\(vm.habits.count)").font(.title2.weight(.bold))
                    Text("heute").font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(width: 120, height: 120)
            Text(vm.doneCount == vm.habits.count && !vm.habits.isEmpty ? "Perfekter Tag! 🎉" : "Weiter so!")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        .padding().frame(maxWidth: .infinity)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var habitGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            ForEach(vm.habits) { habit in
                HabitDotCard(habit: habit) { Task { await vm.toggle(habit) } }
                    .contextMenu {
                        Button(role: .destructive) { Task { await vm.delete(habit) } } label: {
                            Label("Löschen", systemImage: "trash")
                        }
                    }
            }
        }
    }
}

struct HabitDotCard: View {
    let habit: Habit
    let onTap: () -> Void
    private var done: Bool { habit.completedToday ?? false }
    private var accent: Color { habitAccentColor(habit.color) }

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 10) {
                ZStack {
                    Circle().fill(done ? accent : accent.opacity(0.12)).frame(width: 56, height: 56)
                    Image(systemName: habit.icon ?? "star").font(.title2).foregroundStyle(done ? .white : accent)
                }
                Text(habit.name).font(.subheadline.weight(.medium)).multilineTextAlignment(.center).lineLimit(2)
                if let streak = habit.streak, streak > 0 {
                    Label("\(streak)", systemImage: "flame.fill").font(.caption.weight(.semibold)).foregroundStyle(.orange)
                }
            }
            .padding(14).frame(maxWidth: .infinity)
            .background(done ? accent.opacity(0.1) : Color(.secondarySystemBackground))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(done ? accent : Color.clear, lineWidth: 2))
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain)
    }
}

struct HabitStatsCard: View {
    let habit: Habit
    @State private var stats: HabitStats?
    @State private var logs: [HabitLog] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: habit.icon ?? "star")
                    .foregroundStyle(habitAccentColor(habit.color))
                Text(habit.name).font(.subheadline.bold())
                Spacer()
                if let streak = habit.streak {
                    Label("\(streak)", systemImage: "flame.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
            heatmapView
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var heatmapView: some View {
        let last90 = last90Days()
        let logDates = Set(logs.filter { $0.completed }.map { $0.date })
        return LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 3), count: 13), spacing: 3) {
            ForEach(last90, id: \.self) { day in
                let completed = logDates.contains(day)
                RoundedRectangle(cornerRadius: 2)
                    .fill(completed ? habitAccentColor(habit.color) : Color.gray.opacity(0.15))
                    .aspectRatio(1, contentMode: .fit)
            }
        }
        .task { await loadLogs() }
    }

    private func loadLogs() async {
        guard let s = try? await FlowAPI.shared.habitStats(habit.id) else { return }
        logs = s.logs
    }

    private func last90Days() -> [String] {
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withFullDate]
        return (0..<90).reversed().compactMap { Calendar.current.date(byAdding: .day, value: -$0, to: Date()) }
            .map { iso.string(from: $0) }
    }
}
