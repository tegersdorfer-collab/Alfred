import Foundation

final class NutritionAPI {
    static let shared = NutritionAPI()
    private let client = AlfredClient.shared

    func analyzePhoto(imageData: Data, annotation: String?) async throws -> MacroEstimate {
        let data = try await client.postMultipart("/api/nutrition/analyze-photo", imageData: imageData, text: annotation)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        if let resp = try? decoder.decode(AnalyzePhotoResponse.self, from: data), let result = resp.result {
            return result
        }
        return try decoder.decode(MacroEstimate.self, from: data)
    }

    func logMeal(_ request: LogMealRequest) async throws {
        let _: OkResponse = try await client.post("/api/nutrition/log-meal", body: request)
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
