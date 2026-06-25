import Foundation

// MARK: - Tasks

struct AlfredTask: Codable, Identifiable {
    let id: Int
    let title: String
    let notes: String?
    let status: String
    let priority: String?
    let due: String?
    let kind: String?
    let createdAt: String?
    let completedAt: String?

    var description: String? { notes }
    var dueDate: String? { due }
    var project: String? { nil }
    var tags: [String]? { nil }
}

struct CreateTaskRequest: Encodable {
    let title: String
    let notes: String?
    let status: String
    let priority: String
    let due: String?
    let project: String?
    let tags: [String]
}

struct UpdateTaskRequest: Encodable {
    let title: String
    let notes: String?
    let status: String
    let priority: String
    let due: String?
    let project: String?
    let tags: [String]
}

// MARK: - Calendar

struct CalendarEvent: Codable, Identifiable {
    let uid: String?
    let title: String
    let description: String?
    let startIso: String?
    let startTime: String?
    let endTime: String?
    let allDay: Bool?
    let color: String?
    let location: String?
    let calendar: String?

    var id: String { uid ?? title }
    var displayStart: String { startIso ?? startTime ?? "" }
}

struct CreateEventRequest: Encodable {
    let title: String
    let description: String?
    let start: String
    let end: String?
    let allDay: Bool
    let color: String?
    let location: String?
}

// MARK: - Habits

struct Habit: Codable, Identifiable {
    let id: Int
    let name: String
    let description: String?
    let frequency: String
    let targetDays: [Int]?
    let color: String?
    let icon: String?
    let streak: Int?
    let completedToday: Bool?
    let createdAt: String?
}

struct HabitStats: Decodable {
    let habitId: Int
    let streak: Int
    let completionRate: Double
    let totalCompletions: Int
    let logs: [HabitLog]
}

struct HabitLog: Codable, Identifiable {
    let id: Int
    let habitId: Int
    let date: String
    let completed: Bool
    let note: String?
}

struct CreateHabitRequest: Encodable {
    let name: String
    let description: String?
    let frequency: String
    let color: String?
    let icon: String?
}

struct LogHabitRequest: Encodable {
    let date: String
    let completed: Bool
    let note: String?
}

// MARK: - Shared

struct OkResponse: Decodable {
    let ok: Bool?
    let id: Int?
}

let taskStatuses = ["todo", "in_progress", "done", "cancelled"]
let taskPriorities = ["low", "medium", "high", "urgent"]
let habitFrequencies = ["daily", "weekdays", "weekly", "custom"]
let habitColors = ["indigo", "purple", "blue", "green", "orange", "red", "pink"]
let habitIcons = ["star", "bolt", "heart", "brain", "figure.run", "book", "drop", "moon", "sun.max", "flame", "pencil", "music.note"]

// MARK: - Offline Cache

final class OfflineCache {
    static let shared = OfflineCache()
    private let defaults = UserDefaults.standard
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    func save<T: Encodable>(_ value: T, key: String) {
        if let data = try? encoder.encode(value) { defaults.set(data, forKey: key) }
    }

    func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? decoder.decode(T.self, from: data)
    }
}

extension Array {
    func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map { Array(self[$0..<Swift.min($0+size, count)]) }
    }
}
