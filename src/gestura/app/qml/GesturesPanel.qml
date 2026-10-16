import QtQuick
import QtQuick.Controls.Basic
import "."

// Slide-in gesture editor: bind each gesture to a compatible action, switch gestures on/off, set
// keyboard shortcuts, and teach Gestura your own gestures — no settings.json editing required.
Item {
    id: panel
    property bool open: false
    anchors.fill: parent
    visible: open || slideAnim.running
    z: 100

    // Dim/scrim behind the panel.
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.45)
        opacity: panel.open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        MouseArea { anchors.fill: parent; onClicked: panel.open = false }
    }

    GlassPanel {
        id: sheet
        sheet: true
        strong: true
        width: Math.min(480, parent.width * 0.55)
        height: parent.height
        x: panel.open ? parent.width - width : parent.width
        Behavior on x { NumberAnimation { id: slideAnim; duration: 220; easing.type: Easing.OutCubic } }

        // Clicks on the sheet itself must not fall through to the scrim (which closes the panel).
        MouseArea { anchors.fill: parent }

        Column {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            Row {
                width: parent.width
                Text { text: "Gestures"; color: Theme.text; font.pixelSize: Theme.fontL
                       font.weight: Font.DemiBold; width: parent.width - 30 }
                Text {
                    text: "✕"; color: Theme.subtext; font.pixelSize: 16
                    MouseArea { anchors.fill: parent; anchors.margins: -8
                                cursorShape: Qt.PointingHandCursor; onClicked: panel.open = false }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Choose what each gesture does. Only actions a gesture can actually drive are "
                      + "offered. Changes apply instantly."
                color: Theme.subtext; font.pixelSize: Theme.fontS
            }

            Flickable {
                width: parent.width
                height: parent.height - y
                contentHeight: content.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollIndicator.vertical: ScrollIndicator {}

                Column {
                    id: content
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: controller.gestureRows
                        delegate: GestureRow { row: modelData; width: content.width }
                    }

                    SectionLabel { text: "Teach a new gesture" }
                    Trainer { width: content.width }

                    Item { width: 1; height: 4 }
                    PillButton {
                        text: "Reset to default gestures"
                        onClicked: controller.resetGestures()
                    }
                    Item { width: 1; height: 12 }
                }
            }
        }
    }

    // ---- One gesture: label, on/off, action picker, optional key-chord field ----------------
    component GestureRow: Rectangle {
        id: gr
        property var row
        readonly property bool bound: row.action !== ""
        readonly property bool isShortcut: row.action === "run_shortcut"
        height: rowCol.implicitHeight + 20
        radius: 12
        color: Theme.glass
        border.width: 1
        border.color: Theme.glassBorder

        Column {
            id: rowCol
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
            spacing: 8

            Item {
                width: parent.width
                height: 36
                opacity: (!gr.bound || gr.row.enabled) ? 1 : 0.55
                Text {
                    id: icon
                    text: gr.row.icon; font.pixelSize: 20
                    anchors.verticalCenter: parent.verticalCenter
                }
                Column {
                    anchors.left: icon.right; anchors.leftMargin: 10
                    anchors.right: tools.left; anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; text: gr.row.label; color: Theme.text
                           font.pixelSize: Theme.fontM; font.weight: Font.DemiBold
                           elide: Text.ElideRight }
                    Text { width: parent.width; text: gr.row.hint; color: Theme.subtext
                           font.pixelSize: Theme.fontS; elide: Text.ElideRight }
                }
                Row {
                    id: tools
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    MiniSwitch {
                        visible: gr.bound
                        checked: gr.row.enabled
                        anchors.verticalCenter: parent.verticalCenter
                        onToggled: (on) => controller.setGestureEnabled(gr.row.id, on)
                    }
                    Rectangle {
                        visible: gr.row.custom
                        width: 28; height: 28; radius: 8
                        anchors.verticalCenter: parent.verticalCenter
                        color: delMa.containsMouse ? Qt.rgba(0.94, 0.43, 0.43, 0.85) : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Text { anchors.centerIn: parent; text: "🗑"; font.pixelSize: 13
                               color: delMa.containsMouse ? "white" : Theme.subtext }
                        MouseArea {
                            id: delMa; anchors.fill: parent; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            ToolTip.visible: containsMouse
                            ToolTip.text: gr.row.recorded ? "Delete this gesture" : "Remove this binding"
                            onClicked: gr.row.recorded ? controller.deleteCustomGesture(gr.row.id)
                                                       : controller.setGestureAction(gr.row.id, "")
                        }
                    }
                }
            }

            GlassCombo {
                width: parent.width
                model: gr.row.choices
                textRole: "label"
                currentIndex: gr.row.choiceIndex
                onActivated: (i) => controller.setGestureAction(gr.row.id, gr.row.choices[i].id)
            }

            // Key chord for the "Keyboard shortcut" action.
            Column {
                visible: gr.isShortcut
                width: parent.width
                spacing: 4
                GlassField {
                    id: keys
                    width: parent.width
                    text: gr.row.shortcut
                    placeholderText: "Keys, e.g. ctrl+shift+s or alt+f4 — press Enter"
                    onAccepted: shortcutStatus.error = controller.setGestureShortcut(gr.row.id, text)
                }
                // A rejected chord shows why; with no keys set yet, nudge the user, because the
                // binding does nothing until then.
                Text {
                    id: shortcutStatus
                    property string error: ""
                    width: parent.width; wrapMode: Text.WordWrap
                    visible: text !== ""
                    text: error !== "" ? error
                          : gr.row.shortcut === "" ? "No keys set yet — this gesture does nothing until you add some."
                          : ""
                    color: error !== "" ? Theme.bad : Theme.warn
                    font.pixelSize: Theme.fontS
                }
            }
        }
    }

    // ---- The gesture trainer -----------------------------------------------------------------
    component Trainer: Rectangle {
        id: tr
        property int countdown: 0
        property string error: ""
        readonly property bool recording: controller.recordingState === "recording"
        readonly property bool busy: countdown > 0 || recording
        height: trCol.implicitHeight + 24
        radius: 12
        color: Theme.glass
        border.width: 1
        border.color: Theme.glassBorder

        function begin() {
            error = controller.checkRecording(nameField.text)
            if (error !== "") return
            countdown = 3
            tick.restart()
        }
        function cancel() {
            tick.stop()
            countdown = 0
            controller.cancelRecording()
        }

        Timer {
            id: tick
            interval: 1000; repeat: true
            onTriggered: {
                tr.countdown -= 1
                if (tr.countdown > 0) return
                stop()
                tr.error = controller.startRecording(nameField.text)
            }
        }
        Connections {
            target: controller
            function onRecordingChanged() {
                if (controller.recordingState === "done") nameField.text = ""
            }
        }

        Column {
            id: trCol
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
            spacing: 10

            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "Name a hand shape, press Record, then hold it steady in view. Gestura learns "
                      + "it from 40 frames, entirely on this PC — then pick its action above."
                color: Theme.subtext; font.pixelSize: Theme.fontS
            }
            Row {
                width: parent.width
                spacing: 8
                GlassField {
                    id: nameField
                    width: parent.width - recordBtn.width - 8
                    enabled: !tr.busy
                    placeholderText: "Gesture name, e.g. peace sign"
                    onAccepted: if (!tr.busy) tr.begin()
                }
                PillButton {
                    id: recordBtn
                    width: 110
                    height: 36
                    accentFill: !tr.busy
                    text: tr.busy ? "Cancel" : "● Record"
                    onClicked: tr.busy ? tr.cancel() : tr.begin()
                }
            }

            // Live status: countdown, progress, or the last result.
            Row {
                spacing: 8
                visible: tr.busy || tr.error !== "" || controller.recordingMessage !== ""
                Rectangle {
                    width: 9; height: 9; radius: 4.5
                    anchors.verticalCenter: parent.verticalCenter
                    color: controller.handPresent ? Theme.good : Theme.subtext
                }
                Text {
                    color: tr.error !== "" || controller.recordingState === "failed" ? Theme.bad
                           : controller.recordingState === "done" && !tr.busy ? Theme.good
                           : Theme.text
                    font.pixelSize: Theme.fontS
                    text: tr.error !== "" ? tr.error
                          : tr.countdown > 0 ? "Get your hand ready… " + tr.countdown
                          : tr.recording ? controller.recordingMessage + "  "
                                           + Math.round(controller.recordingProgress * 100) + "%"
                          : controller.recordingMessage
                }
            }
            Rectangle {
                visible: tr.recording
                width: parent.width; height: 6; radius: 3
                color: Theme.stroke
                Rectangle {
                    height: parent.height; radius: 3
                    width: parent.width * controller.recordingProgress
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.accent }
                        GradientStop { position: 1; color: Theme.good }
                    }
                    Behavior on width { NumberAnimation { duration: 90 } }
                }
            }
        }
    }

    // ---- Small styled controls ---------------------------------------------------------------
    component SectionLabel: Text {
        topPadding: 10
        color: Theme.accent2
        font.pixelSize: Theme.fontS; font.letterSpacing: 1.4
        font.capitalization: Font.AllUppercase
    }
}
