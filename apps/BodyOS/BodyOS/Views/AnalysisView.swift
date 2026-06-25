import SwiftUI
import UIKit

@MainActor
final class AnalysisViewModel: ObservableObject {
    @Published var estimate: MacroEstimate?
    @Published var isLoading = false
    @Published var error: String?
    @Published var isSaving = false
    @Published var saved = false

    @Published var editedName = ""
    @Published var editedCalories = ""
    @Published var editedProtein = ""
    @Published var editedCarbs = ""
    @Published var editedFat = ""

    func analyze(image: UIImage, annotation: String) async {
        isLoading = true; error = nil
        guard let jpeg = image.jpegData(compressionQuality: 0.8) else {
            error = "Bild konnte nicht konvertiert werden"
            isLoading = false; return
        }
        do {
            let result = try await NutritionAPI.shared.analyzePhoto(imageData: jpeg, annotation: annotation.isEmpty ? nil : annotation)
            estimate = result; prefill(result)
        } catch { self.error = error.localizedDescription }
        isLoading = false
    }

    func logMeal() async {
        isSaving = true
        let req = LogMealRequest(name: editedName.isEmpty ? (estimate?.foodName ?? "Mahlzeit") : editedName,
                                 calories: Double(editedCalories), protein: Double(editedProtein),
                                 carbs: Double(editedCarbs), fat: Double(editedFat), notes: nil)
        do { try await NutritionAPI.shared.logMeal(req); saved = true }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }

    private func prefill(_ m: MacroEstimate) {
        editedName = m.foodName ?? ""
        editedCalories = m.calories.map { String(format: "%.0f", $0) } ?? ""
        editedProtein = m.protein.map { String(format: "%.1f", $0) } ?? ""
        editedCarbs = m.carbs.map { String(format: "%.1f", $0) } ?? ""
        editedFat = m.fat.map { String(format: "%.1f", $0) } ?? ""
    }
}

struct AnalysisView: View {
    let image: UIImage
    let annotation: String
    let onComplete: () -> Void
    @StateObject private var vm = AnalysisViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(uiImage: image).resizable().scaledToFill()
                    .frame(height: 200).clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 16)).padding(.horizontal)

                if vm.isLoading {
                    VStack(spacing: 16) {
                        ProgressView().scaleEffect(1.5)
                        Text("Alfred analysiert…").foregroundStyle(.secondary)
                    }
                    .padding(40)
                } else if vm.saved {
                    savedView
                } else if vm.estimate != nil {
                    macroForm
                    logButton
                } else if let err = vm.error {
                    errorView(err)
                }
            }
            .padding(.top)
        }
        .navigationTitle("Analyse")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.analyze(image: image, annotation: annotation) }
    }

    private var macroForm: some View {
        VStack(spacing: 16) {
            if let conf = vm.estimate?.confidence {
                HStack {
                    Image(systemName: "brain").foregroundStyle(.green)
                    Text("Konfidenz: \(Int(conf * 100))%").font(.caption).foregroundStyle(.secondary)
                }
                .padding(.horizontal)
            }
            Group {
                macroField("Name", $vm.editedName, .default)
                macroField("Kalorien (kcal)", $vm.editedCalories, .decimalPad)
                macroField("Protein (g)", $vm.editedProtein, .decimalPad)
                macroField("Kohlenhydrate (g)", $vm.editedCarbs, .decimalPad)
                macroField("Fett (g)", $vm.editedFat, .decimalPad)
            }
            if let kcal = Double(vm.editedCalories), kcal > 0 { macroBar(kcal: kcal) }
        }
    }

    private func macroField(_ label: String, _ binding: Binding<String>, _ keyboard: UIKeyboardType) -> some View {
        HStack {
            Text(label).font(.subheadline).frame(minWidth: 130, alignment: .leading)
            Spacer()
            TextField("0", text: binding).keyboardType(keyboard)
                .multilineTextAlignment(.trailing).frame(width: 100).textFieldStyle(.roundedBorder)
        }
        .padding(.horizontal)
    }

    private func macroBar(kcal: Double) -> some View {
        let p = (Double(vm.editedProtein) ?? 0) * 4
        let c = (Double(vm.editedCarbs) ?? 0) * 4
        let f = (Double(vm.editedFat) ?? 0) * 9
        let total = p + c + f
        return VStack(alignment: .leading, spacing: 6) {
            Text("Makro-Verteilung").font(.caption).foregroundStyle(.secondary)
            GeometryReader { geo in
                HStack(spacing: 0) {
                    Color.blue.frame(width: total > 0 ? geo.size.width * (p/total) : 0)
                    Color.orange.frame(width: total > 0 ? geo.size.width * (c/total) : 0)
                    Color.yellow.frame(width: total > 0 ? geo.size.width * (f/total) : 0)
                }
                .clipShape(RoundedRectangle(cornerRadius: 4))
            }
            .frame(height: 12)
            HStack(spacing: 16) {
                legendDot(.blue, "Protein"); legendDot(.orange, "Carbs"); legendDot(.yellow, "Fett")
            }
            .font(.caption2)
        }
        .padding(.horizontal)
    }

    private func legendDot(_ color: Color, _ label: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(label).foregroundStyle(.secondary)
        }
    }

    private var logButton: some View {
        Button { Task { await vm.logMeal() } } label: {
            Group {
                if vm.isSaving { ProgressView().tint(.white) }
                else { HStack { Image(systemName: "square.and.arrow.down"); Text("Mahlzeit speichern").fontWeight(.semibold) } }
            }
            .frame(maxWidth: .infinity).padding()
            .background(Color.green).foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .disabled(vm.isSaving).padding(.horizontal).padding(.bottom, 32)
    }

    private var savedView: some View {
        VStack(spacing: 20) {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 64)).foregroundStyle(.green)
            Text("Gespeichert!").font(.title2.bold())
            Button("Zurück") { onComplete(); dismiss() }.buttonStyle(.bordered)
        }
        .padding(40)
    }

    private func errorView(_ err: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.orange)
            Text("Analyse fehlgeschlagen").font(.headline)
            Text(err).font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("Erneut versuchen") { Task { await vm.analyze(image: image, annotation: annotation) } }
                .buttonStyle(.bordered)
        }
        .padding()
    }
}
