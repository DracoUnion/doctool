#!/usr/bin/env python3
"""GGUF viewer: a PyQt6 GUI to inspect a GGUF model file.

Layout:
    - a disabled edit box showing the selected file path
    - an "Open..." button to pick a GGUF file
    - a two-column tree (name | value) showing the file's key/value
      metadata plus every tensor's name, shape and dtype (quantization
      type), grouped under section headers.

The file is parsed on a background QThread so the UI never freezes,
even for very large models (which have tens of thousands of tensors).
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gguf import GGUFReader, GGUFValueType


# Scalar GGUF value types that have a clean string representation.
_SCALAR_TYPES = {
    GGUFValueType.UINT8, GGUFValueType.INT8,
    GGUFValueType.UINT16, GGUFValueType.INT16,
    GGUFValueType.UINT32, GGUFValueType.INT32,
    GGUFValueType.UINT64, GGUFValueType.INT64,
    GGUFValueType.FLOAT32, GGUFValueType.FLOAT64,
    GGUFValueType.BOOL,
}

# Structural pseudo-fields that we surface in the file header instead
# of listing them again in the metadata section.
_PSEUDO_FIELDS = ("GGUF.version", "GGUF.tensor_count", "GGUF.kv_count")


# ----------------------------------------------------------------------
# Helper builders (pure, no Qt widgets) — keep the worker thread light.
# ----------------------------------------------------------------------
def _build_header_rows(reader: GGUFReader, path: str) -> list[tuple[str, str]]:
    """Rows for the top-level file summary."""
    file_size = os.path.getsize(path)
    version = reader.fields.get("GGUF.version")
    kv_count = reader.fields.get("GGUF.kv_count")
    tensor_count = reader.fields.get("GGUF.tensor_count")
    return [
        ("File", os.path.basename(path)),
        ("Version", str(version.contents()) if version else "?"),
        ("File size", f"{file_size} bytes ({file_size / (1024 * 1024):.2f} MiB)"),
        ("Endianness", reader.endianess.name + (" (swapped)" if reader.byte_order == "S" else "")),
        ("Alignment", str(reader.alignment)),
        ("KV pairs", str(kv_count.contents()) if kv_count is not None else "?"),
        ("Tensors", str(tensor_count.contents()) if tensor_count is not None else "?"),
    ]


def _build_kv_rows(reader: GGUFReader) -> list[tuple[str, str]]:
    """One (key, value) row per non-structural metadata field."""
    rows: list[tuple[str, str]] = []
    for field in reader.fields.values():
        if field.name in _PSEUDO_FIELDS:
            continue
        rows.append((field.name, _format_field_value(field)))
    return rows


def _build_tensor_row(tensor_name: str, tensor) -> list[tuple[str, str]]:
    """Rows describing a single tensor."""
    shape = [int(d) for d in tensor.shape]
    while len(shape) < 4:
        shape = [1] + shape
    pretty_dims = " x ".join(str(d) for d in shape)
    return [
        ("Shape", pretty_dims),
        ("Dtype (quant)", tensor.tensor_type.name),
        ("Elements", str(tensor.n_elements)),
        ("Bytes", str(tensor.n_bytes)),
        ("Data offset (hex)", hex(tensor.data_offset)),
    ]


def _format_field_value(field) -> str:
    """Render a ReaderField's value as compact, human-readable text."""
    if not field.types:
        return "N/A"
    main_type = field.types[0]
    if main_type == GGUFValueType.ARRAY:
        depth = len(field.types) - 1
        inner = field.types[-1].name if depth > 1 else "?"
        pretty_type = "[" * depth + inner + "]" * depth
        try:
            contents = field.contents()
            if isinstance(contents, list):
                if len(contents) <= 8:
                    value_repr = ", ".join(str(c) for c in contents)
                else:
                    head = ", ".join(str(c) for c in contents[:8])
                    value_repr = f"{head}, ... ({len(contents)} total)"
            else:
                value_repr = str(contents)
        except Exception:  # noqa: BLE001
            value_repr = "<unreadable>"
        return f"{pretty_type}: {value_repr}"

    if main_type == GGUFValueType.STRING:
        return repr(field.contents())
    if main_type in _SCALAR_TYPES:
        return str(field.contents())
    return f"{field.types[-1].name}: <value>"


