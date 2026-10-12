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

                    SettingGroup { title: "Cursor"; filter: search.text }
                    SettingRow { filter: search.text; label: "Smoothing (steadiness)"
                                 path: "profile.cursor.smoothing_min_cutoff"; minv: 0.3; maxv: 5; stepSize: 0.1 }
                    SettingRow { filter: search.text; label: "Responsiveness (less lag)"
                                 path: "profile.cursor.smoothing_beta"; minv: 0; maxv: 0.4; stepSize: 0.01 }
                    SettingRow { filter: search.text; label: "Dead zone"
                                 path: "profile.cursor.dead_zone"; minv: 0; maxv: 0.03; stepSize: 0.001 }
                    SettingRow { filter: search.text; label: "Active area margin"
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

                    SettingGroup { title: "Interface"; filter: search.text }
                    SettingToggle { filter: search.text; label: "Status overlay"
                                    path: "ui.show_overlay" }
                    SettingToggle { filter: search.text; label: "Mirror camera (selfie view)"
                                    path: "profile.camera.mirror" }
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

    // Inline boolean toggle bound to a settings path
    component SettingToggle: Item {
        id: toggle
        property string label: ""
        property string path: ""
        property string filter: ""
        property bool value: false
        readonly property bool matches:
            filter === "" || label.toLowerCase().indexOf(filter.toLowerCase()) !== -1
        width: parent ? parent.width : 300
        height: matches ? 44 : 0
        visible: matches
        Component.onCompleted: value = controller.getSetting(path) === true
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
