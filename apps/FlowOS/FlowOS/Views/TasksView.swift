import SwiftUI

@MainActor
final class TasksViewModel: ObservableObject {
    @Published var tasks: [AlfredTask] = []
    @Published var filterStatus = "active"
    @Published var isLoading = false
    @Published var error: String?
    @Published var selectedTask: AlfredTask?

    var filtered: [AlfredTask] {
        switch filterStatus {
        case "active": return tasks.filter { $0.status == "todo" || $0.status == "in_progress" }
        case "done": return tasks.filter { $0.status == "done" }
        default: return tasks
        }
    }

    var grouped: [(String, [AlfredTask])] {
        Dictionary(grouping: filtered) { $0.project ?? "Ohne Projekt" }
            .sorted { $0.key < $1.key }
    }

    func load() async {
        isLoading = true; error = nil
        do {
            tasks = try await FlowAPI.shared.fetchTasks()
            OfflineCache.shared.save(tasks, key: "cache_tasks")
        } catch {
            self.error = error.localizedDescription
            tasks = OfflineCache.shared.load([AlfredTask].self, key: "cache_tasks") ?? []
        }
        isLoading = false
    }

    func complete(_ task: AlfredTask) async {
        try? await FlowAPI.shared.completeTask(task.id); await load()
    }

    func delete(_ task: AlfredTask) async {
        try? await FlowAPI.shared.deleteTask(task.id); await load()
    }
}

struct TasksView: View {
    @StateObject private var vm = TasksViewModel()
    @State private var showCreate = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Filter", selection: $vm.filterStatus) {
                    Text("Aktiv").tag("active")
                    Text("Alle").tag("all")
                    Text("Erledigt").tag("done")
                }
                .pickerStyle(.segmented).padding()

                if vm.isLoading {
                    Spacer(); ProgressView(); Spacer()
                } else if vm.filtered.isEmpty {
                    Spacer()
                    ContentUnavailableView("Keine Aufgaben", systemImage: "checklist",
                                          description: vm.filterStatus == "done" ? Text("Noch nichts erledigt") : Text("Alle Aufgaben erledigt! 🎉"))
                    Spacer()
                } else {
                    List {
                        ForEach(vm.grouped, id: \.0) { project, tasks in
                            Section(project) {
                                ForEach(tasks) { task in
                                    TaskRowView(task: task, onComplete: { Task { await vm.complete(task) } })
                                        .listRowBackground(Color.clear)
                                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                                        .onTapGesture { vm.selectedTask = task }
                                        .swipeActions(edge: .trailing) {
                                            Button(role: .destructive) { Task { await vm.delete(task) } } label: {
                                                Label("Löschen", systemImage: "trash")
                                            }
                                            Button { Task { await vm.complete(task) } } label: {
                                                Label("Erledigt", systemImage: "checkmark")
                                            }.tint(.green)
                                        }
                                }
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Aufgaben")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $showCreate, onDismiss: { Task { await vm.load() } }) {
                TaskEditorView(task: nil)
            }
            .sheet(item: $vm.selectedTask, onDismiss: { Task { await vm.load() } }) { task in
                TaskEditorView(task: task)
            }
            .task { await vm.load() }
            .refreshable { await vm.load() }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
        }
    }
}

