import QtQuick
import QtQuick.Controls.Basic
import "."

// Slide-in settings drawer with a live search filter and grouped, live-applied controls.
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
        width: Math.min(400, parent.width * 0.5)
        height: parent.height
        x: panel.open ? parent.width - width : parent.width
        Behavior on x { NumberAnimation { id: slideAnim; duration: 220; easing.type: Easing.OutCubic } }

        // Clicks on the sheet itself must not fall through to the scrim (which closes the panel).
        MouseArea { anchors.fill: parent }

        Column {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 16

            Row {
                width: parent.width
                Text { text: "Settings"; color: Theme.text; font.pixelSize: Theme.fontL
                       font.weight: Font.DemiBold; width: parent.width - 30 }
                Text {
                    text: "✕"; color: Theme.subtext; font.pixelSize: 16
                    MouseArea { anchors.fill: parent; anchors.margins: -8
                                cursorShape: Qt.PointingHandCursor; onClicked: panel.open = false }
                }
            }

            // Search box
            Rectangle {
                width: parent.width; height: 40; radius: 10
                color: Theme.glass; border.color: Theme.glassBorder; border.width: 1
                Row {
                    anchors.fill: parent; anchors.leftMargin: 12; spacing: 8
                    Text { text: "🔍"; color: Theme.subtext; anchors.verticalCenter: parent.verticalCenter }
                    TextInput {
                        id: search
                        width: parent.width - 40; anchors.verticalCenter: parent.verticalCenter
                        color: Theme.text; font.pixelSize: Theme.fontM; clip: true
                        Text { text: "Search settings…"; color: Theme.subtext
                               font.pixelSize: Theme.fontM; visible: !search.text }
                    }
                }
            }

            // Active profile
            Text { text: "PROFILE: " + controller.activeProfile.toUpperCase()
                   color: Theme.subtext; font.pixelSize: Theme.fontS; font.letterSpacing: 1.2 }

            Flickable {
                width: parent.width
                height: parent.height - y
                contentHeight: rows.height
                clip: true
                Column {
                    id: rows
                    width: parent.width
                    spacing: 6

                    SettingGroup { title: "Camera"; filter: search.text }
                    CameraPicker { filter: search.text }
                    SettingToggle { filter: search.text; label: "Show camera preview"
                                    path: "ui.show_camera_preview" }
                    SettingToggle { filter: search.text; label: "Mirror camera (selfie view)"
                                    path: "profile.camera.mirror" }

                    SettingGroup { title: "Cursor"; filter: search.text }
                    CalibrationRow { filter: search.text }
                    SettingRow { filter: search.text; label: "Smoothing (steadiness)"
                                 path: "profile.cursor.smoothing_min_cutoff"; minv: 0.3; maxv: 5; stepSize: 0.1 }
                    SettingRow { filter: search.text; label: "Responsiveness (less lag)"
                                 path: "profile.cursor.smoothing_beta"; minv: 0; maxv: 0.4; stepSize: 0.01 }
                    SettingRow { filter: search.text; label: "Dead zone"
                                 path: "profile.cursor.dead_zone"; minv: 0; maxv: 0.03; stepSize: 0.001 }
                    SettingRow { filter: search.text; label: "Active area margin (uncalibrated)"
                                 path: "profile.cursor.region_margin_x"; minv: 0; maxv: 0.35; stepSize: 0.01 }

                    SettingGroup { title: "Recognition"; filter: search.text }
                    SettingRow { filter: search.text; label: "Pinch sensitivity"
                                 path: "profile.thresholds.pinch_on"; minv: 0.2; maxv: 0.8; stepSize: 0.01 }
                    SettingRow { filter: search.text; label: "Pinch release"
                                 path: "profile.thresholds.pinch_off"; minv: 0.3; maxv: 1.0; stepSize: 0.01 }
                    SettingRow { filter: search.text; label: "Min hand confidence"
                                 path: "profile.thresholds.min_confidence"; minv: 0.3; maxv: 0.95; stepSize: 0.01 }
                    SettingRow { filter: search.text; label: "Hold-to-accept time"
                                 path: "profile.thresholds.stability_time"; minv: 0; maxv: 0.3; stepSize: 0.01; suffix: " s" }

                    SettingGroup { title: "Background & startup"; filter: search.text }
                    SettingToggle { filter: search.text; label: "Keep running in the tray when closed"
                                    path: "ui.close_to_tray" }
                    SettingToggle { filter: search.text; label: "Start with Windows"
                                    path: "ui.launch_on_startup"; available: controller.autostartSupported }
                    SettingToggle { filter: search.text; label: "Start minimized to the tray"
                                    path: "ui.start_minimized" }
                    HotkeyRow { filter: search.text }

                    SettingGroup { title: "Interface"; filter: search.text }
                    SettingToggle { filter: search.text; label: "Status overlay"
                                    path: "ui.show_overlay" }

                    // About footer — the last thing in the panel.
                    Column {
                        visible: search.text === ""
                        width: parent.width
                        topPadding: 22
                        bottomPadding: 12
                        spacing: 4
                        Rectangle { width: parent.width; height: 1; color: Theme.stroke }
                        Item { width: 1; height: 8 }
                        Text { text: "Gestura " + controller.appVersion; color: Theme.subtext
                               font.pixelSize: Theme.fontS }
                        Text { text: "Developed by " + controller.appAuthor; color: Theme.text
                               font.pixelSize: Theme.fontS; font.weight: Font.DemiBold }
                    }
                }
            }
        }
    }

    // Inline group header. The label sits inside an Item so the collapsing height doesn't feed
    // back into the Text's own implicitHeight (which was a height binding loop).
    component SettingGroup: Item {
        property string title: ""
        property string filter: ""
        visible: filter === ""
        width: parent ? parent.width : 300
        height: visible ? groupLabel.implicitHeight + 16 : 0
        Text {
            id: groupLabel
            y: 16
            text: parent.title.toUpperCase(); color: Theme.accent2
            font.pixelSize: Theme.fontS; font.letterSpacing: 1.4
        }
    }

    // Shared filter logic for the custom rows below.
    component FilteredRow: Item {
        property string label: ""
        property string filter: ""
        readonly property bool matches:
            filter === "" || label.toLowerCase().indexOf(filter.toLowerCase()) !== -1
        width: parent ? parent.width : 300
        visible: matches
    }

    // Which webcam to use. Switching reopens the camera in the background.
    component CameraPicker: FilteredRow {
        id: cp
        label: "Camera"
        height: matches ? 50 : 0
        Row {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            spacing: 8
            Text { text: cp.label; color: Theme.text; font.pixelSize: Theme.fontM
                   width: parent.width - camCombo.width - detect.width - 16
                   anchors.verticalCenter: parent.verticalCenter }
            GlassCombo {
                id: camCombo
                width: 130
                dimFirst: false
                anchors.verticalCenter: parent.verticalCenter
                model: controller.cameras.map(function (i) { return { label: "Camera " + (i + 1) } })
                textRole: "label"
                currentIndex: controller.cameras.indexOf(controller.cameraIndex)
                onActivated: function (i) { controller.setCamera(controller.cameras[i]) }
            }
            PillButton {
                id: detect
                width: 76; height: 32
                text: controller.probingCameras ? "..." : "Detect"
                anchors.verticalCenter: parent.verticalCenter
                onClicked: controller.refreshCameras()
            }
        }
    }

    // Fit the cursor's active area to the user's own reach.
    component CalibrationRow: FilteredRow {
        id: cal
        label: "Reach calibration"
        property string error: ""
        height: matches ? (error !== "" ? 76 : 58) : 0
        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            spacing: 4
            Row {
                width: parent.width
                spacing: 8
                Column {
                    width: parent.width - calBtn.width - resetBtn.width - 16
                    anchors.verticalCenter: parent.verticalCenter
                    Text { text: cal.label; color: Theme.text; font.pixelSize: Theme.fontM }
                    Text { text: controller.calibrated ? "Using your calibrated reach"
                                                       : "Using the default active area"
                           color: controller.calibrated ? Theme.good : Theme.subtext
                           font.pixelSize: Theme.fontS }
                }
                PillButton {
                    id: calBtn
                    width: 92; height: 32
                    accentFill: true
                    text: "Calibrate"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: {
                        cal.error = controller.startCalibration()
                        if (cal.error === "") panel.open = false   // let them see the camera
                    }
                }
                PillButton {
                    id: resetBtn
                    width: controller.calibrated ? 64 : 0
                    visible: controller.calibrated
                    height: 32
                    text: "Reset"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: controller.resetCalibration()
                }
            }
            Text { visible: cal.error !== ""; text: cal.error; color: Theme.bad
                   font.pixelSize: Theme.fontS; width: parent.width; wrapMode: Text.WordWrap }
        }
    }

    // The system-wide pause/resume hotkey.
    component HotkeyRow: FilteredRow {
        id: hk
        label: "Pause / resume hotkey"
        property string error: ""
        readonly property string shownError: error !== "" ? error : controller.hotkeyError
        height: matches ? (shownError !== "" ? 70 : 50) : 0
        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            spacing: 4
            Row {
                width: parent.width
                spacing: 8
                Text { text: hk.label; color: Theme.text; font.pixelSize: Theme.fontM
                       width: parent.width - keys.width - 8
                       anchors.verticalCenter: parent.verticalCenter }
                GlassField {
                    id: keys
                    width: 140
                    text: controller.pauseHotkey
                    placeholderText: "ctrl+alt+g"
                    onAccepted: hk.error = controller.setPauseHotkey(text)
                    onActiveFocusChanged: if (!activeFocus) text = controller.pauseHotkey
                }
            }
            Text { visible: hk.shownError !== ""; text: hk.shownError; color: Theme.bad
                   font.pixelSize: Theme.fontS; width: parent.width; wrapMode: Text.WordWrap }
        }
    }

    // Inline boolean toggle bound to a settings path
    component SettingToggle: Item {
        id: toggle
        property string label: ""
        property string path: ""
        property string filter: ""
        property bool available: true
        property bool value: false
        readonly property bool matches: available &&
            (filter === "" || label.toLowerCase().indexOf(filter.toLowerCase()) !== -1)
        width: parent ? parent.width : 300
        height: matches ? 44 : 0
        visible: matches
        Component.onCompleted: value = controller.getSetting(path) === true
        // The app can refuse a change (e.g. Windows startup unavailable): show the real value.
        Connections {
            target: controller
            function onSettingsChanged() { toggle.value = controller.getSetting(toggle.path) === true }
        }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            Text { text: toggle.label; color: Theme.text; font.pixelSize: Theme.fontM
                   width: parent.width - 52; anchors.verticalCenter: parent.verticalCenter }
            Rectangle {
                width: 44; height: 24; radius: 12
                color: toggle.value ? Theme.accent : Theme.stroke
                Behavior on color { ColorAnimation { duration: 120 } }
                Rectangle {
                    width: 18; height: 18; radius: 9; color: "white"
                    y: 3; x: toggle.value ? 23 : 3
                    Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                }
                MouseArea {
                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        toggle.value = !toggle.value
                        controller.setBool(toggle.path, toggle.value)
                    }
                }
            }
        }
    }
}
