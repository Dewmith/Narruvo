from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget


class LibraryView(QWidget):
    open_requested = Signal(str)
    remove_requested = Signal(str)
    locate_requested = Signal(str)
    import_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        eyebrow = QLabel("A LITTLE TIME, A GOOD BOOK")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Your listening library")
        title.setObjectName("hero")
        layout.addWidget(title)
        subtitle = QLabel("Pick up where you left off. Your PDFs stay on your computer.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        row = QHBoxLayout()
        self.count = QLabel("No documents yet")
        self.count.setObjectName("muted")
        row.addWidget(self.count)
        row.addStretch()
        button = QPushButton("Import PDF…")
        button.setObjectName("accent")
        button.clicked.connect(self.import_requested)
        row.addWidget(button)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setSpacing(5)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(lambda item: self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list, 1)
        self.empty = QLabel("A quieter way to read.\n\nImport a text-based PDF to see its pages and listen with natural, offline voices.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setObjectName("muted")
        layout.addWidget(self.empty, 1)
        footer = QHBoxLayout()
        self.open_button = QPushButton("Open selected")
        self.open_button.clicked.connect(self._open)
        self.remove_button = QPushButton("Remove from library")
        self.remove_button.clicked.connect(self._remove)
        self.list.itemSelectionChanged.connect(self._selection)
        footer.addWidget(self.open_button)
        footer.addWidget(self.remove_button)
        footer.addStretch()
        layout.addLayout(footer)
        self._selection()

    def update_documents(self, documents) -> None:
        selected = self.list.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.list.clear()
        for document in documents:
            try:
                opened = datetime.fromisoformat(document.last_opened).strftime("%d %b %Y")
            except ValueError:
                opened = "Recently"
            state = "Finished" if document.progress.completed else f"Resume on page {document.progress.view_page + 1}"
            item = QListWidgetItem(f"{document.title}\n{document.page_count} pages  ·  {state}  ·  Opened {opened}")
            item.setData(Qt.ItemDataRole.UserRole, document.document_id)
            item.setToolTip(document.path)
            self.list.addItem(item)
            if document.document_id == selected_id:
                self.list.setCurrentItem(item)
        self.count.setText(f"{len(documents)} document{'s' if len(documents) != 1 else ''} · Double-click to open")
        self.empty.setVisible(not documents)
        self.list.setVisible(bool(documents))

    def _selection(self) -> None:
        has_selection = self.list.currentItem() is not None
        self.open_button.setEnabled(has_selection)
        self.remove_button.setEnabled(has_selection)

    def _open(self) -> None:
        if item := self.list.currentItem():
            self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _remove(self) -> None:
        if item := self.list.currentItem():
            self.remove_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _menu(self, point) -> None:
        item = self.list.itemAt(point)
        if not item:
            return
        document_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.open_requested.emit(document_id))
        menu.addAction("Locate PDF…", lambda: self.locate_requested.emit(document_id))
        menu.addAction("Remove from library", lambda: self.remove_requested.emit(document_id))
        menu.exec(self.list.mapToGlobal(point))
