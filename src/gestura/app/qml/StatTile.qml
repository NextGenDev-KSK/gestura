import QtQuick
import "."

// A compact metric card: caption on top, big value, optional unit + accent colour.
GlassPanel {
    id: tile
    property string caption: ""
    property string value: "—"
    property string unit: ""
    property color accent: Theme.accent
    implicitWidth: 150
    implicitHeight: 92

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.pad
        anchors.rightMargin: Theme.pad
        spacing: 6

        Text {
            text: tile.caption
            color: Theme.subtext
            font.pixelSize: Theme.fontS
            font.letterSpacing: 1.2
            font.capitalization: Font.AllUppercase
        }
        Row {
            spacing: 4
            Text {
                text: tile.value
                color: tile.accent
                font.pixelSize: Theme.fontXL
                font.weight: Font.DemiBold
            }
            Text {
                text: tile.unit
                color: Theme.subtext
                font.pixelSize: Theme.fontM
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 6
            }
        }
    }
}
