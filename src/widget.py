import sys
import os

from PySide6.QtWidgets import QApplication, QWidget, QDialog, QMessageBox

from ui.ui_about import Ui_AboutDialog

from ui_form import Ui_Widget
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile

import subprocess
import psutil
import shutil
import math


def to_mb(bytes):
    return math.ceil(bytes / 1048576)



class AboutDialog(QDialog, Ui_AboutDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)



class Widget(QWidget):
    allocated: bool = False

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = Ui_Widget()
        self.ui.setupUi(self)
        self.mem_refresh_action()
        self.ui.menubar.setNativeMenuBar(False)
        #self.ui.actionAbout.triggered.connect(QUiLoader().load("ui/about.ui", self).show)

        self.ui.actionAbout.triggered.connect(self.load_about)

        self.ui.actionExit.triggered.connect(self.close)
        self.ui.refreshButton.clicked.connect(self.mem_refresh_action)
        self.ui.applyButton.clicked.connect(self.change_swap_size)
    
    def set_status_text(self, message) -> None:
        self.ui.statusText.appendPlainText(message)

    def get_resource_path(self, relative_path):
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    def load_about(self):
        # ui_file_path = self.get_resource_path("ui/about.ui")
        # ui_file = QFile(ui_file_path)
        # ui_file.open(QFile.ReadOnly)

        # form = QUiLoader().load(ui_file, self)
        # ui_file.close()
        # form.show()
        about_ui = AboutDialog(self)
        about_ui.exec()


    def set_swap_info(self) -> None:
        details = self.get_swap_details()

        partition_value = str(details['partition']) + " MB" if details['partition'] else "N/A"
        file_value = str(details['file']) + " MB" if details['file'] else "N/A"

        self.ui.partitionSizeLabel.setText(partition_value)
        self.ui.fileSizeLabel.setText(file_value)


    def set_ram_values(self, vm):
        self.ui.ramProgressBar.setMinimum(0)
        self.ui.ramProgressBar.setMaximum(to_mb(vm.total))
        self.ui.ramProgressBar.setValue(to_mb(vm.used))
        self.ui.ramProgressBar.setFormat('%v / %m MB used')

        self.ui.totalRamLabel.setText("Total " + str(to_mb(vm.total)) + " MB")
        self.ui.usedRamLabel.setText("Used " + str(to_mb(vm.used)) + " MB")
        self.ui.freeRamLabel.setText("Available " + str(to_mb(vm.total - vm.used)) + " MB")


    def set_swap_values(self, swap):
        self.ui.swapProgressBar.setMinimum(0)
        self.ui.swapProgressBar.setMaximum(to_mb(swap.total))
        self.ui.swapProgressBar.setValue(to_mb(swap.used))
        self.ui.swapProgressBar.setFormat('%v / %m MB used')

        self.ui.totalSwapLabel.setText("Total " + str(to_mb(swap.total)) + " MB")
        self.ui.usedSwapLabel.setText("Used " + str(to_mb(swap.used)) + " MB")
        self.ui.freeSwapLabel.setText("Available " + str(to_mb(swap.free)) + " MB")


    def mem_refresh_action(self):
        self.set_status_text("Refreshing memory values.")
        swap = psutil.swap_memory()
        vm = psutil.virtual_memory()

        self.allocated = swap.total > 0
        if self.allocated:
            self.set_status_text("Swap space is allocated.")
        else:
            self.set_status_text("Swap space is not allocated.")

        self.set_ram_values(vm)
        self.set_swap_values(swap)

        self.set_swap_info()

        self.ui.swapFileInput.setText(str(to_mb(swap.total)))

        self.set_status_text("Memory values updated.")


    def get_swap_details(self) -> dict:
        swap = psutil.swap_memory()
        if swap.total == 0:
            return {"partition": False, "file": False}

        partition_kb = 0
        file_kb = 0
        try:
            with open("/proc/swaps", "r") as f:
                next(f)
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        typ   = parts[1].lower()
                        size_k = int(parts[2])
                        if typ == "partition":
                            partition_kb += size_k
                        elif typ == "file":
                            file_kb += size_k
        except FileNotFoundError:
            pass

        return {
            "partition": math.ceil(partition_kb / 1024) if partition_kb > 0 else False,
            "file": math.ceil(file_kb /1024) if file_kb      > 0 else False
        }


    def parse_memory_values(self, data):
        lines = [line.strip() for line in data.strip().splitlines() if line.strip()]
        delimiter = '\t' if '\t' in lines[0] else None
        headers = lines[0].split(delimiter)
        result = [ dict(zip(headers, row.split(delimiter))) for row in lines[1:] ]

        return result


    def run_command(self, cmd):
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, check=False)

        if int(result.returncode) != 0:
            self.set_status_text("Error in operation.")
            self.set_status_text(result.stderr)
            return int(result.returncode), result.stderr
        else:
            self.set_status_text(result.stdout)
            return int(result.returncode), result.stdout

    def change_swap_size(self):
        new_size = int(self.ui.swapFileInput.text())
        current_size = int(to_mb(psutil.swap_memory().total))

        if new_size == current_size:
            self.set_status_text("Invalid input.\nOperation aborted.")
            return

        self.set_status_text("Applying new swap space requires root access.")

        if shutil.which('pkexec') is None:
            self.set_status_text("Root access is not possible.\nOperation aborted.")
            return

        self.set_status_text(f"Starting to change the size of swap file to {new_size} MB.")
        swap_path = "/swapfile"

        if new_size == 0:
            self.set_status_text("Disabling swap file.")
            c, r = self.run_command(f"pkexec swapoff {swap_path}")
            if c == 0:
                self.set_status_text("Swap space is disabled.")
            return

        sh_cmd = f"""swapoff {swap_path};
                    dd if=/dev/zero of={swap_path} bs=1M count={new_size};
                    chmod 600 {swap_path};
                    mkswap {swap_path};
                    swapon {swap_path};"""

        cmd = ["pkexec", "bash", "-c", sh_cmd]
        c = subprocess.run(cmd, capture_output=True, text=True)

        if c.returncode != 0:
            self.set_status_text("Failed to update swap space.")

        self.mem_refresh_action()
        self.set_status_text("Swap space change operation complete.")




if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = Widget()
    widget.show()
    sys.exit(app.exec())