# ----------------------------------------------------------------------
# Background worker: parse the GGUF file off the UI thread.
# ----------------------------------------------------------------------
class LoadThread(QThread):
    """Parses a GGUF file and reports either its rows or the error text."""

    # (status, path, rows, error) where status in {"ok", "error"}
    finished_ok = pyqtSignal(str, object)   # path, list of (section, rows)
    failed = pyqtSignal(str, str)           # path, error message

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path

    def run(self) -> None:  # runs in the worker thread
        try:
            reader = GGUFReader(self.path, "r")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.path, str(exc))
            return

        try:
            rows: list[tuple[str, list[tuple[str, str]]]] = [
                ("File", _build_header_rows(reader, self.path)),
            ]
            kv_rows = _build_kv_rows(reader)
            rows.append((f"Metadata ({len(kv_rows)} key/value pairs)", kv_rows))
            rows.append((f"Tensors ({len(reader.tensors)})", None))
            for tensor in reader.tensors:
                rows.append((tensor.name, _build_tensor_row(tensor.name, tensor)))
            self.finished_ok.emit(self.path, rows)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.path, str(exc))


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------
class GGUFViewer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GGUF Viewer")
        self.resize(900, 640)
        self._thread: LoadThread | None = None

        layout = QVBoxLayout(self)

        # Top row: disabled edit box + button
        top = QHBoxLayout()

        self.path_label = QLabel("No file selected")
        self.path_label.setWordWrap(True)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setDisabled(True)
        self.path_edit.setPlaceholderText("File path will appear here")

        self.open_button = QPushButton("Open GGUF...")
        self.open_button.clicked.connect(self._open_file)

        top.addWidget(self.path_label, 0)
        top.addWidget(self.path_edit, 1)
        top.addWidget(self.open_button, 0)
        layout.addLayout(top)

        # Two-column tree: Name | Value
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tree, 1)

        self._set_status("Ready. Click “Open GGUF...” to choose a file.")

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------
    def _set_status(self, text: str) -> None:
        """Show a single informational row in place of data."""
        self.tree.clear()
        item = QTreeWidgetItem([text, ""])
        item.setForeground(0, QColor("gray"))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.tree.addTopLevelItem(item)

    def _insert_section(self, title: str, rows: list[tuple[str, str]] | None) -> QTreeWidgetItem:
        """Insert a top-level section item with optional (key, value) child rows."""
        section = QTreeWidgetItem([title, ""])
        section.setForeground(0, QColor("gray"))
        if rows is not None:
            for key, value in rows:
                child = QTreeWidgetItem([key, value])
                section.addChild(child)
        self.tree.addTopLevelItem(section)
        return section

    def _populate_tree(self, rows: list[tuple[str, list[tuple[str, str]]]]) -> None:
        self.tree.clear()
        for section_title, section_rows in rows:
            self._insert_section(section_title, section_rows)
        # Keep tensor leaf rows collapsed under their section headers for large files.
        self.tree.expandAll()
        self.tree.scrollToItem(self.tree.topLevelItem(0))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a GGUF file",
            "",
            "GGUF files (*.gguf);;All files (*)",
        )
        if not path:
            return

        self.path_label.setText(os.path.basename(path))
        self.path_edit.setText(path)
        self._set_status(f"Loading {os.path.basename(path)} ...")
        self.open_button.setEnabled(False)

        self._thread = LoadThread(path, self)
        self._thread.finished_ok.connect(self._on_loaded)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _on_loaded(self, path: str, rows: list[tuple[str, list[tuple[str, str]]]]) -> None:
        self.open_button.setEnabled(True)
        self._populate_tree(rows)

    def _on_failed(self, path: str, error: str) -> None:
        self.open_button.setEnabled(True)
        self._set_status(f"Could not open GGUF file: {error}")
        QMessageBox.critical(self, "Error", f"Could not open GGUF file:\n{error}")

    def _show_context_menu(self, pos) -> None:
        """Small right-click menu: expand/collapse/copy value of the selected row."""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        expand = menu.addAction("Expand all children")
        collapse = menu.addAction("Collapse all children")
        menu.addSeparator()
        copy_key = menu.addAction("Copy name")
        copy_value = menu.addAction("Copy value")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if action is expand:
            self._walk_expand(item, True)
        elif action is collapse:
            self._walk_expand(item, False)
        elif action is copy_key:
            QApplication.clipboard().setText(item.text(0))
        elif action is copy_value:
            QApplication.clipboard().setText(item.text(1))

    def _walk_expand(self, item: QTreeWidgetItem, expand: bool) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setExpanded(expand)
            self._walk_expand(child, expand)

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = GGUFViewer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
