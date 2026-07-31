import QtQuick
import "."

// A rounded, glassy button with hover/press feedback. Set `accentFill` for a solid accent look.
Rectangle {
    id: btn
    property string text: ""
    property bool accentFill: false
    property color accent: Theme.accent
    signal clicked()

    implicitWidth: label.implicitWidth + 40
    implicitHeight: 42
    radius: height / 2
    antialiasing: true
    color: accentFill
           ? (ma.pressed ? Qt.darker(accent, 1.2) : (ma.containsMouse ? Qt.lighter(accent, 1.08) : accent))
           : (ma.pressed ? Theme.glassStrong : (ma.containsMouse ? Theme.glassStrong : Theme.glass))
    border.width: accentFill ? 0 : 1
    border.color: Theme.glassBorder

    Behavior on color { ColorAnimation { duration: 120 } }

    Text {
        id: label
        anchors.centerIn: parent
        text: btn.text
        color: btn.accentFill ? "#07202a" : Theme.text
        font.pixelSize: Theme.fontM
        font.weight: Font.DemiBold
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
