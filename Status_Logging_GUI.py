import sys
import json
import datetime
import img_source_rc

from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QTimer, QTime, Qt
from PyQt5.QtWidgets import QMessageBox, QFileDialog

from SRC_PCAN.PCAN_CONTROLLER import PCANControl

version = "version 0.0.3"
'''
# NOTE Ver_0.0.3
1. 자동/수동 동작모드 추가
2. 수동 동작모드에서 Custom mode setting 추가
3. System log 관련 설정 추가

# TODO
1. System log 저장 (START, STOP 등)
2. Operation log 저장 (CAN or Result 등)
3. PCAN connect (CAN ID, Device ID)
   > CAN ID 0, 1, 2에서 각각 유력한 Device ID 테이블의 각 리스트마다 연결되어 있는지를 확인, Device ID는 테일게이트면 모두 B0, FF면 D0 식으로 정의 → 별칭을 바로 출력하는 편의성 제공)
4. PCAN device auto search (버튼 클릭시 연결된 CAN 케이블 search 후 해당 케이블에 연결된 device ID까지 search)
5. Test 모드 기입 (Test 모드 중 하나만 Mode setting 예외처리, 15 → 8 → 1 → 15 → 8 → 1 ==> 15 → 8 → 16 → 8 → 16 ...으로 처음 1번만 15h 추가)
6. Test 진행 중 Device OFF 상태에서 ON 상태로 들어가면 GUI에서 wake up(Active) 모드로 들어오도록 CAN 메시지 송신하도록 프로토콜 구현

* 엑셀에서 테스트 모드 데이터 로드하는 방안
'''

# Style Sheet Preset
color_disable = "background-color: rgb(156, 156, 156);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_enable = "background-color: rgb(170, 0, 0);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_lock = "background-color: rgb(90, 90, 90);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"

class StatusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("Status_Logging_GUI.ui", self)   # Load GUI file        
        self.init_ui()      # Initialize                
        # Timer setting
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000) # 1000ms = 1s
        self.update_time()
        # Activate PCAN
        self.pcan_ctrl = PCANControl()
        
    def init_ui(self):
        # Get date, time info
        date = datetime.datetime.now()
        select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")

        # Initialize flag
        self.flag_start = False
        self.flag_unlock = False
        self.flag_innerCycle = True
        
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
        # self.btn_canSearch.clicked.connect(self.btn_canSearch)
        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{select_date}_{select_time}")
        self.checkBox_InnerMode.stateChanged.connect(self.toggle_outer_setting)
        self.line_innerOnTime.textChanged.connect(self.update_total_inner_cycle_time)
        self.line_innerOffTime.textChanged.connect(self.update_total_inner_cycle_time)
        self.line_numInnerCycle.textChanged.connect(self.update_total_inner_cycle_time)
        self.line_outerOffTime.textChanged.connect(self.update_total_inner_cycle_time)
        self.line_numOuterCycle.textChanged.connect(self.update_total_inner_cycle_time)
        self.btn_clearCycleSetting.clicked.connect(self.clear_cycle_setting)
        self.radioBtn_manualMode.toggled.connect(self.update_operation_mode)
        self.radioBtn_autoMode.toggled.connect(self.update_operation_mode)
        self.lab_version.setText(version)
        # self.progressBar

    def update_operation_display(self):
        hours = self.operation_timer // 3600
        mins = (self.operation_timer % 3600) //60
        secs = self.operation_timer % 60
        self.lab_timer.setText(f"{hours:04}:{mins:02}:{secs:02}")

    def update_time(self):
        if self.flag_start:
            self.operation_timer += 1
            self.update_operation_display()

        date = datetime.datetime.now()
        crnt_date = (f'{date.year}년 {date.month}월 {date.day}일')
        self.lab_crntDate.setText(crnt_date)
        current_time = QTime.currentTime().toString("hh:mm")
        self.lab_crntTime.setText(current_time)
    
    def toggle_outer_setting(self, state):
        if state == Qt.Checked:
            self.group_outerSetting.setDisabled(True)
            self.flag_innerCycle = True
        else:
            self.group_outerSetting.setDisabled(False)
            self.flag_innerCycle = False

    def update_total_inner_cycle_time(self):
        try:
            # If input value is not integer, consider 0
            on_time = int(self.line_innerOnTime.text()) if self.line_innerOnTime.text().isdigit() else 0
            off_time = int(self.line_innerOffTime.text()) if self.line_innerOffTime.text().isdigit() else 0
            num_cycle = int(self.line_numInnerCycle.text()) if self.line_numInnerCycle.text().isdigit() else 0
            
            # Update result to line_totalInnerCycleTime
            total_time = (on_time + off_time) * num_cycle
            self.line_totalInnerCycleTime.setText(str(total_time))

            hours = total_time // 3600
            mins = total_time //60
            secs = total_time % 60
            self.line_totalTestTime.setText(f"{hours}시간{mins}분{secs}초")

        # If occur exclude case, consider 0
        except ValueError:
            self.line_totalInnerCycleTime.setText("0")
        
        if self.flag_innerCycle == False:
            try:
                off_time_outer = int(self.line_outerOffTime.text()) if self.line_outerOffTime.text().isdigit() else 0
                num_cycle_outer = int(self.line_numOuterCycle.text()) if self.line_numOuterCycle.text().isdigit() else 0

                total_time_outer = (total_time + off_time_outer) * num_cycle_outer
                self.line_totalOuterCycleTime.setText(str(total_time_outer))

                hours = total_time_outer // 3600
                mins = total_time_outer //60
                secs = total_time_outer % 60
                self.line_totalTestTime.setText(f"{hours}시간{mins}분{secs}초")
            
            except ValueError:
                self.line_totalOuterCycleTime.setText("0")

    def clear_cycle_setting(self):
        if self.flag_innerCycle:
            self.line_innerOnTime.setText("")
            self.line_innerOffTime.setText("")
            self.line_numInnerCycle.setText("")
        else:
            self.line_innerOnTime.setText("")
            self.line_innerOffTime.setText("")
            self.line_numInnerCycle.setText("")
            self.line_outerOffTime.setText("")
            self.line_numOuterCycle.setText("")

    def update_operation_mode(self):
        if self.radioBtn_manualMode.isChecked():
            self.radioBtn_autoMode.setChecked(False)
            self.group_customModeSetting.setEnabled(True)
        else:
            self.radioBtn_manualMode.setChecked(False)
            self.group_customModeSetting.setDisabled(True)
    
    def btn_canSearch(self):
        # Open .json file to load PCAN config data
        with open('./SRC_PCAN/PCAN_config.json') as config_file:
            pcan_config = json.load(config_file)

        dev_id_list = pcan_config['DEV_ID_LIST']
        msg_id_list = pcan_config['MSG_ID_LIST']    # dictionary ("0D0" : "Example1") / string
        
        for dev_id in dev_id_list:
            connect_result = self.pcan_ctrl.initialize(dev_id=dev_id)   # CAN connect success : True / Fail : False
            if connect_result:
                # CAN device에 연결을 성공하면 해당 CAN에 연결된 레이더와 통신해서 msg id를 획득
                for msg_id in msg_id_list.keys():
                    # 연결되면 토클키까지 함께 제어해서 바로 connect, 3개 이하면 그 갯수 까지만 연결
                    # 연결 후 line_radar1~3에 msg_id_list의 value 출력

        

    def print_log(self, category, message):
        # Print log to the textEdit
        date = datetime.datetime.now()
        logging_date = date.strftime("%Y.%m.%d")
        logging_time = QTime.currentTime().toString("hh:mm:ss")

        # Limit the number of lines in the textEdit to avoid memory overflow
        max_log_lines = 1000

        # category 0 : System log 
        if category == 0:
            self.txtEdit_sysLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_sysLog.ensureCursorVisible()     # Automatically scroll to the bottom of the textEdit
            if self.txtEdit_sysLog.document().blockCount() > max_log_lines:
                cursor = self.txtEdit_sysLog.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()
        # category 1 : CAN log
        elif category == 1:
            self.txtEdit_canLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_canLog.ensureCursorVisible()     # Automatically scroll to the bottom of the textEdit
            if self.txtEdit_canLog.document().blockCount() > max_log_lines:
                cursor = self.txtEdit_canLog.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()

    def func_modeSelection(self):
        date = datetime.datetime.now()
        select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")
        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{select_date}_{select_time}")

    def func_clearFileName(self):
        self.line_logFileName.setText("")

    def func_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        # Only executed when user select path
        if folder_path:
            self.line_logFilePath.setText(folder_path)

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
            # Print sys log
            self.print_log(0, "START button clicked (Mode : " + self.cmb_modeSelection.currentText() + ")")
            # Lock other functions
            self.group_modeSelection.setEnabled(False)
            self.group_canConnect.setEnabled(False)
            self.group_logConfig.setEnabled(False)
            self.group_customModeSetting.setEnabled(False)
            # Calculate Total test time/Current and Remain cycle


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
                self.print_log(0, "STOP button clicked")  # Print sys log
                # Unlock other functions
                self.group_modeSelection.setEnabled(True)
                self.group_canConnect.setEnabled(True)
                self.group_logConfig.setEnabled(True)
                self.group_customModeSetting.setEnabled(True)

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
    window = StatusGUI()
    window.show()
    sys.exit(app.exec_())