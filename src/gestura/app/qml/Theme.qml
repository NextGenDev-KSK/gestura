pragma Singleton
import QtQuick

// Central design tokens. `dark` is set from the controller's theme at startup; every colour is
// derived from it so the whole UI flips consistently between light and dark.
QtObject {
    id: theme

    property bool dark: true

    // Surfaces
    readonly property color bg0: dark ? "#0a0d15" : "#e9edf4"
    readonly property color bg1: dark ? "#141a2b" : "#ffffff"
    readonly property color glass: dark ? Qt.rgba(1, 1, 1, 0.055) : Qt.rgba(1, 1, 1, 0.60)
    readonly property color glassStrong: dark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(1, 1, 1, 0.80)
    readonly property color glassBorder: dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.85)
    readonly property color stroke: dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.08)

    // Text
    readonly property color text: dark ? "#e9edf6" : "#131824"
    readonly property color subtext: dark ? "#8b93a7" : "#5c6577"

    // Brand / status
    readonly property color accent: "#48d6de"
    readonly property color accent2: "#7c9cff"
    readonly property color good: "#54d69a"
    readonly property color warn: "#f2c14e"
    readonly property color bad: "#f06d6d"

    // Metrics
    readonly property real radius: 18
    readonly property real pad: 16
    readonly property int fontS: 12
    readonly property int fontM: 14
    readonly property int fontL: 20
    readonly property int fontXL: 34
}
