import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView(tabSelection: $selectedTab)
                .tabItem { Label("Dashboard", systemImage: "house.fill") }
                .tag(0)

            WorkoutView()
                .tabItem { Label("Training", systemImage: "dumbbell.fill") }
                .tag(1)

            NutritionView()
                .tabItem { Label("Ernährung", systemImage: "fork.knife") }
                .tag(2)

            HealthView()
                .tabItem { Label("Gesundheit", systemImage: "heart.fill") }
                .tag(3)

            BodySettingsView()
                .tabItem { Label("Einstellungen", systemImage: "gearshape.fill") }
                .tag(4)
        }
        .tint(.orange)
    }
}
