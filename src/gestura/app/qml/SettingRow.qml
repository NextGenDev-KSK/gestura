import QtQuick
import QtQuick.Controls.Basic
import "."

// A labelled slider bound to a dotted settings path. Hides itself when it doesn't match the
// settings search filter.
Item {
    id: row
    property string label: ""
    property string path: ""
    property real minv: 0
    property real maxv: 1
    property real stepSize: 0.01
    property string suffix: ""
    property string filter: ""

    readonly property bool matches:
        filter === "" || label.toLowerCase().indexOf(filter.toLowerCase()) !== -1
    width: parent ? parent.width : 300
    height: matches ? 56 : 0
    visible: matches
    clip: true

    function _decimals(step) {
        return step >= 1 ? 0 : (step >= 0.1 ? 1 : (step >= 0.01 ? 2 : 3))
    }

    Column {
        width: parent.width
        spacing: 4
        Row {
            width: parent.width
            Text {
                text: row.label; color: Theme.text; font.pixelSize: Theme.fontM
                width: parent.width - valText.width
            }
            Text {
                id: valText
                text: slider.value.toFixed(row._decimals(row.stepSize)) + row.suffix
                color: Theme.accent; font.pixelSize: Theme.fontM
            }
        }
        Slider {
            id: slider
            width: parent.width
            from: row.minv; to: row.maxv; stepSize: row.stepSize
            Component.onCompleted: {
                var v = controller.getSetting(row.path)
                if (v !== null && v !== undefined) value = v
            }
            onMoved: controller.setNumber(row.path, value)
            background: Rectangle {
                x: slider.leftPadding
                y: slider.topPadding + slider.availableHeight / 2 - 3
                width: slider.availableWidth; height: 6; radius: 3; color: Theme.stroke
                Rectangle {
                    width: slider.visualPosition * parent.width; height: parent.height
                    radius: 3
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.accent }
                        GradientStop { position: 1; color: Theme.accent2 }
                    }
                }
            }
            handle: Rectangle {
                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - 16)
                y: slider.topPadding + slider.availableHeight / 2 - 8
                width: 16; height: 16; radius: 8
                color: "white"; border.color: Theme.accent; border.width: 2
            }
        }
    }
}