struct TaskRowView: View {
    let task: AlfredTask
    let onComplete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onComplete) {
                Image(systemName: task.status == "done" ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(task.status == "done" ? .green : priorityColor(task.priority ?? "medium"))
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                Text(task.title)
                    .font(.subheadline)
                    .strikethrough(task.status == "done")
                    .foregroundStyle(task.status == "done" ? .secondary : .primary)
                HStack(spacing: 8) {
                    if let notes = task.notes, !notes.isEmpty {
                        Text(notes).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    if let due = task.due {
                        Text(formatDue(due))
                            .font(.caption)
                            .foregroundStyle(isDueOverdue(due) && task.status != "done" ? .red : .secondary)
                    }
                }
            }
            Spacer()
            priorityIndicator(task.priority ?? "medium")
        }
        .padding(.vertical, 4)
    }

    private func priorityColor(_ p: String) -> Color {
        switch p { case "urgent": return .red; case "high": return .orange; case "medium": return .indigo; default: return .gray }
    }

    private func priorityIndicator(_ p: String) -> some View {
        let color = priorityColor(p)
        let show = p == "urgent" || p == "high"
        return Group {
            if show {
                Circle().fill(color).frame(width: 8, height: 8)
            } else { EmptyView() }
        }
    }

    private func formatDue(_ iso: String) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        guard let d = f.date(from: iso) else { return iso }
        let df = DateFormatter(); df.dateStyle = .short; df.locale = Locale(identifier: "de_DE")
        return df.string(from: d)
    }

    private func isDueOverdue(_ iso: String) -> Bool {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        guard let d = f.date(from: iso) else { return false }
        return d < Calendar.current.startOfDay(for: Date())
    }
}

struct TaskEditorView: View {
    let task: AlfredTask?
    @State private var title: String
    @State private var notes: String
    @State private var status: String
    @State private var priority: String
    @State private var project: String
    @State private var tags: String
    @State private var hasDueDate: Bool
    @State private var dueDate: Date
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    init(task: AlfredTask?) {
        self.task = task
        _title = State(initialValue: task?.title ?? "")
        _notes = State(initialValue: task?.notes ?? "")
        _status = State(initialValue: task?.status ?? "todo")
        _priority = State(initialValue: task?.priority ?? "medium")
        _project = State(initialValue: task?.project ?? "")
        _tags = State(initialValue: task?.tags?.joined(separator: ", ") ?? "")
        if let d = task?.due, let date = ISO8601DateFormatter().date(from: d) {
            _hasDueDate = State(initialValue: true); _dueDate = State(initialValue: date)
        } else {
            _hasDueDate = State(initialValue: false); _dueDate = State(initialValue: Date())
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Aufgabe") {
                    TextField("Titel", text: $title)
                    TextField("Notiz (optional)", text: $notes, axis: .vertical).lineLimit(3...6)
                }
                Section("Einstellungen") {
                    Picker("Status", selection: $status) {
                        ForEach(taskStatuses, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ").capitalized).tag($0) }
                    }
                    Picker("Priorität", selection: $priority) {
                        ForEach(taskPriorities, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                }
                Section("Organisation") {
                    TextField("Projekt", text: $project)
                    TextField("Tags (kommagetrennt)", text: $tags)
                }
                Section("Fälligkeitsdatum") {
                    Toggle("Datum setzen", isOn: $hasDueDate)
                    if hasDueDate {
                        DatePicker("Datum", selection: $dueDate, displayedComponents: .date)
                    }
                }
            }
            .navigationTitle(task == nil ? "Neue Aufgabe" : "Bearbeiten")
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
        guard !title.isEmpty else { error = "Titel fehlt"; return }
        isSaving = true
        let tagList = tags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        let dueDateStr: String? = hasDueDate ? ISO8601DateFormatter().string(from: dueDate) : nil
        do {
            if let id = task?.id {
                let req = UpdateTaskRequest(title: title, notes: notes.isEmpty ? nil : notes, status: status,
                                           priority: priority, due: dueDateStr, project: project.isEmpty ? nil : project, tags: tagList)
                struct StatusPatch: Encodable { let status: String }
                let _: OkResponse = try await AlfredClient.shared.post("/api/tasks/\(id)/status", body: StatusPatch(status: req.status))
            } else {
                let req = CreateTaskRequest(title: title, notes: notes.isEmpty ? nil : notes, status: status,
                                           priority: priority, due: dueDateStr, project: project.isEmpty ? nil : project, tags: tagList)
                let _: OkResponse = try await AlfredClient.shared.post("/api/tasks", body: req)
            }
            dismiss()
        } catch { self.error = error.localizedDescription }
        isSaving = false
    }
}
