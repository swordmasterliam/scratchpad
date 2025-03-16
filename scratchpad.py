""" Import the necessary modules for the program to work """
import sys
import os
import requests
import validators
import chardet
from chardet.universaldetector import UniversalDetector
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QAction,
                             QFileDialog, QMessageBox, QStatusBar, QDialog,
                             QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QIcon, QTextCursor, QTextDocument



""" Thread for handling file-related operations """
class FileHandler(QThread):
    file_content_loaded = pyqtSignal(str, str)
    file_saved = pyqtSignal(bool)

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
                with open(self.file_path, 'r', encoding=encoding, errors='replace') as file:
                    content = ""
                    chunk_size = 1024 * 1024
                    while chunk := file.read(chunk_size):
                        content += chunk
                        self.file_content_loaded.emit(content, encoding)
                self.file_content_loaded.emit(content, encoding)
            except Exception as e:
                self.file_content_loaded.emit(f"Error reading file: {e}", '')



""" Utility function to load icons """
def load_icon(icon_name):
    icon_path = os.path.join(os.path.dirname(__file__), icon_name)
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, icon_name)
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    return None



""" Utility function to load CSS stylesheet """
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



""" Dialog for Find and Replace functionality """
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
            content = self.text_edit.toPlainText()
            self.text_edit.setPlainText(content.replace(text_to_find, text_to_replace, 1))

    def replace_all(self):
        text_to_find = self.find_input.text()
        text_to_replace = self.replace_input.text()
        if text_to_find and text_to_replace:
            content = self.text_edit.toPlainText()
            self.text_edit.setPlainText(content.replace(text_to_find, text_to_replace))



""" Dialog for importing content from the web """
class ImportFromWebDialog(QDialog):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
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

    def fetch_from_web(self):
        url = self.url_input.text().strip()
        if self.is_valid_url(url):
            try:
                response = requests.get(url)
                response.raise_for_status()
                self.text_edit.setPlainText(response.text)
                self.accept()
            except requests.exceptions.RequestException as e:
                QMessageBox.critical(self, "Error", f"Failed to fetch content: {e}")
        else:
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid HTTPS URL.")

    def is_valid_url(self, url):
        return validators.url(url) and url.startswith("https://")



""" Dialog for unsaved changes warning """
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



