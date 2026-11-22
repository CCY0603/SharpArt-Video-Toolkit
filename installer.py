"""SharpArtVideo 安装程序（离线、纯 Python + PyInstaller）。

- 默认把内嵌的应用目录（含 ffmpeg/ffprobe）安装到用户的 Program Files；
- 创建开始菜单 + 桌面快捷方式；
- 在 HKEY_CURRENT_USER 注册卸载信息（无需管理员权限）；
- 把自身复制为 uninstall.exe，支持 `--uninstall` 卸载。
"""

import os
import shutil
import subprocess
import sys
import winreg
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QProgressBar, QFileDialog, QMessageBox,
    QTextEdit,
)

APP_NAME = "锐艺视频处理工具"
APP_VERSION = "2.0"
APP_EXE = "SharpArtVideo.exe"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SharpArtVideo"
HIDE = 0x08000000  # CREATE_NO_WINDOW


def payload_dir() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    cand = os.path.join(base, "app_payload")
    return cand if os.path.isdir(cand) else base


def default_install_dir() -> str:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    return os.path.join(pf, "SharpArtVideo")


def start_menu_dir() -> str:
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME,
    )


def create_shortcut(lnk: str, target: str, workdir: str, desc: str) -> None:
    ps = (
        "$w = New-Object -ComObject WScript.Shell;"
        "$s = $w.CreateShortcut('%s');"
        "$s.TargetPath = '%s';"
        "$s.WorkingDirectory = '%s';"
        "$s.Description = '%s';"
        "$s.Save()" % (lnk, target, workdir, desc)
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=HIDE, timeout=30,
        )
    except Exception:
        pass


def write_uninstall_entry(install_dir: str) -> None:
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        uninstall_exe = os.path.join(install_dir, "uninstall.exe")
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "SharpArt")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                          '"%s" --uninstall' % uninstall_exe)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
    except Exception:
        pass


def remove_uninstall_entry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except Exception:
        pass


def remove_shortcuts() -> None:
    sm = start_menu_dir()
    for path in (
        os.path.join(sm, APP_NAME + ".lnk"),
        os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk"),
    ):
        try:
            os.remove(path)
        except Exception:
            pass
    try:
        os.rmdir(sm)
    except Exception:
        pass


class InstallWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, src: str, dst: str) -> None:
        super().__init__()
        self.src = src
        self.dst = dst

    def _count(self, root: str) -> int:
        n = 0
        for _, _, files in os.walk(root):
            n += len(files)
        return max(n, 1)

    def run(self) -> None:
        try:
            if os.path.isdir(self.dst):
                shutil.rmtree(self.dst)
            os.makedirs(self.dst, exist_ok=True)
            total = self._count(self.src)
            done = 0
            for root, dirs, files in os.walk(self.src):
                rel = os.path.relpath(root, self.src)
                tgt = self.dst if rel == "." else os.path.join(self.dst, rel)
                os.makedirs(tgt, exist_ok=True)
                for f in files:
                    shutil.copy2(os.path.join(root, f), os.path.join(tgt, f))
                    done += 1
                    if done % 200 == 0:
                        self.progress.emit(
                            max(5, min(85, int(done / total * 85))),
                            "正在复制文件…", )
            self.progress.emit(90, "创建快捷方式…")
            exe = os.path.join(self.dst, APP_EXE)
            os.makedirs(start_menu_dir(), exist_ok=True)
            create_shortcut(os.path.join(start_menu_dir(), APP_NAME + ".lnk"),
                            exe, self.dst, APP_NAME)
            create_shortcut(
                os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk"),
                exe, self.dst, APP_NAME)
            try:
                shutil.copyfile(sys.executable,
                                os.path.join(self.dst, "uninstall.exe"))
            except Exception:
                pass
            write_uninstall_entry(self.dst)
            self.progress.emit(100, "完成")
            self.finished.emit(True, self.dst)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


def do_uninstall() -> None:
    install_dir = None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        install_dir = winreg.QueryValueEx(key, "InstallLocation")[0]
        winreg.CloseKey(key)
    except Exception:
        pass
    if not install_dir or not os.path.isdir(install_dir):
        install_dir = default_install_dir()
    try:
        remove_shortcuts()
    except Exception:
        pass
    remove_uninstall_entry()
    try:
        for root, dirs, files in os.walk(install_dir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except Exception:
                    pass
        try:
            os.rmdir(install_dir)
        except Exception:
            pass
    except Exception:
        pass


class InstallerWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("%s 安装程序" % APP_NAME)
        self.setMinimumWidth(560)
        self.resize(560, 300)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("%s  v%s" % (APP_NAME, APP_VERSION))
        title.setFont(QFont("", 15, QFont.Bold))
        layout.addWidget(title)
        layout.addWidget(QLabel("本安装包已内置 ffmpeg / ffprobe，无需额外安装。"))

        row = QHBoxLayout()
        self.path_edit = QLineEdit(default_install_dir())
        self.path_edit.setReadOnly(True)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        row.addWidget(QLabel("安装位置："), 0)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse, 0)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(70)
        layout.addWidget(self.log)

        self.install_btn = QPushButton("安装")
        self.install_btn.clicked.connect(self._install)
        layout.addWidget(self.install_btn)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择安装目录",
                                             self.path_edit.text())
        if d:
            self.path_edit.setText(os.path.join(d, "SharpArtVideo"))

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _install(self) -> None:
        dst = self.path_edit.text().strip()
        if not dst:
            return
        self.install_btn.setEnabled(False)
        self.worker = InstallWorker(payload_dir(), dst)
        self.worker.progress.connect(
            lambda v, m: (self.progress.setValue(v), self._log(m)))
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, ok: bool, msg: str) -> None:
        if ok:
            self._log("安装完成：%s" % msg)
            QMessageBox.information(
                self, APP_NAME,
                "安装完成！\n\n%s 已安装到：\n%s\n\n已创建开始菜单与桌面快捷方式。"
                % (APP_NAME, msg))
            QApplication.quit()
        else:
            self._log("安装失败：%s" % msg)
            QMessageBox.critical(
                self, APP_NAME,
                "安装失败：%s\n\n若目标目录需要管理员权限，请右键“以管理员身份运行”本安装程序。"
                % msg)
            self.install_btn.setEnabled(True)


def main() -> None:
    if "--uninstall" in sys.argv:
        do_uninstall()
        app = QApplication(sys.argv)
        QMessageBox.information(None, APP_NAME, "已卸载 %s。" % APP_NAME)
        return
    app = QApplication(sys.argv)
    w = InstallerWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
