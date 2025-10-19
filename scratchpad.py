import sys
import os
import requests
import validators
import chardet
import importlib.util
from functools import partial
from PyQt5.QtWidgets import (QApplication, QMainWindow, QAction,
                             QFileDialog, QMessageBox, QStatusBar, QDialog, QInputDialog,
                             QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSettings, QSignalBlocker
from PyQt5.QtGui import QIcon, QFont, QFontDatabase, QTextDocument
from PyQt5.Qsci import QsciScintilla, QsciScintillaBase



def detect_newline(sample: bytes) -> str:
    crlf = sample.count(b"\r\n")
    tmp = sample.replace(b"\r\n", b"")
    cr = tmp.count(b"\r")
    lf = tmp.count(b"\n")
    if crlf >= cr and crlf >= lf and crlf > 0:
        return "\r\n"
    if lf >= cr and lf > 0:
        return "\n"
    if cr > 0:
        return "\r"
    return "\r\n"



class FileHandler(QThread):
    file_content_loaded = pyqtSignal(str, str, object, object)
    file_load_started = pyqtSignal(str, object, object)
    file_chunk_loaded = pyqtSignal(str, str, bool)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
            detector = chardet.universaldetector.UniversalDetector()
            try:
                with open(self.file_path, 'rb') as file:
                    while chunk := file.read(1024):
                        detector.feed(chunk)
                        if detector.done:
                            break
                    detector.close()
                encoding = detector.result['encoding'] or 'utf-8'
                with open(self.file_path, 'rb') as fb:
                    sample = fb.read(64 * 1024)
                newline = detect_newline(sample)
                self.file_load_started.emit(self.file_path, encoding, newline)
                chunk_size = 1024 * 1024
                with open(self.file_path, 'r', encoding=encoding, errors='replace', newline=None) as file:
                    while True:
                        chunk = file.read(chunk_size)
                        if not chunk:
                            break
                        self.file_chunk_loaded.emit(self.file_path, chunk, False)
                self.file_chunk_loaded.emit(self.file_path, '', True)
            except Exception as e:
                self.file_content_loaded.emit(self.file_path, f"Error reading file: {e}", None, None)



class WebFetcher(QThread):
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, url, max_bytes=1_000_000, timeout=(5, 10), allow_redirects=False):
        super().__init__()
        self.url = url
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.allow_redirects = allow_redirects

    def run(self):
        try:
            headers = {
                'User-Agent': 'Scratchpad/1.0',
                'Accept': 'text/*, application/json'
            }
            with requests.get(
                self.url,
                timeout=self.timeout,
                allow_redirects=self.allow_redirects,
                stream=True,
                headers=headers
            ) as resp:
                if 300 <= resp.status_code < 400:
                    raise ValueError(f"Redirects not allowed (status {resp.status_code})")
                resp.raise_for_status()
                content_type = (resp.headers.get('Content-Type') or '').lower()
                if not (content_type.startswith('text/') or 'application/json' in content_type):
                    raise ValueError(f"Non-text content type: {content_type or 'unknown'}")
                cl = resp.headers.get('Content-Length')
                size_hint = None
                if cl is not None:
                    try:
                        size_hint = int(cl)
                    except (TypeError, ValueError):
                        size_hint = None
                if size_hint is not None and size_hint > self.max_bytes:
                    raise ValueError(f"Response too large (> {self.max_bytes} bytes)")
                chunks = []
                total = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ValueError(f"Response exceeded size limit ({self.max_bytes} bytes)")
                    chunks.append(chunk)
                data = b''.join(chunks)
                encoding = resp.encoding
                if not encoding:
                    detected = chardet.detect(data)
                    encoding = detected.get('encoding') or 'utf-8'
                text = data.decode(encoding, errors='replace')
                self.completed.emit(text)
        except Exception as e:
            self.failed.emit(f"Failed to fetch content: {e}")



def load_icon(icon_name):
    icon_path = os.path.join(os.path.dirname(__file__), icon_name)
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, icon_name)
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    return None



