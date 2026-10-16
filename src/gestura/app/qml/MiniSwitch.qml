import QtQuick
import QtQuick.Controls.Basic
import "."

// Compact on/off switch. Emits toggled(on); the owner sets `checked` from its model.
Rectangle {
    id: sw
    property bool checked: false
    signal toggled(bool on)
    width: 40; height: 22; radius: 11
    color: checked ? Theme.accent : Theme.stroke
    Behavior on color { ColorAnimation { duration: 120 } }
    Rectangle {
        width: 16; height: 16; radius: 8; color: "white"
        y: 3; x: sw.checked ? 21 : 3
        Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
        onClicked: sw.toggled(!sw.checked)
    }
}
