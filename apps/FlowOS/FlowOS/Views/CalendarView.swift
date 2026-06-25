import SwiftUI

@MainActor
final class CalendarViewModel: ObservableObject {
    @Published var selectedDate: Date = Date()
    @Published var events: [CalendarEvent] = []
    @Published var isLoading = false
    @Published var error: String?

    var eventsForSelected: [CalendarEvent] {
        let dayStr = isoDate(selectedDate)
        return events.filter { $0.displayStart.hasPrefix(dayStr) }.sorted { $0.displayStart < $1.displayStart }
    }

    func load() async {
        isLoading = true; error = nil
        do {
            events = try await FlowAPI.shared.fetchEvents(days: 90)
            OfflineCache.shared.save(events, key: "cache_events")
        } catch {
            self.error = error.localizedDescription
            events = OfflineCache.shared.load([CalendarEvent].self, key: "cache_events") ?? []
        }
        isLoading = false
    }

    func deleteEvent(_ event: CalendarEvent) async {
        guard let uid = event.uid else { return }
        try? await FlowAPI.shared.deleteEvent(uid: uid)
        await load()
    }

    func isoDate(_ date: Date) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withFullDate]
        return f.string(from: date)
    }
}

struct CalendarView: View {
    @StateObject private var vm = CalendarViewModel()
    @State private var showCreateEvent = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                monthHeader
                monthGrid
                    .padding(.bottom, 8)
                Divider()
                selectedDayEvents
            }
            .navigationTitle(monthTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { showCreateEvent = true } label: { Image(systemName: "plus") }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Heute") { vm.selectedDate = Date() }
                }
            }
            .sheet(isPresented: $showCreateEvent, onDismiss: { Task { await vm.load() } }) {
                EventEditorView(date: vm.selectedDate)
            }
            .task { await vm.load() }
            .onChange(of: vm.selectedDate) { _, _ in Task { await vm.load() } }
            .alert("Fehler", isPresented: .init(get: { vm.error != nil }, set: { _ in vm.error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(vm.error ?? "") }
        }
    }

    private var monthHeader: some View {
        HStack {
            Button { changeMonth(by: -1) } label: { Image(systemName: "chevron.left") }
            Spacer()
            Text(monthTitle).font(.headline)
            Spacer()
            Button { changeMonth(by: 1) } label: { Image(systemName: "chevron.right") }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    private var monthGrid: some View {
        let cal = Calendar.current
        let comps = cal.dateComponents([.year, .month], from: vm.selectedDate)
        let startOfMonth = cal.date(from: comps)!
        let range = cal.range(of: .day, in: .month, for: startOfMonth)!
        let firstWeekday = (cal.component(.weekday, from: startOfMonth) + 5) % 7
        let days: [Date?] = Array(repeating: nil, count: firstWeekday) + range.compactMap { day -> Date? in
            var dc = comps; dc.day = day; return cal.date(from: dc)
        }
        let weeks = days.chunked(into: 7)

        return VStack(spacing: 4) {
            HStack {
                ForEach(["Mo","Di","Mi","Do","Fr","Sa","So"], id: \.self) { d in
                    Text(d).font(.caption2.weight(.medium)).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal)

            ForEach(weeks.indices, id: \.self) { wi in
                HStack(spacing: 0) {
                    ForEach(weeks[wi].indices, id: \.self) { di in
                        if let date = weeks[wi][di] { dayCell(date: date) }
                        else { Color.clear.frame(maxWidth: .infinity, minHeight: 40) }
                    }
                }
            }
            .padding(.horizontal)
        }
    }

    private func dayCell(date: Date) -> some View {
        let cal = Calendar.current
        let isToday = cal.isDateInToday(date)
        let isSelected = cal.isDate(date, inSameDayAs: vm.selectedDate)
        let day = cal.component(.day, from: date)
        let dayStr = vm.isoDate(date)
        let hasEvent = vm.events.contains { $0.displayStart.hasPrefix(dayStr) }

        return Button { vm.selectedDate = date } label: {
            VStack(spacing: 3) {
                Text("\(day)")
                    .font(.subheadline.weight(isToday ? .bold : .regular))
                    .frame(width: 34, height: 34)
                    .background(isSelected ? Color.indigo : (isToday ? Color.indigo.opacity(0.12) : Color.clear))
                    .foregroundStyle(isSelected ? .white : .primary)
                    .clipShape(Circle())
                Circle().fill(hasEvent ? Color.indigo : Color.clear).frame(width: 5, height: 5)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var selectedDayEvents: some View {
        let events = vm.eventsForSelected
        let title = formatSelectedDate(vm.selectedDate)
        return ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.subheadline.bold()).foregroundStyle(.secondary).padding(.horizontal).padding(.top, 8)
                if events.isEmpty {
                    HStack {
                        Spacer()
                        VStack(spacing: 8) {
                            Image(systemName: "calendar").font(.largeTitle).foregroundStyle(.tertiary)
                            Text("Keine Termine").foregroundStyle(.secondary)
                        }
                        .padding(24)
                        Spacer()
                    }
                } else {
                    ForEach(events) { event in
                        EventDetailRow(event: event) { Task { await vm.deleteEvent(event) } }
                            .padding(.horizontal)
                    }
                }
            }
        }
    }

    private var monthTitle: String {
        let f = DateFormatter(); f.dateFormat = "MMMM yyyy"; f.locale = Locale(identifier: "de_DE")
        return f.string(from: vm.selectedDate)
    }

    private func formatSelectedDate(_ date: Date) -> String {
        let f = DateFormatter(); f.dateStyle = .full; f.locale = Locale(identifier: "de_DE")
        return f.string(from: date)
    }

    private func changeMonth(by delta: Int) {
        vm.selectedDate = Calendar.current.date(byAdding: .month, value: delta, to: vm.selectedDate) ?? vm.selectedDate
    }
}

struct EventDetailRow: View {
    let event: CalendarEvent
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 3).fill(Color.indigo).frame(width: 4)
            VStack(alignment: .leading, spacing: 3) {
                Text(event.title).font(.subheadline.bold())
                if let desc = event.description, !desc.isEmpty {
                    Text(desc).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                HStack(spacing: 8) {
                    if !(event.allDay ?? false) {
                        Text(formatTime(event.displayStart)).font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Ganztägig").font(.caption).foregroundStyle(.secondary)
                    }
                    if let loc = event.location, !loc.isEmpty {
                        Label(loc, systemImage: "mappin").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
            Spacer()
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onDelete) { Label("Löschen", systemImage: "trash") }
        }
    }

    private func formatTime(_ iso: String) -> String {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let f2 = ISO8601DateFormatter(); f2.formatOptions = [.withInternetDateTime]
        guard let d = f.date(from: iso) ?? f2.date(from: iso) else { return String(iso.suffix(5)) }
        let df = DateFormatter(); df.timeStyle = .short; df.dateStyle = .none
        return df.string(from: d)
    }
}

struct EventEditorView: View {
    let date: Date
    @State private var title = ""
    @State private var desc = ""
    @State private var startTime: Date
    @State private var endTime: Date
    @State private var allDay = false
    @State private var location = ""
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    init(date: Date) {
        self.date = date
        let cal = Calendar.current
        let noon = cal.date(bySettingHour: 10, minute: 0, second: 0, of: date) ?? date
        _startTime = State(initialValue: noon)
        _endTime = State(initialValue: noon.addingTimeInterval(3600))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Termin") {
                    TextField("Titel", text: $title)
                    TextField("Beschreibung", text: $desc, axis: .vertical).lineLimit(2...4)
                    TextField("Ort", text: $location)
                }
                Section("Zeit") {
                    Toggle("Ganztägig", isOn: $allDay)
                    if !allDay {
                        DatePicker("Beginn", selection: $startTime)
                        DatePicker("Ende", selection: $endTime)
                    } else {
                        DatePicker("Datum", selection: $startTime, displayedComponents: .date)
                    }
                }
            }
            .navigationTitle("Neuer Termin")
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
        let f = ISO8601DateFormatter()
        let req = CreateEventRequest(
            title: title, description: desc.isEmpty ? nil : desc,
            start: f.string(from: startTime), end: allDay ? nil : f.string(from: endTime),
            allDay: allDay, color: nil, location: location.isEmpty ? nil : location
        )
        do { try await FlowAPI.shared.createEvent(req); dismiss() }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }
}

