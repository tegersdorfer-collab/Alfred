import Foundation
import SwiftData

// MARK: - Fitness Models

struct TodayPlan: Codable {
    let dayType: String
    let dayLabel: String
    let intensityFactor: Double
    let alfredMessage: String
    let health: HealthSnapshot?
    let exercises: [PlannedExercise]
    let doneToday: Bool?
    let nextLabel: String?
    let planWeek: Int?
    let planSource: String?
}

struct TrainingProfile: Codable {
    var goal: String
    var equipment: String
    var experience: String
    var notes: String
}

struct HealthSnapshot: Codable {
    let hrv: Double?
    let sleepHours: Double?
    let date: String?
}

struct PlannedExercise: Codable, Identifiable {
    var id: String { name }
    let name: String
    let warmupSets: [PlannedSet]
    let workingSets: [PlannedSet]
    let restSec: Int?
}

struct PlannedSet: Codable, Identifiable {
    var id = UUID()
    let weight: Double?
    let reps: Int?
    let rpeTarget: Int?
    let distanceKm: Double?
    let paceTarget: String?

    enum CodingKeys: String, CodingKey {
        case weight, reps, rpeTarget, distanceKm, paceTarget
    }
}

struct SessionSet: Identifiable, Codable {
    var id = UUID()
    var weight: Double = 0
    var reps: Int = 0
    var rpe: Int? = nil
    var isWarmup: Bool = false
    var isFailure: Bool = false
    var done: Bool = false
}

struct SessionExercise: Identifiable, Codable {
    var id = UUID()
    var name: String
    var sets: [SessionSet] = []
}

struct ActiveSession: Codable {
    var dayType: String
    var dayLabel: String
    var exercises: [SessionExercise] = []
    var startTime: Date = Date()
    var notes: String = ""

    var elapsedSeconds: Int { Int(Date().timeIntervalSince(startTime)) }
}

struct LogWorkoutRequest: Encodable {
    let title: String
    let type: String
    let durationMin: Int?
    let notes: String?
    let rpe: Int?
    let sets: [LogSetPayload]
}

struct LogSetPayload: Encodable {
    let exercise: String
    let setIndex: Int
    let reps: Int?
    let weightKg: Double?
    let rpe: Int?
    let isWarmup: Bool
    let isFailure: Bool
}

struct UpdateWorkoutRequest: Encodable {
    let title: String?
    let notes: String?
    let rpe: Int?
    let sets: [LogSetPayload]
}

struct WorkoutDetail: Decodable {
    let id: Int
    let title: String
    let type: String
    let notes: String?
    let rpe: Int?
    let sets: [WorkoutDetailSet]
}

struct WorkoutDetailSet: Identifiable, Decodable {
    let id: Int
    let exercise: String?
    let reps: Int?
    let weightKg: Double?
    let rpe: Int?
    let isWarmup: Bool
    let isFailure: Bool
}

struct LastSet: Decodable { let reps: Int?; let weightKg: Double? }

struct LogWorkoutResponse: Decodable {
    let id: Int
}

struct LogRPERequest: Encodable {
    let workoutId: Int
    let exercise: String
    let rpe: Int
}

struct WorkoutHistoryItem: Codable, Identifiable {
    let id: Int
    let date: String
    let title: String
    let type: String
    let durationMin: Int?
    let rpe: Int?
    let notes: String?
    let sets: [WorkoutSetItem]?
}

struct WorkoutSetItem: Codable, Identifiable {
    let id: Int
    let exercise: String?
    let reps: Int?
    let weightKg: Double?
    let rpe: Int?
    let setIndex: Int?
}

struct ExerciseItem: Codable, Identifiable {
    let id: Int
    let name: String
    let muscle: String?
    let category: String?
}

// MARK: - Nutrition Models

struct MacroEstimate: Decodable {
    let foodName: String?
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
    let portion: String?
    let confidence: Double?
}

struct AnalyzePhotoResponse: Decodable {
    let result: MacroEstimate?
    let ok: Bool?
    let error: String?
}

