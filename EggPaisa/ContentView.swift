//
//  ContentView.swift
//  EggPaisa
//
//  Created by manojkiran on 26/10/26.
//

import SwiftUI

struct ContentView: View {
    @Environment(PriceStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationStack {
            if let loadError = store.loadError {
                ContentUnavailableView(
                    "Prices unavailable",
                    systemImage: "exclamationmark.triangle",
                    description: Text(loadError)
                )
            } else {
                TodayView()
            }
        }
        // On launch and each return to the app, as NECC publishes new prices during the day.
        .onChange(of: scenePhase, initial: true) { _, phase in
            if phase == .active {
                Task {
                    await store.refreshIfStale()
                }
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(PriceStore())
}