def load_plugins(app_context):
    user_home = os.path.expanduser("~")
    plugins_dir = os.path.join(user_home, "spplugins")
    os.makedirs(plugins_dir, exist_ok=True)
    loaded_plugins = []
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            plugin_path = os.path.join(plugins_dir, filename)
            mod_name = os.path.splitext(filename)[0]
            spec = importlib.util.spec_from_file_location(mod_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin(app_context)
                    loaded_plugins.append(mod_name)
                    print(f"Plugin '{mod_name}' loaded successfully from {plugins_dir}")
            except Exception as e:
                print(f"Failed to load plugin '{filename}' from {plugins_dir}: {e}")
    return loaded_plugins



def loadStyle():
    user_css_path = os.path.join(os.path.expanduser("~"), "spstyle.css")
    stylesheet = None
    if os.path.exists(user_css_path):
        try:
            with open(user_css_path, 'r') as css_file:
                stylesheet = css_file.read()
            print(f"Loaded user CSS style from: {user_css_path}")
        except Exception as e:
            print(f"Error loading user CSS: {e}")
    else:
        css_file_path = os.path.join(os.path.dirname(__file__), 'style.css')
        if getattr(sys, 'frozen', False):
            css_file_path = os.path.join(sys._MEIPASS, 'style.css')
        try:
            with open(css_file_path, 'r') as css_file:
                stylesheet = css_file.read()
        except FileNotFoundError:
            print(f"Default CSS file not found: {css_file_path}")
    if stylesheet:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            print("No QApplication instance found. Stylesheet not applied.")



def get_preferred_font():
    db = QFontDatabase()
    if "Cascadia Code" in db.families():
        family = "Cascadia Code"
    elif "Courier New" in db.families():
        family = "Courier New"
    elif "Courier" in db.families():
        family = "Courier"
    else:
        fallback = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if fallback.pointSize() <= 0:
            fallback.setPointSize(10)
        return fallback
    return QFont(family, 10)



class FindReplaceDialog(QDialog):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setWindowTitle("Find and Replace")
        self.setWindowIcon(load_icon('scratchpad.png'))
        self.layout = QVBoxLayout(self)
        self.find_label = QLabel("Find:")
        self.find_input = QLineEdit(self)
        self.layout.addWidget(self.find_label)
        self.layout.addWidget(self.find_input)
        self.replace_label = QLabel("Replace with:")
        self.replace_input = QLineEdit(self)
        self.layout.addWidget(self.replace_label)
        self.layout.addWidget(self.replace_input)
        self.button_layout = QHBoxLayout()
        self.find_button = QPushButton("Find Next", self)
        self.replace_button = QPushButton("Replace", self)
        self.replace_all_button = QPushButton("Replace All", self)
        self.button_layout.addWidget(self.find_button)
        self.button_layout.addWidget(self.replace_button)
        self.button_layout.addWidget(self.replace_all_button)
        self.layout.addLayout(self.button_layout)
        self.find_button.clicked.connect(self.find_next)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.setLayout(self.layout)
        self.current_index = 0

    def find_next(self):
        text_to_find = self.find_input.text().strip()
        if text_to_find:
            options = QTextDocument.FindFlags()
            found = self.text_edit.find(text_to_find, options)
            if not found:
                QMessageBox.information(self, "Not Found", "No more occurrences found.")
        else:
            QMessageBox.warning(self, "Empty Search", "Please enter text to find.")

    def replace(self):
        text_to_find = self.find_input.text()
        text_to_replace = self.replace_input.text()
        if text_to_find and text_to_replace:
            editor = self.text_edit
            found = editor.findFirst(text_to_find, False, False, False, True, True)
            if found:
                editor.replaceSelectedText(text_to_replace)

    def replace_all(self):
        text_to_find = self.find_input.text()
        text_to_replace = self.replace_input.text()
        if text_to_find and text_to_replace:
            editor = self.text_edit
            editor.setCursorPosition(0, 0)
            replaced = 0
            if editor.findFirst(text_to_find, False, False, False, True, True):
                while True:
                    editor.replaceSelectedText(text_to_replace)
                    replaced += 1
                    if not getattr(editor, 'findNext')():
                        break
            QMessageBox.information(self, "Replace All", f"Replaced {replaced} occurrence(s).")



class ImportFromWebDialog(QDialog):
    def __init__(self, text_edit, app_context=None):
        super().__init__()
        self.text_edit = text_edit
        self.app_context = app_context
        self.setWindowTitle("Import From Web")
        self.setWindowIcon(load_icon('scratchpad.png'))
        self.layout = QVBoxLayout(self)
        self.url_label = QLabel("Enter URL:")
        self.url_input = QLineEdit(self)
        self.layout.addWidget(self.url_label)
        self.layout.addWidget(self.url_input)
        self.fetch_button = QPushButton("Fetch", self)
        self.layout.addWidget(self.fetch_button)
        self.fetch_button.clicked.connect(self.fetch_from_web)
        self.setLayout(self.layout)
        self._fetcher = None

    def fetch_from_web(self):
        url = self.url_input.text().strip()
        if not self.is_valid_url(url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid HTTPS URL.")
            return
        if self._fetcher and self._fetcher.isRunning():
            QMessageBox.information(self, "In Progress", "A fetch is already in progress.")
            return
        self.fetch_button.setEnabled(False)
        self._fetcher = WebFetcher(url)
        self._fetcher.completed.connect(self._on_fetch_completed)
        self._fetcher.failed.connect(self._on_fetch_failed)
        self._fetcher.start()

    def _on_fetch_completed(self, text):
        try:
            self.text_edit.setPlainText(text)
            self.accept()
        finally:
            self.fetch_button.setEnabled(True)
            if self._fetcher:
                self._fetcher.deleteLater()
                self._fetcher = None

    def _on_fetch_failed(self, error_message):
        try:
            QMessageBox.critical(self, "Error", error_message)
        finally:
            self.fetch_button.setEnabled(True)
            if self._fetcher:
                self._fetcher.deleteLater()
                self._fetcher = None

    def is_valid_url(self, url):
        return validators.url(url) and url.startswith("https://")



class UnsavedWorkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("Unsaved Changes")
        self.setWindowIcon(load_icon('scratchpad.png'))
        self.layout = QVBoxLayout(self)
        self.message_label = QLabel("You have unsaved changes. What would you like to do?")
        self.layout.addWidget(self.message_label)
        self.button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Changes", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.discard_button = QPushButton("Discard Changes", self)
        self.button_layout.addWidget(self.save_button)
        self.button_layout.addWidget(self.cancel_button)
        self.button_layout.addWidget(self.discard_button)
        self.layout.addLayout(self.button_layout)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        self.discard_button.clicked.connect(self.discard_changes)
        self.setLayout(self.layout)

    def discard_changes(self):
        self.done(2)



class Editor(QsciScintilla):
    zoomChanged = pyqtSignal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preferred_font = get_preferred_font()
        self.setFont(self.preferred_font)
        self.setMarginsFont(self.preferred_font)
        self.setMarginWidth(0, 0)
        self.setMarginLineNumbers(1, False)
        self.setMarginWidth(1, 0)
        self.setWrapMode(QsciScintilla.WrapNone)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.adjust_scroll_bar_policy()
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)
        self.setIndentationGuides(False)
        self.setTabWidth(4)
        self.setIndentationsUseTabs(False)
        self.setEolMode(QsciScintilla.EolWindows)
        self._zoom = 0
        self.setUtf8(True) if hasattr(self, 'setUtf8') else None

    def append_text(self, text: str):
        try:
            data = text.encode('utf-8', errors='replace')
            self.SendScintilla(QsciScintillaBase.SCI_APPENDTEXT, len(data), data)
        except Exception:
            self.SendScintilla(QsciScintillaBase.SCI_DOCUMENTEND)
            try:
                self.insert(text)
            except Exception:
                self.setText(self.text() + text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_scroll_bar_policy()

    def setPlainText(self, text):
        super().setText(text)

    def toPlainText(self):
        return super().text()

    def zoomTo(self, size):
        super().zoomTo(size)
        try:
            size = int(size)
        except Exception:
            pass
        if size != getattr(self, '_zoom', None):
            self._zoom = size
            self.zoomChanged.emit(size)

    def zoomIn(self):
        super().zoomIn()
        z = int(self.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
        if z != self._zoom:
            self._zoom = z
            self.zoomChanged.emit(z)

    def zoomOut(self):
        super().zoomOut()
        z = int(self.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
        if z != self._zoom:
            self._zoom = z
            self.zoomChanged.emit(z)

    def find(self, text, options):
        case_sensitive = bool(options & QTextDocument.FindCaseSensitively)
        backward = bool(options & QTextDocument.FindBackward)
        whole_word = bool(options & QTextDocument.FindWholeWords)
        return self.findFirst(text, False, case_sensitive, whole_word, True, not backward)

    def textCursor(self):
        line, index = self.getCursorPosition()
        class CursorWrapper:
            def __init__(self, line, index):
                self._line = line
                self._index = index
            def blockNumber(self):
                return self._line
            def columnNumber(self):
                return self._index
        return CursorWrapper(line, index)

    def adjust_scroll_bar_policy(self):
        text = self.text()
        if not text:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            return
        fm = self.fontMetrics()
        max_width = max(fm.horizontalAdvance(line) for line in text.split('\n'))
        if max_width > self.viewport().width():
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        super().wheelEvent(event)
        if ctrl:
            z = int(self.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
            if z != self._zoom:
                self._zoom = z
                self.zoomChanged.emit(z)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.modifiers() & Qt.ControlModifier:
            z = int(self.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
            if z != self._zoom:
                self._zoom = z
                self.zoomChanged.emit(z)



class Scratchpad(QMainWindow):
    def __init__(self, file_to_open=None):
        super().__init__()
        self.current_file = file_to_open
        self.file_handler = None
        self._open_generation = 0
        self.unsaved_changes = False
        self.loadRecentFiles()
        self.initUI()
        if file_to_open:
            self.load_file_on_startup(file_to_open)
        self.app_context = {"main_window": self}
        self.plugins = load_plugins(self.app_context)

    def _start_file_load(self, file_path):
        self.current_file = file_path
        self._open_generation += 1
        gen = self._open_generation

        if self.file_handler is not None:
            try:
                self.file_handler.file_content_loaded.disconnect()
            except Exception:
                pass

        handler = FileHandler(file_path)
        handler.file_load_started.connect(lambda path, encoding, newline, gen=gen: self._on_file_load_started(gen, path, encoding, newline))
        handler.file_chunk_loaded.connect(lambda path, chunk, is_last, gen=gen: self._on_file_chunk_loaded(gen, path, chunk, is_last))
        handler.file_content_loaded.connect(lambda path, content, encoding, newline, gen=gen: self._on_file_content_loaded(gen, path, content, encoding, newline))
        handler.finished.connect(handler.deleteLater)
        handler.finished.connect(partial(self._on_handler_finished, handler))
        try:
            handler.destroyed.connect(partial(self._on_handler_destroyed, handler))
        except Exception:
            pass
        handler.start()
        self.file_handler = handler

    def load_file_on_startup(self, file_path):
        if os.path.exists(file_path):
            self._start_file_load(file_path)
        else:
            QMessageBox.critical(self, "Error", f"File does not exist: {file_path}")

    def closeEvent(self, event):
        if self.unsaved_changes:
            dialog = UnsavedWorkDialog(self)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                success = self.saveFile()
                if success:
                    self._safe_wait_for_handler()
                    event.accept()
                else:
                    event.ignore()
            elif result == QDialog.Rejected:
                event.ignore()
            elif result == 2:
                self._safe_wait_for_handler()
                event.accept()
            else:
                self._safe_wait_for_handler()
                event.accept()
        else:
            self._safe_wait_for_handler()
            event.accept()

    def initUI(self):
        self.setWindowTitle('Scratchpad - Unnamed')
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(load_icon('scratchpad.png'))
        self.textEdit = Editor(self)
        self.setCentralWidget(self.textEdit)
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        self.line = 1
        self.column = 1
        self.char_count = 0
        self.encoding = "UTF-8"
        self.newline = "\r\n"
        wrapEnabled = self.settings.value("wordWrap", False, type=bool)
        self.textEdit.setWrapMode(QsciScintilla.WrapWord if wrapEnabled else QsciScintilla.WrapNone)
        self.zoom_level = self.settings.value("view/zoom", 0, type=int)
        try:
            self.textEdit.zoomTo(int(self.zoom_level))
        except Exception:
            self.zoom_level = 0
            self.textEdit.zoomTo(0)
        self.textEdit.cursorPositionChanged.connect(self.updateStatusBar)
        self.textEdit.zoomChanged.connect(self._on_zoom_changed)
        self.createMenu()
        self.textEdit.textChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        self.unsaved_changes = True

    def createMenu(self):
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        self.createFileActions(fileMenu)
        editMenu = menubar.addMenu('&Edit')
        self.createEditActions(editMenu)
        viewMenu = menubar.addMenu('&View')
        self.createViewActions(viewMenu)

    def createFileActions(self, menu):
        self.actions = {}
        newAction = QAction('New', self)
        newAction.setShortcut('Ctrl+N')
        newAction.triggered.connect(self.newFile)
        menu.addAction(newAction)
        self.actions['new'] = newAction
        openAction = QAction('Open...', self)
        openAction.setShortcut('Ctrl+O')
        openAction.triggered.connect(self.openFile)
        menu.addAction(openAction)
        self.actions['open'] = openAction
        saveAction = QAction('Save', self)
        saveAction.setShortcut('Ctrl+S')
        saveAction.triggered.connect(self.saveFile)
        menu.addAction(saveAction)
        self.actions['save'] = saveAction
        saveAsAction = QAction('Save As...', self)
        saveAsAction.setShortcut('Ctrl+Shift+S')
        saveAsAction.triggered.connect(self.saveFileAs)
        menu.addAction(saveAsAction)
        self.actions['saveas'] = saveAsAction
        importFromWebAction = QAction('Import From Web...', self)
        importFromWebAction.setShortcut('Ctrl+I')
        importFromWebAction.triggered.connect(self.importFromWeb)
        menu.addAction(importFromWebAction)
        self.actions['importfromweb'] = importFromWebAction
        exitAction = QAction('Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.triggered.connect(self.close)
        menu.addAction(exitAction)
        self.actions['exit'] = exitAction
        menu.addSeparator()
        self.recentFilesMenu = menu.addMenu('Recently Opened Files')
        self.recentFilesMenu.aboutToShow.connect(self.updateRecentFilesMenu)
        self.updateRecentFilesMenu()
        
    def createEditActions(self, menu):
        undoAction = QAction('Undo', self)
        undoAction.setShortcut('Ctrl+Z')
        undoAction.triggered.connect(self.textEdit.undo)
        menu.addAction(undoAction)
        self.actions['undo'] = undoAction
        redoAction = QAction('Redo', self)
        if sys.platform != 'darwin':
            redoAction.setShortcuts(['Ctrl+Y', 'Ctrl+Shift+Z'])
        else:
            redoAction.setShortcuts(['Ctrl+Shift+Z', 'Ctrl+Y'])
        redoAction.triggered.connect(self.textEdit.redo)
        menu.addAction(redoAction)
        self.actions['redo'] = redoAction
        cutAction = QAction('Cut', self)
        cutAction.setShortcut('Ctrl+X')
        cutAction.triggered.connect(self.textEdit.cut)
        menu.addAction(cutAction)
        self.actions['cut'] = cutAction
        copyAction = QAction('Copy', self)
        copyAction.setShortcut('Ctrl+C')
        copyAction.triggered.connect(self.textEdit.copy)
        menu.addAction(copyAction)
        self.actions['copy'] = copyAction
        pasteAction = QAction('Paste', self)
        pasteAction.setShortcut('Ctrl+V')
        pasteAction.triggered.connect(self.textEdit.paste)
        menu.addAction(pasteAction)
        self.actions['paste'] = pasteAction
        selectAllAction = QAction('Select All', self)
        selectAllAction.setShortcut('Ctrl+A')
        selectAllAction.triggered.connect(self.textEdit.selectAll)
        menu.addAction(selectAllAction)
        self.actions['selectall'] = selectAllAction
        findReplaceAction = QAction('Find and Replace...', self)
        findReplaceAction.triggered.connect(self.openFindReplaceDialog)
        findReplaceAction.setShortcut('Ctrl+F')
        menu.addAction(findReplaceAction)
        self.actions['findreplace'] = findReplaceAction

    def createViewActions(self, menu):
        wrapEnabled = self.settings.value("wordWrap", False, type=bool)
        self.textEdit.setWrapMode(QsciScintilla.WrapWord if wrapEnabled else QsciScintilla.WrapNone)
        wordWrapAction = QAction('Word Wrap', self)
        wordWrapAction.setShortcut('Ctrl+W')
        wordWrapAction.setCheckable(True)
        wordWrapAction.setChecked(wrapEnabled)
        wordWrapAction.toggled.connect(lambda checked: (self.textEdit.setWrapMode(QsciScintilla.WrapWord if checked else QsciScintilla.WrapNone), self.settings.setValue("wordWrap", checked)))
        menu.addAction(wordWrapAction)
        self.actions['wordwrap'] = wordWrapAction
        zoomInAction = QAction('Zoom In', self)
        zoomInAction.setShortcut('Ctrl+=')
        zoomInAction.triggered.connect(lambda: self._zoom_delta(1))
        menu.addAction(zoomInAction)
        self.actions['zoomin'] = zoomInAction
        zoomOutAction = QAction('Zoom Out', self)
        zoomOutAction.setShortcut('Ctrl+-')
        zoomOutAction.triggered.connect(lambda: self._zoom_delta(-1))
        menu.addAction(zoomOutAction)
        self.actions['zoomout'] = zoomOutAction
        resetZoomAction = QAction('Reset Zoom', self)
        resetZoomAction.setShortcut('Ctrl+0')
        resetZoomAction.triggered.connect(lambda: self._set_zoom(0))
        menu.addAction(resetZoomAction)
        self.actions['resetzoom'] = resetZoomAction

    def _safe_wait_for_handler(self, timeout_ms=None):
        handler = getattr(self, 'file_handler', None)
        if not handler:
            return
        try:
            running = handler.isRunning()
        except RuntimeError:
            self.file_handler = None
            return
        if running:
            try:
                if timeout_ms is None:
                    handler.wait()
                else:
                    handler.wait(timeout_ms)
            except RuntimeError:
                self.file_handler = None

    def _on_handler_finished(self, handler_obj):
        if getattr(self, 'file_handler', None) is handler_obj:
            self.file_handler = None

    def _on_handler_destroyed(self, handler_obj, destroyed_obj=None):
        if getattr(self, 'file_handler', None) is handler_obj:
            self.file_handler = None

    def _zoom_delta(self, delta):
        try:
            current = int(getattr(self, 'zoom_level', 0))
        except Exception:
            current = 0
        new_level = current + int(delta)
        new_level = max(-10, min(20, new_level))
        self.textEdit.zoomTo(new_level)
        actual = int(self.textEdit.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
        self.zoom_level = actual
        self.settings.setValue("view/zoom", actual)

    def _set_zoom(self, level):
        level = int(level)
        level = max(-10, min(20, level))
        self.textEdit.zoomTo(level)
        actual = int(self.textEdit.SendScintilla(QsciScintillaBase.SCI_GETZOOM))
        self.zoom_level = actual
        self.settings.setValue("view/zoom", actual)

    def _on_zoom_changed(self, level):
        try:
            self.zoom_level = int(level)
        except Exception:
            self.zoom_level = 0
        self.settings.setValue("view/zoom", self.zoom_level)

    def openFindReplaceDialog(self):
        dialog = FindReplaceDialog(self.textEdit)
        dialog.exec_()

    def importFromWeb(self):
        dialog = ImportFromWebDialog(self.textEdit, app_context=self.app_context)
        dialog.exec_()

    def newFile(self):
        self.current_file = None
        self.textEdit.clear()
        self.setWindowTitle('Scratchpad - Unnamed')
        self.newline = "\r\n"
        self.textEdit.setEolMode(QsciScintilla.EolWindows)
        self.unsaved_changes = False
        self.updateStatusBar(after_save=True)

    def openFile(self):
        options = QFileDialog.Options()
        try:
            file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt);;All Files (*)", options=options)
            if file_name:
                self._start_file_load(file_name)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open file: {e}")

    def _on_file_content_loaded(self, gen, path, content, encoding, newline):
        if gen != self._open_generation:
            return
        self.loadFileContent(path, content, encoding, newline)

    def _on_file_load_started(self, gen, path, encoding, newline):
        if gen != self._open_generation:
            return
        if not self.current_file or os.path.realpath(path) != os.path.realpath(self.current_file):
            return
        if encoding:
            self.encoding = encoding
        if newline:
            self.newline = newline
            if newline == "\r\n":
                self.textEdit.setEolMode(QsciScintilla.EolWindows)
            elif newline == "\r":
                self.textEdit.setEolMode(QsciScintilla.EolMac)
            else:
                self.textEdit.setEolMode(QsciScintilla.EolUnix)
        with QSignalBlocker(self.textEdit):
            self.textEdit.setText("")
        self.setWindowTitle(f'Scratchpad - {os.path.basename(self.current_file)}')
        if self.current_file:
            self.addToRecentFiles(self.current_file)
        self.unsaved_changes = False
        self.updateStatusBar(after_save=True)

    def _on_file_chunk_loaded(self, gen, path, chunk, is_last):
        if gen != self._open_generation:
            return
        if not self.current_file or os.path.realpath(path) != os.path.realpath(self.current_file):
            return
        if chunk:
            with QSignalBlocker(self.textEdit):
                self.textEdit.append_text(chunk)
        if is_last:
            self.unsaved_changes = False
            self.updateStatusBar(after_save=True)

    def loadFileContent(self, path, content, encoding, newline):
        if not self.current_file or os.path.realpath(path) != os.path.realpath(self.current_file):
            return
        if encoding is None:
            QMessageBox.critical(self, "Error", content)
            return
        if encoding:
            self.encoding = encoding
        if newline:
            self.newline = newline
            if newline == "\r\n":
                self.textEdit.setEolMode(QsciScintilla.EolWindows)
            elif newline == "\r":
                self.textEdit.setEolMode(QsciScintilla.EolMac)
            else:
                self.textEdit.setEolMode(QsciScintilla.EolUnix)
        with QSignalBlocker(self.textEdit):
            self.textEdit.setPlainText(content)
        self.setWindowTitle(f'Scratchpad - {os.path.basename(self.current_file)}')
        if self.current_file:
            self.addToRecentFiles(self.current_file)
        self.unsaved_changes = False
        self.updateStatusBar(after_save=True)

    def saveFile(self):
        content = self.textEdit.toPlainText()
        if self.encoding is None:
            self.encoding = 'utf-8'
        try:
            content.encode(self.encoding)
        except UnicodeEncodeError:
            return self.promptForEncoding(content)
        if self.current_file:
            return self.saveFileWithEncoding(content, self.encoding)
        else:
            return self.saveFileAs(content)

    def promptForEncoding(self, content):
        encoding, ok = QInputDialog.getItem(self, "Choose Encoding", "Select Encoding", 
                                             ["UTF-8", "ISO-8859-1", "Windows-1252", "UTF-16"], 0, False)
        if ok:
            return self.saveFileWithEncoding(content, encoding)
        return False
    
    def saveFileWithEncoding(self, content, encoding):
        if self.current_file:
            try:
                with open(self.current_file, 'w', encoding=encoding, newline='') as file:
                    file.write(content)
                self.unsaved_changes = False
                self.updateStatusBar(after_save=True)
                return True
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save file with encoding '{encoding}': {e}")
                return False
        return False

    

    def saveFileAs(self, content=None):
        options = QFileDialog.Options()
        try:
            file_name, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "Text Files (*.txt);;All Files (*)", options=options)
            if file_name:
                self.current_file = file_name
                if content is None:
                    content = self.textEdit.toPlainText()
                return self.saveFileWithEncoding(content, self.encoding)
            return False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save file: {e}")
            return False

    def updateStatusBar(self, after_save=False):
        cursor = self.textEdit.textCursor()
        self.line = cursor.blockNumber() + 1
        self.column = cursor.columnNumber() + 1
        try:
            self.char_count = self.textEdit.length()
        except Exception:
            try:
                self.char_count = self.textEdit.textLength()
            except Exception:
                self.char_count = len(self.textEdit.text())
        asterisk = ""
        if not after_save:
            asterisk = "*" if self.unsaved_changes else ""
        self.statusBar.showMessage(f"Line: {self.line} | Column: {self.column} | Characters: {self.char_count} | Encoding: {self.encoding} {asterisk}")
    def loadRecentFiles(self):
        self.settings = QSettings("Scratchpad", "ScratchpadApp")
        self.recent_files = self.settings.value("recentFiles", [], type=list)

    def addToRecentFiles(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)          
        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[:5]
        self.settings.setValue("recentFiles", self.recent_files)
        self.updateRecentFilesMenu()

    def updateRecentFilesMenu(self):
        self.recentFilesMenu.clear()
        filtered = []
        seen = set()
        for p in self.recent_files:
            real = os.path.realpath(p)
            if not (os.path.exists(real) and os.access(real, os.R_OK)):
                continue
            if real in seen:
                continue
            seen.add(real)
            filtered.append(real)
        filtered = filtered[:5]
        if filtered != self.recent_files:
            self.recent_files = filtered
            self.settings.setValue("recentFiles", self.recent_files)
        if not self.recent_files:
            self.recentFilesMenu.setEnabled(False)
        else:
            self.recentFilesMenu.setEnabled(True)
            for path in self.recent_files:
                file_name = os.path.basename(path)
                action = QAction(file_name, self)
                action.triggered.connect(lambda checked, p=path: self.openRecentFile(p))
                action.setToolTip(path)
                self.recentFilesMenu.addAction(action)
            self.recentFilesMenu.addSeparator()
            clearAction = QAction("Clear Recently Opened Files", self)
            clearAction.triggered.connect(self.clearRecentFiles)
            self.recentFilesMenu.addAction(clearAction)

    def openRecentFile(self, file_path):
        if os.path.exists(file_path):
            self._start_file_load(file_path)
        else:
            QMessageBox.warning(self, "File Not Found", f"File not found: {file_path}")
            if file_path in self.recent_files:
                self.recent_files.remove(file_path)
                self.settings.setValue("recentFiles", self.recent_files)
                self.updateRecentFilesMenu()
                
    def clearRecentFiles(self):
        self.recent_files = []
        self.settings.setValue("recentFiles", self.recent_files)
        self.updateRecentFilesMenu()
        


if __name__ == '__main__':
    app = QApplication(sys.argv)
    loadStyle()
    file_to_open = None
    if len(sys.argv) > 1:
        file_to_open = sys.argv[1]
    scratchpad = Scratchpad(file_to_open)
    scratchpad.show()
    sys.exit(app.exec_())
