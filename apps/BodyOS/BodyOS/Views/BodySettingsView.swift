import SwiftUI

struct BodySettingsView: View {
    @AppStorage("alfred_base_url") private var baseURL = "http://macbook-air-von-timo.tail7e29ff.ts.net:7779"
    @State private var isConnected: Bool? = nil
    @State private var isTesting = false
    @StateObject private var hk = HealthKitManager.shared

    var body: some View {
        NavigationStack {
            Form {
                Section("Alfred Verbindung") {
                    TextField("URL", text: $baseURL)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
                    Button {
                        Task { await testConnection() }
                    } label: {
                        HStack {
                            Text("Verbindung testen")
                            Spacer()
                            if isTesting {
                                ProgressView()
                            } else if let connected = isConnected {
                                Image(systemName: connected ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundStyle(connected ? .green : .red)
                            }
                        }
                    }
                }

                Section("HealthKit") {
                    HStack {
                        Text("Status")
                        Spacer()
                        Text(hk.isAuthorized ? "Verbunden" : "Nicht autorisiert")
                            .foregroundStyle(hk.isAuthorized ? .green : .secondary)
                    }
                    if !hk.isAuthorized {
                        Button("Zugriff erlauben") { Task { await hk.requestAuthorization() } }
                    }
                    if let last = hk.lastSync {
                        HStack {
                            Text("Letzter Sync")
                            Spacer()
                            Text(last.formatted(date: .omitted, time: .shortened))
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Info") {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text("1.0").foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Ziel-Kalorien")
                        Spacer()
                        Text("2800 kcal").foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Ziel-Protein")
                        Spacer()
                        Text("180 g").foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Einstellungen")
        }
    }

    private func testConnection() async {
        isTesting = true
        isConnected = await AlfredClient.shared.isReachable
        isTesting = false
    }
}
