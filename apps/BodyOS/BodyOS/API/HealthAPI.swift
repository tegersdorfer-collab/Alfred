import Foundation

final class HealthAPI {
    static let shared = HealthAPI()
    private let client = MantisClient.shared

    func fetchHistory(days: Int = 30) async throws -> [HealthEntry] {
        try await client.get("/api/health?days=\(days)")
    }

    func pushHealthData(_ payload: HealthPushPayload) async throws {
        let _: OkResponse = try await client.post("/api/health/push", body: payload)
    }

    func manualEntry(_ payload: HealthPushPayload) async throws {
        let _: OkResponse = try await client.post("/api/health/manual", body: payload)
    }
}
