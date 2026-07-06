import Foundation

final class NutritionAPI {
    static let shared = NutritionAPI()
    private let client = MantisClient.shared

    func analyzePhoto(imageData: Data, annotation: String?) async throws {
        _ = try await client.postMultipart("/api/nutrition/analyze-photo", imageData: imageData, text: annotation)
    }

    func logMeal(_ request: LogMealRequest) async throws {
        let _: OkResponse = try await client.post("/api/nutrition/log-meal", body: request)
    }

    func updateMeal(_ id: Int, _ req: UpdateMealRequest) async throws {
        let _: OkResponse = try await client.put("/api/nutrition/\(id)", body: req)
    }

    func todayNutrition() async throws -> TodayNutritionResponse {
        try await client.get("/api/nutrition")
    }

    func nutritionHistory(days: Int = 14) async throws -> [[String: Double]] {
        try await client.get("/api/nutrition/history?days=\(days)")
    }

    func nutritionGoals() async throws -> NutritionGoals {
        try await client.get("/api/nutrition/goals")
    }
}
