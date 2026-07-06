import Foundation

final class FitnessAPI {
    static let shared = FitnessAPI()
    private let client = MantisClient.shared

    func fetchTodayPlan() async throws -> TodayPlan {
        try await client.get("/api/fitness/today-plan")
    }

    func fetchHistory(limit: Int = 60) async throws -> [WorkoutHistoryItem] {
        try await client.get("/api/workouts?limit=\(limit)")
    }

    func fetchExercises() async throws -> [ExerciseItem] {
        try await client.get("/api/fitness/exercises")
    }

    func logWorkout(_ request: LogWorkoutRequest) async throws -> LogWorkoutResponse {
        try await client.post("/api/workouts", body: request)
    }

    func logRPE(_ request: LogRPERequest) async throws {
        let _: OkResponse = try await client.post("/api/fitness/log-rpe", body: request)
    }

    func markJogDone(distanceKm: Double? = nil, durationMin: Int? = nil,
                     source: String = "manual") async throws {
        struct Body: Encodable { let distanceKm: Double?; let durationMin: Int?; let source: String }
        let _: OkResponse = try await client.post(
            "/api/fitness/jog-done",
            body: Body(distanceKm: distanceKm, durationMin: durationMin, source: source))
    }

    func markRestDay() async throws {
        struct Empty: Encodable {}
        let _: OkResponse = try await client.post("/api/fitness/rest-day", body: Empty())
    }

    func fetchProfile() async throws -> TrainingProfile {
        try await client.get("/api/fitness/profile")
    }

    func saveProfile(_ p: TrainingProfile) async throws -> TrainingProfile {
        try await client.put("/api/fitness/profile", body: p)
    }

    @discardableResult
    func generatePlan() async throws -> OkResponse {
        try await client.post("/api/fitness/plan/generate", body: EmptyReqBody())
    }

    func fetchWorkout(_ id: Int) async throws -> WorkoutDetail {
        try await client.get("/api/workouts/\(id)")
    }

    func updateWorkout(_ id: Int, body: UpdateWorkoutRequest) async throws {
        let _: OkResponse = try await client.put("/api/workouts/\(id)", body: body)
    }

    func deleteWorkout(_ id: Int) async throws {
        try await client.delete("/api/workouts/\(id)")
    }

    func lastSets(exercise: String) async throws -> [LastSet] {
        let enc = exercise.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? exercise
        return try await client.get("/api/fitness/last-sets?exercise=\(enc)")
    }
}

private struct EmptyReqBody: Encodable {}
