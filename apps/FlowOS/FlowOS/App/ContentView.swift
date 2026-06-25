import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            TodayView()
                .tabItem { Label("Heute", systemImage: "sun.max.fill") }
                .tag(0)

            HabitsView()
                .tabItem { Label("Gewohnheiten", systemImage: "circle.dotted") }
                .tag(1)

            TasksView()
                .tabItem { Label("Aufgaben", systemImage: "checklist") }
                .tag(2)

            CalendarView()
                .tabItem { Label("Kalender", systemImage: "calendar") }
                .tag(3)

            FlowSettingsView()
                .tabItem { Label("Einstellungen", systemImage: "gearshape.fill") }
                .tag(4)
        }
        .tint(.indigo)
    }
}
