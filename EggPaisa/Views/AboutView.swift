import SwiftUI

struct AboutView: View {
    @Environment(PriceStore.self) private var store
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            Section {
                Text("EggPaisa shows daily NECC egg prices for 7 zones, to help poultry farmers follow the market.")
            }
            Section("Data") {
                Text("Prices come from the National Egg Co-ordination Committee (NECC) website.")
                Text("The app checks NECC for new prices when you open it and keeps them for offline use.")
                if let sourceURL = store.sourceURL {
                    Link("Open NECC egg prices", destination: sourceURL)
                }
                LabeledContent("Unit", value: "₹ per 100 eggs")
                if let lastPriceDate = store.lastPriceDate {
                    LabeledContent("Latest data") {
                        Text(lastPriceDate, format: .dateTime.day().month(.abbreviated).year())
                    }
                }
                Text("When NECC shows no price for a day, the previous day's price is used.")
                Text("EggPaisa is not affiliated with NECC.")
            }
            ClarificationSection(text: store.clarification)
            Section {
                LabeledContent("Version", value: version)
            }
        }
        .navigationTitle("About")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button("Done") {
                    dismiss()
                }
            }
        }
    }

    private var version: String {
        let info = Bundle.main.infoDictionary
        let marketing = info?["CFBundleShortVersionString"] as? String ?? "–"
        let build = info?["CFBundleVersion"] as? String ?? "–"
        return "\(marketing) (\(build))"
    }
}
