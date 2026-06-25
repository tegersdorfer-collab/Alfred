import SwiftUI

@MainActor
final class TodayViewModel: ObservableObject {
    @Published var tasks: [AlfredTask] = []
    @Published var events: [CalendarEvent] = []
    @Published var habits: [Habit] = []
    @Published var isLoading = false
    @Published var isOffline = false

    var todayTasks: [AlfredTask] {
        tasks.filter { $0.status == "todo" || $0.status == "in_progress" }
              .sorted { priorityWeight($0.priority ?? "medium") > priorityWeight($1.priority ?? "medium") }
              .prefix(5).map { $0 }
    }

    var todayEvents: [CalendarEvent] {
        let today = isoToday()
        return events.filter { $0.displayStart.hasPrefix(today) }
                     .sorted { $0.displayStart < $1.displayStart }
    }

    var pendingHabits: [Habit] { habits.filter { !($0.completedToday ?? false) } }
    var doneHabits: [Habit] { habits.filter { $0.completedToday ?? false } }

    func load() async {
        isLoading = true; isOffline = false
        async let t: [AlfredTask]? = { try? await FlowAPI.shared.fetchTasks() }()
        async let e: [CalendarEvent]? = { try? await FlowAPI.shared.fetchEvents(days: 7) }()
        async let h: [Habit]? = { try? await FlowAPI.shared.fetchHabits() }()

        let tv = await t; let ev = await e; let hv = await h
        tasks = tv ?? OfflineCache.shared.load([AlfredTask].self, key: "cache_tasks") ?? []
        events = ev ?? OfflineCache.shared.load([CalendarEvent].self, key: "cache_events") ?? []
        habits = hv ?? OfflineCache.shared.load([Habit].self, key: "cache_habits") ?? []
        isOffline = tv == nil && ev == nil && hv == nil

        if let t = tv { OfflineCache.shared.save(t, key: "cache_tasks") }
        if let e = ev { OfflineCache.shared.save(e, key: "cache_events") }
        if let h = hv { OfflineCache.shared.save(h, key: "cache_habits") }
        isLoading = false
    }

    func completeTask(_ task: AlfredTask) async {
        try? await FlowAPI.shared.completeTask(task.id)
        await load()
    }

    func toggleHabit(_ habit: Habit) async {
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withFullDate]
        let req = LogHabitRequest(date: iso.string(from: Date()), completed: !(habit.completedToday ?? false), note: nil)
        if habit.completedToday == true {
            try? await FlowAPI.shared.unlogHabit(habit.id)
        } else {
            try? await FlowAPI.shared.logHabit(habit.id, req)
        }
        await load()
    }

    private func isoToday() -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        return f.string(from: Date())
    }

    private func priorityWeight(_ p: String) -> Int {
        switch p { case "urgent": return 4; case "high": return 3; case "medium": return 2; default: return 1 }
    }
}

struct TodayView: View {
    @StateObject private var vm = TodayViewModel()
    @State private var showCreateTask = false
    @State private var showCreateEvent = false
    @State private var showFocusTimer = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if vm.isOffline { offlineBanner }
                    dateHeader
                    focusButton
                    if !vm.todayEvents.isEmpty { eventsSection }
                    habitsSection
                    tasksSection
                }
                .padding(.vertical)
            }
            .navigationTitle("Heute")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showFocusTimer = true } label: {
                        Label("Fokus", systemImage: "timer")
                    }
                    .foregroundStyle(.indigo)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { showCreateTask = true } label: { Label("Aufgabe", systemImage: "plus.circle") }
                        Button { showCreateEvent = true } label: { Label("Termin", systemImage: "calendar.badge.plus") }
                    } label: { Image(systemName: "plus") }
                }
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
            .sheet(isPresented: $showCreateTask, onDismiss: { Task { await vm.load() } }) {
                TaskEditorView(task: nil)
            }
            .sheet(isPresented: $showCreateEvent, onDismiss: { Task { await vm.load() } }) {
                EventEditorView(date: Date())
            }
            .sheet(isPresented: $showFocusTimer) {
                FocusTimerView()
            }
        }
    }

    private var focusButton: some View {
        Button { showFocusTimer = true } label: {
            HStack(spacing: 12) {
                Image(systemName: "brain.head.profile")
                    .font(.title3)
                    .foregroundStyle(.indigo)
                    .frame(width: 40, height: 40)
                    .background(Color.indigo.opacity(0.1))
                    .clipShape(Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text("Fokus-Timer")
                        .font(.subheadline.bold())
                        .foregroundStyle(.primary)
                    Text("25 min Pomodoro starten")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(14)
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
        .padding(.horizontal)
    }

    private var dateHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(dayGreeting).font(.subheadline).foregroundStyle(.secondary)
                Text(formattedDate).font(.title3.bold())
            }
            Spacer()
            habitProgressRing
        }
        .padding(.horizontal)
    }

    private var habitProgressRing: some View {
        let done = vm.doneHabits.count
        let total = vm.habits.count
        let progress = total > 0 ? CGFloat(done) / CGFloat(total) : 0
        return ZStack {
            Circle().stroke(Color.indigo.opacity(0.15), lineWidth: 4)
            Circle().trim(from: 0, to: progress)
                .stroke(Color.indigo, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.spring(), value: done)
            VStack(spacing: 1) {
                Text("\(done)").font(.caption.bold())
                Text("/\(total)").font(.system(size: 8)).foregroundStyle(.secondary)
            }
        }
        .frame(width: 48, height: 48)
    }

    private var eventsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Termine heute", systemImage: "calendar").font(.headline).padding(.horizontal)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(vm.todayEvents) { event in
                        EventChip(event: event)
                    }
                }
                .padding(.horizontal)
            }
        }
    }

    private var habitsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Gewohnheiten", systemImage: "circle.dotted").font(.headline)
                Spacer()
                Text("\(vm.doneHabits.count)/\(vm.habits.count)").font(.caption).foregroundStyle(.secondary)
            }
            .padding(.horizontal)

            if vm.habits.isEmpty {
                Text("Keine Gewohnheiten").font(.subheadline).foregroundStyle(.secondary).padding(.horizontal)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(vm.habits) { habit in
                            TodayHabitChip(habit: habit) {
                                Task { await vm.toggleHabit(habit) }
                            }
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    private var tasksSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Priorität", systemImage: "arrow.up.circle.fill").font(.headline)
                Spacer()
                Text("\(vm.todayTasks.count) offen").font(.caption).foregroundStyle(.secondary)
            }
            .padding(.horizontal)

            if vm.todayTasks.isEmpty {
                HStack {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                    Text("Alles erledigt!").font(.subheadline).foregroundStyle(.secondary)
                }
                .padding(.horizontal)
            } else {
                ForEach(vm.todayTasks) { task in
                    TodayTaskRow(task: task) {
                        Task { await vm.completeTask(task) }
                    }
                }
            }
        }
    }

    private var offlineBanner: some View {
        HStack {
            Image(systemName: "wifi.slash")
            Text("Offline — zeige gecachte Daten")
        }
        .font(.caption).padding(8)
        .frame(maxWidth: .infinity)
        .background(Color.orange.opacity(0.12))
        .foregroundStyle(.orange)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.horizontal)
    }

    private var dayGreeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<12: return "Guten Morgen"
        case 12..<17: return "Guten Mittag"
        case 17..<22: return "Guten Abend"
        default: return "Gute Nacht"
        }
    }

    private var formattedDate: String {
        let f = DateFormatter(); f.dateStyle = .full; f.locale = Locale(identifier: "de_DE")
        return f.string(from: Date())
    }
}