""" Main window """
class Scratchpad(QMainWindow):
    def __init__(self, file_to_open=None):
        super().__init__()
        self.current_file = file_to_open
        self.file_handler = None
        self.unsaved_changes = False
        self.loadRecentFiles()
        self.initUI()
        if file_to_open:
            self.load_file_on_startup(file_to_open)

    def load_file_on_startup(self, file_path):
        if os.path.exists(file_path):
            self.current_file = file_path
            self.file_handler = FileHandler(file_path)
            self.file_handler.file_content_loaded.connect(self.loadFileContent)
            self.file_handler.start()
        else:
            QMessageBox.critical(self, "Error", f"File does not exist: {file_path}")

    def closeEvent(self, event):
        if self.textEdit.document().isModified():
            dialog = UnsavedWorkDialog(self)
            result = dialog.exec_()
            if result == QDialog.Accepted:
                self.saveFile()
                event.accept()
            elif result == QDialog.Rejected:
                event.ignore()
            elif result == 2:
                event.accept()
        else:
            event.accept()

    def initUI(self):
        self.setWindowTitle('Scratchpad - Unnamed')
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(load_icon('scratchpad.png'))
        self.textEdit = QTextEdit(self)
        self.setCentralWidget(self.textEdit)
        self.textEdit.setAcceptRichText(False)
        self.statusBar = QStatusBar(self)
        self.setStatusBar(self.statusBar)
        self.line = 1
        self.column = 1
        self.char_count = 0
        self.encoding = "UTF-8"
        self.textEdit.cursorPositionChanged.connect(self.updateStatusBar)
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
        #----
        menu.addSeparator()
        self.recentFilesMenu = menu.addMenu('Recently Opened Files')
        self.recentFilesMenu.aboutToShow.connect(self.updateRecentFilesMenu)
        self.updateRecentFilesMenu() #Removing this means you need to hover over it before it grays out
        
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

    def openFindReplaceDialog(self):
        dialog = FindReplaceDialog(self.textEdit)
        dialog.exec_()

    def importFromWeb(self):
        dialog = ImportFromWebDialog(self.textEdit)
        dialog.exec_()

    def newFile(self):
        self.current_file = None
        self.textEdit.clear()
        self.setWindowTitle('Scratchpad - Unnamed')

    def openFile(self):
        options = QFileDialog.Options()
        try:
            file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt);;All Files (*)", options=options)
            if file_name:
                self.current_file = file_name
                self.file_handler = FileHandler(file_name)
                self.file_handler.file_content_loaded.connect(self.loadFileContent)
                self.file_handler.start()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open file: {e}")

    def loadFileContent(self, content, encoding):
        if encoding:
            self.encoding = encoding
        if content.startswith("Error reading file"):
            QMessageBox.critical(self, "Error", content)
        else:
            self.textEdit.setPlainText(content)
            self.setWindowTitle(f'Scratchpad - {os.path.basename(self.current_file)}')
            if self.current_file:
                self.addToRecentFiles(self.current_file)

    def saveFile(self):
        """Save the current file."""
        content = self.textEdit.toPlainText()
        if self.encoding is None:
            self.encoding = 'utf-8'
        try:
            content.encode(self.encoding)
            if self.current_file:
                self.saveFileWithEncoding(content, self.encoding)
                self.unsaved_changes = False
                self.updateStatusBar(after_save=True)
            else:
                self.saveFileAs()
        except UnicodeEncodeError:
            self.promptForEncoding(content)

    def promptForEncoding(self, content):
        encoding, ok = QInputDialog.getItem(self, "Choose Encoding", "Select Encoding", 
                                             ["UTF-8", "ISO-8859-1", "Windows-1252", "UTF-16"], 0, False)
        if ok:
            self.saveFileWithEncoding(content, encoding)
    
    def saveFileWithEncoding(self, content, encoding):
        if self.current_file:
            try:
                with open(self.current_file, 'w', encoding=encoding) as file:
                    file.write(content)
                self.unsaved_changes = False
                self.updateStatusBar(after_save=True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save file with encoding '{encoding}': {e}")


    def handleSaveFile(self, success):
        if success:
            self.unsaved_changes = False
            self.updateStatusBar()
        else:
            QMessageBox.warning(self, "Error", "Failed to save file!")

    def saveFileAs(self):
        options = QFileDialog.Options()
        try:
            file_name, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "Text Files (*.txt);;All Files (*)", options=options)
            if file_name:
                self.current_file = file_name
                self.saveFile()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save file: {e}")

    def updateStatusBar(self, after_save=False):
        cursor = self.textEdit.textCursor()
        self.line = cursor.blockNumber() + 1
        self.column = cursor.columnNumber() + 1
        self.char_count = len(self.textEdit.toPlainText())
        asterisk = ""
        if not after_save:
            asterisk = "*" if self.unsaved_changes else ""
        self.statusBar.showMessage(f"Line: {self.line} | Column: {self.column} | Characters: {self.char_count} | Encoding: {self.encoding} {asterisk}")
    #Line 433 -> 463 relates to recent files and opening them
    def loadRecentFiles(self):
        self.settings = QSettings("Scratchpad", "ScratchpadApp")
        self.recent_files = self.settings.value("recentFiles", [], type=list)

    def addToRecentFiles(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)          
        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[:5] #This is the amount of files that should be displayed
        self.settings.setValue("recentFiles", self.recent_files)
        self.updateRecentFilesMenu()

    def updateRecentFilesMenu(self):
        self.recentFilesMenu.clear()
        if not self.recent_files:
            self.recentFilesMenu.setEnabled(False)
        else:
            self.recentFilesMenu.setEnabled(True)
            for file in self.recent_files:
                file_name = os.path.basename(file)
                action = QAction(file_name, self)
                action.triggered.connect(lambda checked, path=file: self.openRecentFile(path))
                action.setToolTip(file)
                self.recentFilesMenu.addAction(action)
            self.recentFilesMenu.addSeparator()
            clearAction = QAction("Clear Recently Opened Files", self)
            clearAction.triggered.connect(self.clearRecentFiles)
            self.recentFilesMenu.addAction(clearAction)

    def openRecentFile(self, file_path):
        if os.path.exists(file_path):
            self.current_file = file_path
            self.file_handler = FileHandler(file_path)
            self.file_handler.file_content_loaded.connect(self.loadFileContent)
            self.file_handler.start()
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
        

""" Start the program """
if __name__ == '__main__':
    app = QApplication(sys.argv)
    loadStyle()
    file_to_open = None
    if len(sys.argv) > 1:
        file_to_open = sys.argv[1]
    scratchpad = Scratchpad(file_to_open)
    scratchpad.show()
    sys.exit(app.exec_())
