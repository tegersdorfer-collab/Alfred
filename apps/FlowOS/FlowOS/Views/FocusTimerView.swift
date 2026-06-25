import SwiftUI

enum FocusPhase: String, CaseIterable {
    case focusing = "Fokus"
    case shortBreak = "Kurze Pause"
    case longBreak = "Lange Pause"

    var duration: Int {
        switch self {
        case .focusing: return 25 * 60
        case .shortBreak: return 5 * 60
        case .longBreak: return 15 * 60
        }
    }

    var color: Color {
        switch self {
        case .focusing: return .indigo
        case .shortBreak: return .green
        case .longBreak: return .teal
        }
    }

    var icon: String {
        switch self {
        case .focusing: return "brain.head.profile"
        case .shortBreak: return "cup.and.saucer.fill"
        case .longBreak: return "figure.walk"
        }
    }
}

@MainActor
final class FocusTimerViewModel: ObservableObject {
    @Published var phase: FocusPhase = .focusing
    @Published var secondsRemaining: Int = 25 * 60
    @Published var isRunning = false
    @Published var sessionsCompleted: Int = 0
    @Published var tasks: [AlfredTask] = []
    @Published var selectedTask: AlfredTask?
    @Published var showTaskPicker = false

    private var timerTask: Task<Void, Never>?

    var progress: Double {
        let total = Double(phase.duration)
        let elapsed = total - Double(secondsRemaining)
        return max(0, min(1, elapsed / total))
    }

    var timeString: String {
        let m = secondsRemaining / 60
        let s = secondsRemaining % 60
        return String(format: "%02d:%02d", m, s)
    }

    var sessionDots: [Bool] {
        (0..<4).map { $0 < sessionsCompleted % 4 }
    }

    func start() {
        guard !isRunning else { return }
        isRunning = true
        timerTask = Task {
            while secondsRemaining > 0 && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if isRunning { secondsRemaining -= 1 }
                if secondsRemaining == 0 { onPhaseComplete() }
            }
        }
    }

    func pause() {
        isRunning = false
        timerTask?.cancel()
        timerTask = nil
    }

    func reset() {
        pause()
        secondsRemaining = phase.duration
    }

    func skip() {
        pause()
        onPhaseComplete()
    }

    func switchPhase(_ newPhase: FocusPhase) {
        pause()
        phase = newPhase
        secondsRemaining = newPhase.duration
    }

    func loadTasks() async {
        tasks = (try? await FlowAPI.shared.fetchTasks())?.filter { $0.status == "todo" || $0.status == "in_progress" } ?? []
    }

    private func onPhaseComplete() {
        isRunning = false
        timerTask = nil
        if phase == .focusing {
            sessionsCompleted += 1
            let nextPhase: FocusPhase = sessionsCompleted % 4 == 0 ? .longBreak : .shortBreak
            phase = nextPhase
        } else {
            phase = .focusing
        }
        secondsRemaining = phase.duration
    }
}

struct FocusTimerView: View {
    @StateObject private var vm = FocusTimerViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                phasePicker
                    .padding(.top, 8)

                Spacer()

                timerSection

                Spacer()

                sessionDots
                    .padding(.bottom, 24)

                if let task = vm.selectedTask {
                    activeTaskBadge(task)
                        .padding(.bottom, 12)
                }

                controls
                    .padding(.bottom, 32)
            }
            .frame(maxWidth: .infinity)
            .background(vm.phase.color.opacity(0.06))
            .navigationTitle("Fokus")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fertig") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        vm.showTaskPicker = true
                        Task { await vm.loadTasks() }
                    } label: {
                        Image(systemName: "list.bullet.clipboard")
                    }
                }
            }
            .sheet(isPresented: $vm.showTaskPicker) {
                taskPickerSheet
            }
        }
    }

    private var phasePicker: some View {
        HStack(spacing: 8) {
            ForEach(FocusPhase.allCases, id: \.self) { p in
                Button {
                    vm.switchPhase(p)
                } label: {
                    Text(p.rawValue)
                        .font(.caption.bold())
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(vm.phase == p ? p.color : Color(.tertiarySystemBackground))
                        .foregroundStyle(vm.phase == p ? .white : .secondary)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal)
    }

    private var timerSection: some View {
        ZStack {
            Circle()
                .stroke(vm.phase.color.opacity(0.12), lineWidth: 14)
                .frame(width: 240, height: 240)

            Circle()
                .trim(from: 0, to: vm.progress)
                .stroke(vm.phase.color, style: StrokeStyle(lineWidth: 14, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.linear(duration: 1), value: vm.progress)
                .frame(width: 240, height: 240)

            VStack(spacing: 8) {
                Image(systemName: vm.phase.icon)
                    .font(.title2)
                    .foregroundStyle(vm.phase.color)

                Text(vm.timeString)
                    .font(.system(size: 52, weight: .thin, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.primary)

                Text(vm.phase.rawValue.uppercased())
                    .font(.caption.bold())
                    .tracking(2)
                    .foregroundStyle(vm.phase.color)
            }
        }
    }

    private var sessionDots: some View {
        HStack(spacing: 10) {
            ForEach(0..<4, id: \.self) { i in
                Circle()
                    .fill(i < vm.sessionsCompleted % 4 ? vm.phase.color : vm.phase.color.opacity(0.2))
                    .frame(width: 8, height: 8)
                    .animation(.spring(), value: vm.sessionsCompleted)
            }
        }
    }

    private func activeTaskBadge(_ task: AlfredTask) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "target").font(.caption).foregroundStyle(.indigo)
            Text(task.title).font(.caption.bold()).lineLimit(1)
            Spacer()
            Button { vm.selectedTask = nil } label: {
                Image(systemName: "xmark").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal, 24)
    }

    private var controls: some View {
        HStack(spacing: 24) {
            Button { vm.reset() } label: {
                Image(systemName: "arrow.counterclockwise")
                    .font(.title3)
                    .frame(width: 52, height: 52)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(Circle())
            }
            .foregroundStyle(.secondary)

            Button {
                if vm.isRunning { vm.pause() } else { vm.start() }
            } label: {
                Image(systemName: vm.isRunning ? "pause.fill" : "play.fill")
                    .font(.title)
                    .frame(width: 72, height: 72)
                    .background(vm.phase.color)
                    .foregroundStyle(.white)
                    .clipShape(Circle())
                    .shadow(color: vm.phase.color.opacity(0.4), radius: 12, y: 4)
            }

            Button { vm.skip() } label: {
                Image(systemName: "forward.end.fill")
                    .font(.title3)
                    .frame(width: 52, height: 52)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(Circle())
            }
            .foregroundStyle(.secondary)
        }
    }

    private var taskPickerSheet: some View {
        NavigationStack {
            List(vm.tasks) { task in
                Button {
                    vm.selectedTask = task
                    vm.showTaskPicker = false
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(task.title).font(.subheadline).foregroundStyle(.primary)
                            if let due = task.due {
                                Text(due).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if vm.selectedTask?.id == task.id {
                            Image(systemName: "checkmark").foregroundStyle(.indigo)
                        }
                    }
                }
                .listRowBackground(Color.clear)
            }
            .listStyle(.plain)
            .navigationTitle("Aufgabe wählen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { vm.showTaskPicker = false }
                }
            }
        }
        .presentationDetents([.medium])
    }
}
