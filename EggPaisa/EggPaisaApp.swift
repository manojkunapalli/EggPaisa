//
//  EggPaisaApp.swift
//  EggPaisa
//
//  Created by manojkiran on 26/10/26.
//

import SwiftUI

@main
struct EggPaisaApp: App {
    @State private var store = PriceStore()
    @State private var forecasts = ForecastStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(store)
                .environment(forecasts)
        }
    }
}
