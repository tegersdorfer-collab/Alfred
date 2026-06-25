import SwiftUI

struct BrainContentView: View {
    @State private var selectedTab: Tab = .daily

    enum Tab { case daily, notes, search, graph, quotes, settings }

    var body: some View {
        TabView(selection: $selectedTab) {
            DailyNoteView()
                .tabItem { Label("Heute", systemImage: "sun.max.fill") }
                .tag(Tab.daily)

            NoteListView()
                .tabItem { Label("Notizen", systemImage: "note.text") }
                .tag(Tab.notes)

            SearchView()
                .tabItem { Label("Suche", systemImage: "magnifyingglass") }
                .tag(Tab.search)

            GraphView()
                .tabItem { Label("Graph", systemImage: "circle.hexagongrid") }
                .tag(Tab.graph)

            QuotesView()
                .tabItem { Label("Zitate", systemImage: "quote.bubble") }
                .tag(Tab.quotes)

            BrainSettingsView()
                .tabItem { Label("Einstellungen", systemImage: "gear") }
                .tag(Tab.settings)
        }
        .tint(.purple)
    }
}
