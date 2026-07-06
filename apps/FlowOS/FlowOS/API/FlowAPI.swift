import Foundation

final class FlowAPI {
    static let shared = FlowAPI()
    private let c = MantisClient.shared

    // MARK: - Tasks

    func fetchTasks(status: String? = nil) async throws -> [MantisTask] {
        var path = "/api/tasks"
        if let s = status { path += "?status=\(s == "active" ? "open" : s)" }
        return try await c.get(path)
    }

    func createTask(_ req: CreateTaskRequest) async throws -> MantisTask {
        let resp: OkResponse = try await c.post("/api/tasks", body: req)
        guard let id = resp.id else { throw MantisError.invalidURL }
        let tasks: [MantisTask] = try await c.get("/api/tasks")
        return tasks.first { $0.id == id } ??
            MantisTask(id: id, title: req.title, notes: req.notes, status: req.status,
                       priority: req.priority, due: req.due, kind: nil, createdAt: nil, completedAt: nil)
    }

    func completeTask(_ id: Int) async throws {
        let _: OkResponse = try await c.post("/api/tasks/\(id)/complete", body: EmptyBody())
    }

    func deleteTask(_ id: Int) async throws {
        try await c.delete("/api/tasks/\(id)")
    }

    func updateTaskStatus(_ id: Int, status: String) async throws {
        struct Patch: Encodable { let status: String }
        let _: OkResponse = try await c.post("/api/tasks/\(id)/status", body: Patch(status: status))
    }

    // MARK: - Calendar

    func fetchEvents(days: Int = 60) async throws -> [CalendarEvent] {
        try await c.get("/api/calendar?days=\(days)")
    }

    func createEvent(_ req: CreateEventRequest) async throws {
        let _: OkResponse = try await c.post("/api/calendar", body: req)
    }

    func deleteEvent(uid: String) async throws {
        try await c.delete("/api/calendar/\(uid)")
    }

    // MARK: - Habits

    func fetchHabits(days: Int = 30) async throws -> [Habit] {
        try await c.get("/api/habits?days=\(days)")
    }

    func createHabit(_ req: CreateHabitRequest) async throws {
        let _: OkResponse = try await c.post("/api/habits", body: req)
    }

    func logHabit(_ id: Int, _ req: LogHabitRequest) async throws {
        let _: OkResponse = try await c.post("/api/habits/\(id)/log", body: req)
    }

    func unlogHabit(_ id: Int) async throws {
        let _: OkResponse = try await c.post("/api/habits/\(id)/unlog", body: EmptyBody())
    }

    func deleteHabit(_ id: Int) async throws {
        try await c.delete("/api/habits/\(id)")
    }

    func commitHistory(days: Int = 90) async throws -> [[String: Int]] {
        try await c.get("/api/habits/commit?days=\(days)")
    }
}

private struct EmptyBody: Encodable {}
