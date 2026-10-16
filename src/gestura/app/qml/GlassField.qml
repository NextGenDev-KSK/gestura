import QtQuick
import QtQuick.Controls.Basic
import "."

// Single-line text input in the glass style.
TextField {
    id: tf
    height: 36
    color: Theme.text
    placeholderTextColor: Theme.subtext
    selectionColor: Theme.accent
    selectedTextColor: "#07202a"
    font.pixelSize: Theme.fontM
    leftPadding: 12; rightPadding: 12
    background: Rectangle {
        radius: 10
        color: Theme.glass
        opacity: tf.enabled ? 1 : 0.6
        border.width: 1
        border.color: tf.activeFocus ? Theme.accent : Theme.glassBorder
    }
}
