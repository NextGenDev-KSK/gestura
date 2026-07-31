import QtQuick
import "."

// A small always-on-top status pill, visible even when the main window is minimized. Shows the
// current pose / mode / paused state and can be dragged. Toggle via the "Status overlay" setting.
Window {
    id: overlay
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    width: 190
    height: 52
    x: Screen.width - width - 28
    y: Screen.height - height - 72

    Rectangle {
        anchors.fill: parent
        radius: 16
        color: Qt.rgba(0.05, 0.06, 0.09, 0.88)
        border.color: Theme.glassBorder
        border.width: 1

        Row {
            anchors.centerIn: parent
            spacing: 10

            Rectangle {
                width: 12; height: 12; radius: 6
                anchors.verticalCenter: parent.verticalCenter
                color: controller.paused ? Theme.warn
                       : controller.handPresent ? Theme.good : Theme.subtext
                SequentialAnimation on opacity {
                    running: !controller.paused && controller.handPresent
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.4; duration: 700 }
                    NumberAnimation { to: 1.0; duration: 700 }
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    text: controller.paused ? "Paused"
                          : (controller.pose === "none" ? "Ready" : controller.pose.replace("_", " "))
                    color: "white"; font.pixelSize: Theme.fontM; font.weight: Font.DemiBold
                    font.capitalization: Font.Capitalize
                }
                Text {
                    text: controller.mode.charAt(0) + controller.mode.slice(1).toLowerCase()
                          + " · " + controller.fps.toFixed(0) + " fps"
                    color: Theme.subtext; font.pixelSize: Theme.fontS
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            onPressed: overlay.startSystemMove()
        }
    }
}
