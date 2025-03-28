import sys
import datetime
import time
import img_source_rc
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QTimer, QTime, Qt
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import QMessageBox

'''
0.0.1 :> GUI 초기 구성 완료
'''
version = "version 0.0.1"

# Style Sheet Preset
color_disable = "background-color: rgb(156, 156, 156);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_enable = "background-color: rgb(170, 0, 0);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_lock = "background-color: rgb(90, 90, 90);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"

class MyApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("Status_Logging_GUI.ui", self)   # Load GUI file
        
        # Initialize
        self.init_ui()
                
        # Timer setting
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000) # 1000ms = 1s
        self.update_time()

        
    def init_ui(self):
        '''
        1. START 버튼 클릭 전 (동작 전)
        lab_programStatus : '대기중' 출력

        2. START 버튼 클릭 후 (동작 중)

        3. 동작 중 UNLOCK 버튼 클릭

        4. 동작 완료 후

        '''
        # Initialize flag
        self.flag_start = False
        self.flag_unlock = False
        
        self.operation_timer = 0

        # Initialize status
        self.lab_timer.hide()
        self.lab_timer.setAlignment(Qt.AlignCenter)
        self.btn_stop.setEnabled(False)
        self.btn_unlock.setEnabled(False)

        # Initialize system related buttons/labels
        self.cmb_modeSelection.currentTextChanged.connect(self.func_modeSelection)
        self.btn_clearFileName.clicked.connect(self.func_clearFileName)
        self.btn_folder.clicked.connect(self.func_folder)
        self.btn_start.clicked.connect(self.func_start)
        self.btn_stop.clicked.connect(self.func_stop)
        self.btn_unlock.clicked.connect(self.func_unlock)
        # self.btn_device1.clicked.connect(self.)
        # self.btn_device2.clicked.connect(self.)
        # self.btn_device3.clicked.connect(self.)
        self.lab_version.setText(version)
        # self.progressBar

        for self.group_canConnect

        # Operation related buttons/labels
        # self.lab_current_dev1
        # self.lab_temp_dev1
    
    def update_operation_display(self):
        hours = self.operation_timer // 3600
        mins = (self.operation_timer % 3600) //60
        secs = self.operation_timer % 60
        self.lab_timer.setText(f"{hours:04}:{mins:02}:{secs:02}")
        pass

    def update_time(self):
        if self.flag_start:
            self.operation_timer += 1
            self.update_operation_display()

        date = datetime.datetime.now()
        crnt_date = (f'{date.year}년 {date.month}월 {date.day}일')
        self.lab_crntDate.setText(crnt_date)
        current_time = QTime.currentTime().toString("hh:mm")
        self.lab_crntTime.setText(current_time)
    
    def func_modeSelection(self):
        date = datetime.datetime.now()
        select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")
        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{select_date}_{select_time}")

    def func_clearFileName(self):
        self.line_logFileName.setText("")

    def func_folder(self):
        pass

    def func_start(self):
        # When clicked start button, poped up a messageBox to confirm
        reply = QMessageBox.question(self, "확인 메시지", "테스트를 시작하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Interlock Start/Stop/Unlock button
            self.flag_start = True
            self.flag_unlock = True
            self.btn_start.setEnabled(False)
            self.btn_start.setStyleSheet(color_disable)
            self.btn_unlock.setEnabled(True)
            self.btn_unlock.setText("UNLOCK")
            self.btn_unlock.setStyleSheet(color_enable)
            self.lab_programStatus.setText("동작중")
            self.lab_programStatus.setFont(QFont("한컴 고딕", 16, QFont.Bold))
            self.lab_programStatus.setStyleSheet("color: rgb(170, 0, 0);")
            self.lab_programStatus.setAlignment(Qt.AlignCenter)
            self.lab_timer.show()            

    def func_stop(self):
        if self.flag_start:
            reply = QMessageBox.question(self, "확인 메시지", "테스트를 정지하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # Interlock Start/Stop/Unlock button
                self.btn_stop.setEnabled(False)
                self.btn_stop.setStyleSheet(color_disable)
                self.btn_unlock.setEnabled(False)
                self.btn_unlock.setStyleSheet(color_disable)
                self.btn_start.setEnabled(True)
                self.btn_start.setStyleSheet(color_enable)
                self.lab_programStatus.setText("대기중")
                self.lab_programStatus.setStyleSheet("color: rgb(0, 120, 0);")
                self.lab_timer.hide()
                self.flag_start = False
                self.operation_timer = 0
                self.lab_timer.setText("0000:00:00")

    def func_unlock(self):
        # Interlock Start/Stop/Unlock button
        if self.flag_start:
            if self.flag_unlock:
                self.flag_unlock = False
                self.btn_unlock.setStyleSheet(color_lock)
                self.btn_unlock.setText("LOCK")
                self.btn_stop.setEnabled(True)
                self.btn_stop.setStyleSheet(color_enable)
            else:
                self.flag_unlock = True
                self.btn_unlock.setStyleSheet(color_enable)
                self.btn_unlock.setText("UNLOCK")
                self.btn_stop.setEnabled(False)
                self.btn_stop.setStyleSheet(color_disable)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MyApp()
    window.show()
    sys.exit(app.exec_())