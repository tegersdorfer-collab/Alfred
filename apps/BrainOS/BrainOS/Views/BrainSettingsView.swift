import SwiftUI

struct BrainSettingsView: View {
    @AppStorage("alfred_base_url") private var baseURL: String = "http://macbook-air-von-timo.tail7e29ff.ts.net:7779"
    @State private var testResult: String?
    @State private var isTesting = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Alfred Verbindung") {
                    TextField("Base URL", text: $baseURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)

                    Button {
                        Task { await testConnection() }
                    } label: {
                        HStack {
                            if isTesting { ProgressView().scaleEffect(0.8) }
                            else { Image(systemName: "network") }
                            Text("Verbindung testen")
                        }
                    }

                    if let result = testResult {
                        Text(result)
                            .font(.footnote)
                            .foregroundColor(result.contains("✓") ? .green : .red)
                    }
                }

                Section("Info") {
                    LabeledContent("App", value: "BrainOS")
                    LabeledContent("Version", value: "1.0")
                    LabeledContent("Backend", value: "Alfred FastAPI :7779")
                }
            }
            .navigationTitle("Einstellungen")
        }
    }

    private func testConnection() async {
        isTesting = true; testResult = nil
        let ok = await AlfredClient.shared.isReachable
        testResult = ok ? "✓ Verbunden mit Alfred" : "✗ Nicht erreichbar – URL prüfen"
        isTesting = false
    }
}
