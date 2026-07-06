import Foundation

final class BrainAPI {
    static let shared = BrainAPI()
    private let c = MantisClient.shared

    func fetchNotes(category: String? = nil, limit: Int = 200) async throws -> [BrainNote] {
        var path = "/api/brain/notes?limit=\(limit)"
        if let cat = category, !cat.isEmpty { path += "&category=\(cat)" }
        return try await c.get(path)
    }

    func fetchNote(_ id: Int) async throws -> BrainNote {
        try await c.get("/api/brain/notes/\(id)")
    }

    func createNote(_ req: CreateNoteRequest) async throws -> BrainNote {
        let resp: OkResponse = try await c.post("/api/brain/notes", body: req)
        guard let id = resp.id else { throw MantisError.invalidURL }
        return try await fetchNote(id)
    }

    func updateNote(_ id: Int, _ req: UpdateNoteRequest) async throws -> BrainNote {
        let _: OkResponse = try await c.put("/api/brain/notes/\(id)", body: req)
        return try await fetchNote(id)
    }

    func deleteNote(_ id: Int) async throws {
        try await c.delete("/api/brain/notes/\(id)")
    }

    func fetchGraph() async throws -> GraphData {
        try await c.get("/api/brain/graph")
    }

    func fetchBacklinks(_ id: Int) async throws -> [BacklinkItem] {
        try await c.get("/api/brain/backlinks/\(id)")
    }

    func search(_ query: String) async throws -> [BrainNote] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        return try await c.get("/api/brain/search?q=\(encoded)")
    }

    func fetchDailyNote() async throws -> BrainNote {
        try await c.get("/api/brain/daily")
    }
}
