import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects
import Gestura 1.0
import "."

ApplicationWindow {
    id: win
    width: 1120
    height: 720
    minimumWidth: 900
    minimumHeight: 600
    visible: true
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "Gestura"

    Component.onCompleted: Theme.dark = (controller.theme !== "light")
    Connections {
        target: controller
        function onThemeChanged() { Theme.dark = (controller.theme !== "light") }
        function onFrameReady(image, points) { cameraView.update_frame(image, points) }
        function onGestureFired(name) { toast.show(name) }
    }

    // ---- Background ----------------------------------------------------------------------
    Rectangle {
        id: bg
        anchors.fill: parent
        radius: 22
        clip: true
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Theme.bg0 }
            GradientStop { position: 1.0; color: Theme.bg1 }
        }
        border.width: 1
        border.color: Theme.stroke

        // Soft aurora glows for glassmorphism depth.
        Rectangle {
            width: 460; height: 460; radius: width / 2
            x: -120; y: -160
            color: Theme.accent; opacity: Theme.dark ? 0.22 : 0.14
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
        }
        Rectangle {
            width: 520; height: 520; radius: width / 2
            x: parent.width - 320; y: parent.height - 340
            color: Theme.accent2; opacity: Theme.dark ? 0.20 : 0.12
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
        }
    }

    // ---- Root layout ---------------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12

        // Title bar (drag + window controls)
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            MouseArea {
                anchors.fill: parent
                onPressed: win.startSystemMove()
                onDoubleClicked: win.visibility === Window.Maximized
                                 ? win.showNormal() : win.showMaximized()
            }
            RowLayout {
                anchors.fill: parent
                spacing: 10
                Rectangle {
                    width: 26; height: 26; radius: 8
                    gradient: Gradient {
                        GradientStop { position: 0; color: Theme.accent }
                        GradientStop { position: 1; color: Theme.accent2 }
                    }
                    Text { anchors.centerIn: parent; text: "✦"; color: "#07202a"
                           font.pixelSize: 16; font.bold: true }
                }
                Text { text: "Gestura"; color: Theme.text; font.pixelSize: Theme.fontL
                       font.weight: Font.DemiBold }
                Text { text: "offline gesture control"; color: Theme.subtext
                       font.pixelSize: Theme.fontS; Layout.alignment: Qt.AlignVCenter }
                Item { Layout.fillWidth: true }

                WinButton { glyph: "🌓"; onClicked: controller.setTheme(Theme.dark ? "light" : "dark") }
                WinButton { glyph: "—"; onClicked: win.showMinimized() }
                WinButton { glyph: "✕"; danger: true; onClicked: Qt.quit() }
            }
        }

        // Error banner
        GlassPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            visible: controller.initError !== ""
            strong: true
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.pad
                anchors.rightMargin: Theme.pad
                Text { text: "⚠"; color: Theme.bad; font.pixelSize: 18 }
                Text { text: controller.initError; color: Theme.text
                       font.pixelSize: Theme.fontM; Layout.fillWidth: true; elide: Text.ElideRight }
            }
        }

        // Main content
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            // Camera card
            GlassPanel {
                Layout.preferredWidth: parent.width * 0.56
                Layout.fillHeight: true
                clip: true

                CameraView {
                    id: cameraView
                    anchors.fill: parent
                    anchors.margins: 1
                }

                // Camera status chip
                Rectangle {
                    x: 16; y: 16
                    radius: height / 2
                    height: 30
                    width: statusRow.implicitWidth + 24
                    color: Qt.rgba(0, 0, 0, 0.45)
                    Row {
                        id: statusRow
                        anchors.centerIn: parent
                        spacing: 8
                        Rectangle {
                            width: 9; height: 9; radius: 4.5
                            anchors.verticalCenter: parent.verticalCenter
                            color: controller.cameraStatus === "streaming" ? Theme.good
                                   : controller.cameraStatus === "recovering" ? Theme.warn : Theme.bad
                            SequentialAnimation on opacity {
                                running: controller.cameraStatus !== "streaming"
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.3; duration: 600 }
                                NumberAnimation { to: 1.0; duration: 600 }
                            }
                        }
                        Text {
                            text: controller.cameraStatus
                            color: "white"; font.pixelSize: Theme.fontS
                            font.capitalization: Font.Capitalize
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // Pose + paused overlay (bottom)
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 16
                    visible: controller.pose !== "none" || controller.paused
                    radius: height / 2
                    height: 34
                    width: poseText.implicitWidth + 30
                    color: controller.paused ? Qt.rgba(0.94, 0.43, 0.43, 0.9)
                                             : Qt.rgba(0.28, 0.84, 0.60, 0.9)
                    Text {
                        id: poseText
                        anchors.centerIn: parent
                        text: controller.paused ? "PAUSED" : controller.pose.replace("_", " ")
                        color: "#06121a"; font.pixelSize: Theme.fontM; font.weight: Font.DemiBold
                        font.capitalization: Font.Capitalize
                    }
                }
            }

            // Right column
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                // Primary control
                PillButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    accentFill: !controller.paused
                    accent: controller.paused ? Theme.good : Theme.accent
                    text: controller.paused ? "▶  Resume control" : "❚❚  Pause control"
                    onClicked: controller.togglePause()
                }

                // Stat tiles
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 12
                    columnSpacing: 12
                    StatTile {
                        Layout.fillWidth: true
                        caption: "Frame rate"; unit: "fps"
                        value: controller.fps.toFixed(0)
                        accent: controller.fps >= 24 ? Theme.good
                                : controller.fps >= 12 ? Theme.warn : Theme.bad
                    }
                    StatTile {
                        Layout.fillWidth: true
                        caption: "Latency"; unit: "ms"
                        value: controller.inferenceMs.toFixed(0)
                        accent: Theme.accent2
                    }
                    StatTile {
                        Layout.fillWidth: true
                        caption: "Mode"
                        value: controller.mode.charAt(0) + controller.mode.slice(1).toLowerCase()
                        accent: Theme.accent
                    }
                    StatTile {
                        Layout.fillWidth: true
                        caption: "Hand"
                        value: controller.handPresent ? "Tracked" : "—"
                        accent: controller.handPresent ? Theme.good : Theme.subtext
                    }
                }

                // Confidence meter
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 70
                    Column {
                        anchors.fill: parent
                        anchors.margins: Theme.pad
                        spacing: 8
                        Text { text: "CONFIDENCE"; color: Theme.subtext
                               font.pixelSize: Theme.fontS; font.letterSpacing: 1.2 }
                        Rectangle {
                            width: parent.width; height: 12; radius: 6
                            color: Theme.stroke
                            Rectangle {
                                height: parent.height; radius: 6
                                width: parent.width * Math.max(0, Math.min(1, controller.confidence))
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0; color: Theme.accent }
                                    GradientStop { position: 1; color: Theme.good }
                                }
                                Behavior on width { NumberAnimation { duration: 120 } }
                            }
                        }
                    }
                }

                // Gesture cheat sheet
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Column {
                        anchors.fill: parent
                        anchors.margins: Theme.pad
                        spacing: 10
                        Text { text: "GESTURES"; color: Theme.subtext
                               font.pixelSize: Theme.fontS; font.letterSpacing: 1.2 }
                        Repeater {
                            model: [
                                { g: "👌  Pinch", a: "Left click" },
                                { g: "🤏  Middle pinch", a: "Right click" },
                                { g: "✊  Fist", a: "Drag" },
                                { g: "✌  Two fingers", a: "Scroll" },
                                { g: "👍  Thumb up / down", a: "Volume" },
                                { g: "🖐  Open palm (hold)", a: "Pause / resume" }
                            ]
                            Row {
                                width: parent.width
                                spacing: 8
                                Text { text: modelData.g; color: Theme.text
                                       font.pixelSize: Theme.fontM; width: parent.width * 0.55 }
                                Text { text: modelData.a; color: Theme.subtext
                                       font.pixelSize: Theme.fontM }
                            }
                        }
                    }
                }
            }
        }
    }

    // Transient gesture toast
    Rectangle {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        radius: height / 2
        height: 40
        width: toastText.implicitWidth + 36
        color: Theme.glassStrong
        border.width: 1
        border.color: Theme.glassBorder
        opacity: 0
        property alias label: toastText.text
        function show(name) { toastText.text = "✓ " + name.replace("_", " "); anim.restart() }
        Text { id: toastText; anchors.centerIn: parent; color: Theme.text
               font.pixelSize: Theme.fontM; font.capitalization: Font.Capitalize }
        SequentialAnimation {
            id: anim
            NumberAnimation { target: toast; property: "opacity"; to: 1; duration: 120 }
            PauseAnimation { duration: 800 }
            NumberAnimation { target: toast; property: "opacity"; to: 0; duration: 400 }
        }
    }

    // Inline window button component
    component WinButton: Rectangle {
        property string glyph: ""
        property bool danger: false
        signal clicked()
        width: 34; height: 30; radius: 8
        color: wbma.containsMouse ? (danger ? Qt.rgba(0.94, 0.43, 0.43, 0.85) : Theme.glassStrong)
                                  : "transparent"
        Behavior on color { ColorAnimation { duration: 120 } }
        Text { anchors.centerIn: parent; text: glyph
               color: (danger && wbma.containsMouse) ? "white" : Theme.subtext
               font.pixelSize: 14 }
        MouseArea {
            id: wbma; anchors.fill: parent; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor; onClicked: parent.clicked()
        }
    }
}
