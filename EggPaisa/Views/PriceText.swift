import SwiftUI

enum PriceFormat {
    /// Indian number style whatever the phone's region, e.g. "₹1,250" and "+5%", not "1 250 ₹" and "+5 %".
    private static let locale = Locale(identifier: "en_IN")

    static func rupees(_ price: Double) -> String {
        price.formatted(.currency(code: "INR").precision(.fractionLength(0...2)).locale(locale))
    }

    static func change(_ change: Double) -> String {
        change.formatted(
            .currency(code: "INR").precision(.fractionLength(0...2)).sign(strategy: .always()).locale(locale)
        )
    }

    /// Whole percent with a sign, e.g. "+14%"; `percent` is in percent units.
    static func percent(_ percent: Double) -> String {
        (whole(percent) / 100).formatted(
            .percent.precision(.fractionLength(0)).sign(strategy: .always(includingZero: false)).locale(locale)
        )
    }

    /// Whole number with a sign and no % sign, short enough for a label on a narrow bar, e.g. "+14".
    static func signedWhole(_ value: Double) -> String {
        whole(value).formatted(
            .number.precision(.fractionLength(0)).sign(strategy: .always(includingZero: false)).locale(locale)
        )
    }

    /// Chart axis numbers, e.g. "1,000".
    static func number(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)).locale(locale))
    }

    /// Adding 0 turns -0 into 0, so a value that rounds to zero shows as "0", not "-0".
    private static func whole(_ value: Double) -> Double {
        value.rounded() + 0
    }
}

/// Change since the previous day; rises are green because higher prices help farmers.
struct ChangeLabel: View {
    let change: Double?

    var body: some View {
        if let change {
            if change == 0 {
                Text("No change")
                    .foregroundStyle(.secondary)
            } else {
                // Not a Label: in a list row, a Label moves the row's divider to its title and adds a wide icon gap.
                HStack(spacing: 2) {
                    Image(systemName: change > 0 ? "arrow.up.right" : "arrow.down.right")
                        .accessibilityHidden(true)
                    Text(PriceFormat.change(change))
                }
                .foregroundStyle(change > 0 ? Color.green : Color.red)
            }
        }
    }
}

struct ClarificationSection: View {
    let text: String

    var body: some View {
        Section("NECC clarification") {
            Text(text)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }
}
