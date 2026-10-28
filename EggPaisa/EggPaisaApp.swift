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

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(store)
        }
    }
}
