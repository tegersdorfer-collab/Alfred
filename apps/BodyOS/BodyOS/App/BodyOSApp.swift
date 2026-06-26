import SwiftUI
import SwiftData

@main
struct BodyOSApp: App {
    var sharedModelContainer: ModelContainer = {
        let schema = Schema([CachedWorkout.self, CachedExercise.self])
        let config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)
        return try! ModelContainer(for: schema, configurations: [config])
    }()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .task { await HealthKitManager.shared.enableBackgroundSync() }
        }
        .modelContainer(sharedModelContainer)
    }
}
