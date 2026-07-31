import QtQuick
import QtQuick.Effects
import "."

// A frosted-glass card: translucent fill, hairline border, a soft top highlight for the "lit
// edge" glass look, and a diffuse drop shadow for depth.
Rectangle {
    id: root
    property bool strong: false
    color: strong ? Theme.glassStrong : Theme.glass
    radius: Theme.radius
    border.width: 1
    border.color: Theme.glassBorder
    antialiasing: true

    // Lit top edge — a subtle vertical highlight that sells the glass surface.
    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, Theme.dark ? 0.10 : 0.35) }
            GradientStop { position: 0.18; color: "transparent" }
        }
        border.width: 0
    }

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Qt.rgba(0, 0, 0, Theme.dark ? 0.55 : 0.18)
        shadowBlur: 0.7
        shadowVerticalOffset: 8
        shadowHorizontalOffset: 0
    }
}
