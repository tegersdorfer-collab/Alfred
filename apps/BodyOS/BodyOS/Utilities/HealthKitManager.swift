import Foundation
import HealthKit

@MainActor
final class HealthKitManager: ObservableObject {
    static let shared = HealthKitManager()
    private let store = HKHealthStore()

    @Published var isAvailable = HKHealthStore.isHealthDataAvailable()
    @Published var isAuthorized = false
    @Published var lastSync: Date? = nil

    private let readTypes: Set<HKObjectType> = [
        HKQuantityType(.stepCount),
        HKQuantityType(.heartRateVariabilitySDNN),
        HKQuantityType(.restingHeartRate),
        HKQuantityType(.bodyMass),
        HKCategoryType(.sleepAnalysis),
    ]

    func requestAuthorization() async {
        guard isAvailable else { return }
        do {
            // statusForAuthorizationRequest returns .unnecessary when already granted —
            // in that case requestAuthorization shows no dialog but still succeeds.
            let status = try await store.statusForAuthorizationRequest(toShare: [], read: readTypes)
            if status == .unnecessary {
                isAuthorized = true
                return
            }
            try await store.requestAuthorization(toShare: [], read: readTypes)
            isAuthorized = true
        } catch {
            // Even on error, attempt reads — HealthKit often works despite this
            isAuthorized = true
        }
    }

    func syncToday() async throws {
        guard isAvailable else { return }
        let today = Calendar.current.startOfDay(for: Date())
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: today)!
        let predicate = HKQuery.predicateForSamples(withStart: today, end: tomorrow)

        async let steps = fetchSteps(predicate: predicate)
        async let hrv = fetchLatestQuantity(.heartRateVariabilitySDNN, predicate: predicate)
        async let rhr = fetchLatestQuantity(.restingHeartRate, predicate: predicate)
        async let weight = fetchLatestQuantity(.bodyMass, unit: .gramUnit(with: .kilo), predicate: nil)
        async let sleep = fetchSleepHours(predicate: predicate)

        let isoDate = ISO8601DateFormatter()
        isoDate.formatOptions = [.withFullDate]
        let dateStr = isoDate.string(from: Date())

        let payload = HealthPushPayload(
            date: dateStr,
            hrv: try? await hrv,
            restingHr: try? await rhr,
            weight: try? await weight,
            sleepDuration: try? await sleep,
            steps: try? await steps
        )

        try await HealthAPI.shared.pushHealthData(payload)
        lastSync = Date()
    }

    func fetchRecentData(days: Int = 30) async throws -> [DailyHealthSnapshot] {
        guard isAvailable else { return [] }
        var snapshots: [DailyHealthSnapshot] = []
        let cal = Calendar.current

        for dayOffset in (0..<days).reversed() {
            guard let date = cal.date(byAdding: .day, value: -dayOffset, to: Date()) else { continue }
            let start = cal.startOfDay(for: date)
            let end = cal.date(byAdding: .day, value: 1, to: start)!
            let pred = HKQuery.predicateForSamples(withStart: start, end: end)

            let steps = (try? await fetchSteps(predicate: pred)) ?? 0
            let hrv = try? await fetchLatestQuantity(.heartRateVariabilitySDNN, predicate: pred)
            let rhr = try? await fetchLatestQuantity(.restingHeartRate, predicate: pred)
            let sleep = try? await fetchSleepHours(predicate: pred)

            let isoDate = ISO8601DateFormatter()
            isoDate.formatOptions = [.withFullDate]
            snapshots.append(DailyHealthSnapshot(
                date: isoDate.string(from: date),
                steps: steps,
                hrv: hrv,
                restingHr: rhr,
                sleepHours: sleep
            ))
        }
        return snapshots
    }

    private func fetchSteps(predicate: NSPredicate) async throws -> Int {
        try await withCheckedThrowingContinuation { cont in
            let type = HKQuantityType(.stepCount)
            let query = HKStatisticsQuery(quantityType: type, quantitySamplePredicate: predicate,
                                          options: .cumulativeSum) { _, stats, err in
                if let err { cont.resume(throwing: err); return }
                let val = stats?.sumQuantity()?.doubleValue(for: .count()) ?? 0
                cont.resume(returning: Int(val))
            }
            store.execute(query)
        }
    }

    private func fetchLatestQuantity(_ type: HKQuantityTypeIdentifier, unit: HKUnit = .count().unitDivided(by: .minute()), predicate: NSPredicate?) async throws -> Double {
        let qType = HKQuantityType(type)
        let unit: HKUnit = type == .heartRateVariabilitySDNN ? .secondUnit(with: .milli) :
                           type == .bodyMass ? .gramUnit(with: .kilo) :
                           type == .restingHeartRate ? .count().unitDivided(by: .minute()) : .count()
        return try await withCheckedThrowingContinuation { cont in
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
            let query = HKSampleQuery(sampleType: qType, predicate: predicate, limit: 1, sortDescriptors: [sort]) { _, samples, err in
                if let err { cont.resume(throwing: err); return }
                let val = (samples?.first as? HKQuantitySample)?.quantity.doubleValue(for: unit) ?? 0
                cont.resume(returning: val)
            }
            store.execute(query)
        }
    }

    private func fetchSleepHours(predicate: NSPredicate) async throws -> Double {
        try await withCheckedThrowingContinuation { cont in
            let type = HKCategoryType(.sleepAnalysis)
            let query = HKSampleQuery(sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, err in
                if let err { cont.resume(throwing: err); return }
                let totalSeconds = (samples as? [HKCategorySample])?.reduce(0.0) { sum, s in
                    guard s.value == HKCategoryValueSleepAnalysis.asleepCore.rawValue ||
                          s.value == HKCategoryValueSleepAnalysis.asleepDeep.rawValue ||
                          s.value == HKCategoryValueSleepAnalysis.asleepREM.rawValue else { return sum }
                    return sum + s.endDate.timeIntervalSince(s.startDate)
                } ?? 0
                cont.resume(returning: totalSeconds / 3600)
            }
            store.execute(query)
        }
    }
}

struct DailyHealthSnapshot: Identifiable {
    let id = UUID()
    let date: String
    let steps: Int
    let hrv: Double?
    let restingHr: Double?
    let sleepHours: Double?
}