struct EventChip: View {
    let event: CalendarEvent
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(formatTime(event.displayStart)).font(.caption2.bold()).foregroundStyle(.blue)
            Text(event.title).font(.caption.bold()).lineLimit(1)
            if let loc = event.location { Text(loc).font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
        }
        .padding(10)
        .background(Color.blue.opacity(0.08))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.blue.opacity(0.2), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .frame(minWidth: 100)
    }

    private func formatTime(_ iso: String) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let d = f.date(from: iso) else { return String(iso.suffix(5)) }
        let df = DateFormatter(); df.timeStyle = .short; df.dateStyle = .none
        return df.string(from: d)
    }
}

struct TodayHabitChip: View {
    let habit: Habit
    let onTap: () -> Void
    private var done: Bool { habit.completedToday ?? false }
    private var accent: Color { habitAccentColor(habit.color) }

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 6) {
                ZStack {
                    Circle().fill(done ? accent : accent.opacity(0.12)).frame(width: 44, height: 44)
                    Image(systemName: habit.icon ?? "star")
                        .font(.title3).foregroundStyle(done ? .white : accent)
                }
                Text(habit.name).font(.caption).lineLimit(1).frame(maxWidth: 60)
                if done { Image(systemName: "checkmark").font(.caption2).foregroundStyle(.green) }
            }
            .padding(8)
            .background(done ? accent.opacity(0.08) : Color(.secondarySystemBackground))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(done ? accent : Color.clear, lineWidth: 1.5))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
    }
}

struct TodayTaskRow: View {
    let task: AlfredTask
    let onComplete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onComplete) {
                Image(systemName: "circle").font(.title3).foregroundStyle(priorityColor(task.priority ?? "medium"))
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(task.title).font(.subheadline)
                if let due = task.due {
                    Text(formatDue(due)).font(.caption).foregroundStyle(isDueOverdue(due) ? .red : .secondary)
                }
            }
            Spacer()
            priorityBadge(task.priority ?? "medium")
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }

    private func priorityColor(_ p: String) -> Color {
        switch p { case "urgent": return .red; case "high": return .orange; case "medium": return .blue; default: return .gray }
    }

    private func priorityBadge(_ p: String) -> some View {
        if p == "low" || p == "medium" { return AnyView(EmptyView()) }
        return AnyView(
            Text(p.uppercased()).font(.system(size: 9, weight: .bold))
                .padding(.horizontal, 5).padding(.vertical, 2)
                .background(priorityColor(p).opacity(0.12))
                .foregroundStyle(priorityColor(p))
                .clipShape(Capsule())
        )
    }

    private func formatDue(_ iso: String) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        guard let d = f.date(from: iso) else { return iso }
        let df = DateFormatter(); df.dateStyle = .short; df.locale = Locale(identifier: "de_DE")
        return "Fällig \(df.string(from: d))"
    }

    private func isDueOverdue(_ iso: String) -> Bool {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        guard let d = f.date(from: iso) else { return false }
        return d < Calendar.current.startOfDay(for: Date())
    }
}

func habitAccentColor(_ color: String?) -> Color {
    switch color {
    case "purple": return .purple
    case "blue": return .blue
    case "green": return .green
    case "orange": return .orange
    case "red": return .red
    case "pink": return .pink
    default: return .indigo
    }
}