struct LogMealRequest: Encodable {
    let name: String
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
    let notes: String?
}

struct TodayNutritionResponse: Codable {
    let meals: [MealItem]?
    let totals: NutritionTotals?
}

struct NutritionTotals: Codable {
    let totalCalories: Double?
    let totalProtein: Double?
    let totalCarbs: Double?
    let totalFat: Double?
}

struct MealItem: Codable, Identifiable {
    let id: Int
    let name: String?
    let description: String?
    let calories: Double?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
    let createdAt: String?
    let status: String?

    var protein: Double? { proteinG }
    var carbs: Double? { carbsG }
    var fat: Double? { fatG }
    var displayName: String { name ?? description ?? "Mahlzeit" }
}

struct UpdateMealRequest: Encodable {
    let name: String
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
}

struct NutritionGoals: Decodable {
    let targetCalories: Double?
    let proteinG: Double?
    let carbsG: Double?
    let fatG: Double?
}

// MARK: - Health Models

struct HealthEntry: Codable, Identifiable {
    let id: String
    let date: String
    let hrv: Double?
    let restingHr: Double?
    let weight: Double?
    let sleepDuration: Double?
    let steps: Int?
    let bodyFat: Double?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try c.decode(String.self, forKey: .date)
        id = date
        hrv = try c.decodeIfPresent(Double.self, forKey: .hrv)
        restingHr = try c.decodeIfPresent(Double.self, forKey: .restingHr)
        weight = try c.decodeIfPresent(Double.self, forKey: .weight)
        sleepDuration = try c.decodeIfPresent(Double.self, forKey: .sleepDuration)
        steps = try c.decodeIfPresent(Int.self, forKey: .steps)
        bodyFat = try c.decodeIfPresent(Double.self, forKey: .bodyFat)
    }

    enum CodingKeys: String, CodingKey {
        case date, hrv, restingHr, weight, sleepDuration, steps, bodyFat
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(date, forKey: .date)
        try c.encodeIfPresent(hrv, forKey: .hrv)
        try c.encodeIfPresent(restingHr, forKey: .restingHr)
        try c.encodeIfPresent(weight, forKey: .weight)
        try c.encodeIfPresent(sleepDuration, forKey: .sleepDuration)
        try c.encodeIfPresent(steps, forKey: .steps)
        try c.encodeIfPresent(bodyFat, forKey: .bodyFat)
    }
}

struct HealthPushPayload: Encodable {
    let date: String
    let hrv: Double?
    let restingHr: Double?
    let weight: Double?
    let sleepDuration: Double?
    let steps: Int?
}

struct OkResponse: Decodable {
    let ok: Bool?
    let id: Int?
    let written: Bool?
}

// MARK: - SwiftData Cache

@Model
final class CachedWorkout {
    var id: Int
    var date: String
    var title: String
    var type: String
    var durationMin: Int?
    var rpe: Int?
    var notes: String?

    init(id: Int, date: String, title: String, type: String,
         durationMin: Int? = nil, rpe: Int? = nil, notes: String? = nil) {
        self.id = id; self.date = date; self.title = title; self.type = type
        self.durationMin = durationMin; self.rpe = rpe; self.notes = notes
    }
}

@Model
final class CachedExercise {
    var name: String
    var lastWeightKg: Double
    var lastReps: Int
    var personalRecord: Double

    init(name: String, lastWeightKg: Double, lastReps: Int, personalRecord: Double) {
        self.name = name; self.lastWeightKg = lastWeightKg
        self.lastReps = lastReps; self.personalRecord = personalRecord
    }
}

// MARK: - Offline Cache (UserDefaults)

final class OfflineCache {
    static let shared = OfflineCache()
    private let defaults = UserDefaults.standard
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    func save<T: Encodable>(_ value: T, key: String) {
        if let data = try? encoder.encode(value) {
            defaults.set(data, forKey: key)
        }
    }

    func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? decoder.decode(T.self, from: data)
    }

    func clear(_ key: String) {
        defaults.removeObject(forKey: key)
    }
}

// MARK: - Helpers

extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
