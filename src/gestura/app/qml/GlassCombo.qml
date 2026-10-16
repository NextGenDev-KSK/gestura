import QtQuick
import QtQuick.Controls.Basic
import "."

// Drop-down in the glass style; the popup is themed to match.
ComboBox {
    id: cb
    // Grey out the first entry when it means "nothing chosen" (e.g. "Not bound").
    property bool dimFirst: true
    height: 36
    font.pixelSize: Theme.fontM
    background: Rectangle {
        radius: 10
        color: cb.hovered || cb.pressed ? Theme.glassStrong : Theme.glass
        border.width: 1
        border.color: cb.activeFocus || cb.popup.visible ? Theme.accent : Theme.glassBorder
        Behavior on color { ColorAnimation { duration: 120 } }
    }
    contentItem: Text {
        leftPadding: 12
        rightPadding: 28
        text: cb.displayText
        color: cb.dimFirst && cb.currentIndex <= 0 ? Theme.subtext : Theme.text
        font: cb.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: cb.width - width - 12
        y: (cb.height - height) / 2
        text: "▾"; color: Theme.subtext; font.pixelSize: Theme.fontM
    }
    delegate: ItemDelegate {
        id: item
        required property var modelData
        required property int index
        width: ListView.view ? ListView.view.width : cb.width
        height: 34
        highlighted: cb.highlightedIndex === index
        contentItem: Text {
            text: item.modelData.label
            color: item.index === cb.currentIndex ? Theme.accent : Theme.text
            font.pixelSize: Theme.fontM
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 8
            color: item.highlighted ? Theme.glassStrong : "transparent"
        }
    }
    popup: Popup {
        y: cb.height + 4
        width: cb.width
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 300)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: cb.popup.visible ? cb.delegateModel : null
            currentIndex: cb.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: 12
            color: Theme.dark ? "#1a2134" : "#ffffff"
            border.width: 1
            border.color: Theme.glassBorder
        }
    }
}
