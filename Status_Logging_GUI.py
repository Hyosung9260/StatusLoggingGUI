import sys
import time
import json
import logging
import datetime
import numpy as np
import img_source_rc
import logging.handlers

from Status_DEF import *
from threading import Thread
from SRC_PCAN.PCANBasic import *
from SRC_PCAN.PCAN_CONTROLLER import PCANControl


from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from PyQt5.QtCore import QTimer, QTime, QThread, Qt, pyqtSignal, QObject, QEventLoop

update_date = "25.04.07"
version = "version 0.0.6"
'''
# NOTE Ver_0.0.6
6-1. Auto Start Mode, Manual Start Mode 구분, Tx Power/Temperature request message 전송 및 read
6-2. Update Tx Power/Temp를 monitoring panel과 연동
6-3. 크리티컬 로그 출력 (일정 온도 범위를 초과하는 경우에만 로그에 기록, 저장은 X)
6-4. 

# TODO
- PCAN connect (CAN ID, Device ID)
    > CAN ID 0, 1, 2에서 각각 유력한 Device ID 테이블의 각 리스트마다 연결되어 있는지를 확인, Device ID는 테일게이트면 모두 B0, FF면 D0 식으로 정의 → 별칭을 바로 출력하는 편의성 제공)
    > Sleep 모드 표시
- Test 모드 기입 (Test 모드 중 하나만 Mode setting 예외처리, 15 → 8 → 1 → 15 → 8 → 1 ==> 15 → 8 → 16 → 8 → 16 ...으로 처음 1번만 15h 추가)
- Test 진행 중 Device OFF 상태에서 ON 상태로 들어가면 GUI에서 wake up(Active) 모드로 들어오도록 CAN 메시지 송신하도록 프로토콜 구현
- 모드별 setting 기입 및 소요시간 출력
- System log에 PCAN connection status 추가
- Graph view 기능 추가 (QThread or Thread)
- MOBED와 RODS 테스트모드 구분
- 로그파일 저장 경로에 폴더가 없으면 폴더를 생성하는 기능 추가
- Sys log, CAN log가 어떤건 저장되고 어떤건 저장 안되는(저장 옵션이 켜져 있음에도) 부분이 있을 수 있으므로 전체 확인
    > 특히 CANReadWorker에서 emit으로 전송한 CAN log부분

* 엑셀에서 테스트 모드 데이터 로드하는 방안 강구
'''

# Style Sheet Preset
color_disable = "background-color: rgb(156, 156, 156);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_enable = "background-color: rgb(170, 0, 0);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_lock = "background-color: rgb(90, 90, 90);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"

class CANReadWorker(QObject):
    log_signal = pyqtSignal(int, str)                       # Signal for print log
    finished = pyqtSignal()                                 # Signal for worker finish
    update_signal = pyqtSignal(int, str, str, str, str)     # Signal for update TxPower, Temperature
    onOff_signal = pyqtSignal(bool)                         # Signal for check radar on/off
    stop_signal = pyqtSignal()                              # Signal for worker stop    

    def __init__(self, pcan_ctrl, dev_id, flag_door_test, flag_auto_start, parent=None):
        super().__init__(parent)
        self.pcan_ctrl = pcan_ctrl
        self.dev_id = dev_id
        self.flag_door_test = flag_door_test
        self.flag_auto_start = flag_auto_start
        self.onOff_signal.connect(self.control_onOff)
        self.stop_signal.connect(self.stop)
        self.running = True
        self.flag_on = False
        self.flag_deact = False
        self.send_count = 0       
        self.ascii_data_tx0 = 0
        self.ascii_data_tx1 = 0
        self.ascii_data_tx2 = 0
        self.ascii_data_temp = 0 
        self.onOffErrorCount = 0
        self.offCount = 0
        self.pcan_handle = None
            
    def run(self):
        # Get PCAN USB handle and Receive event
        _, self.pcan_handle = self.pcan_ctrl.get_handle_from_id(self.dev_id)
        _, self.receive_event = self.pcan_ctrl.InitializeEvent(Channel=self.pcan_handle)

        if self.pcan_ctrl.reset_handle(self.pcan_handle) != 0:
            self.log_signal.emit(0, "Reset failed")
            self.finished.emit()
            return

        # Initial Act message write
        if not self.flag_auto_start:
            self.send_act_msg()
        
        # Timer for TxPower/Temperature requrest message write (2ms -> 500ms)
        self.Timer_2ms = QTimer()
        self.Timer_2ms.setInterval(2)
        self.Timer_2ms.timeout.connect(lambda: self.send_msg_2ms())
        self.Timer_2ms.moveToThread(QThread.currentThread())

        self.Timer_500ms = QTimer()
        self.Timer_500ms.setInterval(500)
        self.Timer_500ms.timeout.connect(self.send_msg_500ms)
        self.Timer_500ms.moveToThread(QThread.currentThread())

        # Write 'send tx power and temp' request cmd (2ms - 500ms)
        self.Timer_2ms.start()
        loop = QEventLoop()

        self.log_signal.emit(0, "CAN read thread started")
        while self.running:
            msg_flag, msg_data, msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=self.pcan_handle, recv_event=self.receive_event, wait_time=1000, output_mode='numpy', evt_mode=False)

            if self.flag_auto_start:
                if self.flag_door_test:
                    # TODO :: Door test의 경우 MSG_ID 체크
                    pass

                else:   # Talegate test
                    if msg_id == 0x17FC0014 or msg_id == 0x17C5F801:    # 40ms sleep check
                        if self.flag_on:
                            if self.onOffErrorCount != 0:
                                self.onOffErrorCount = 0
                                self.flag_deact == False
                        else:   # OFF                            
                            self.log_signal.emit(0, f"[CAN] Deact Error count : {self.onOffErrorCount} / {MAX_ERROR_COUNT}")
                            self.check_onOff(self.flag_on)
                            time.sleep(0.1)  # 100 ms
                            if self.onOffErrorCount > MAX_ERROR_COUNT:
                                # TODO :: 조치할 내용 추가
                                self.log_signal.emit(0, f"[ERROR] Radar device deact error")
                            self.onOffErrorCount += 1

                    elif msg_id == 0x1FF11400:      # TxPower / Temperature
                        # Tx0 Power
                        if msg_data[5] == 0x50 and msg_data[6] == 0x6F and msg_data[7] == 0x77 and msg_data[8] == 0x65 and msg_data[9] == 0x72:
                            tx0_data_hex = msg_data[17:21]
                            self.ascii_data_tx0 = tx0_data_hex.tobytes().decode('ascii')
                            self.log_signal.emit(1, f"Tx0 Power : {self.ascii_data_tx0} [dBm]")
                        # Tx1 Power
                        elif msg_data[6] == 0x50 and msg_data[7] == 0x6F and msg_data[8] == 0x77 and msg_data[9] == 0x65 and msg_data[10] == 0x72:
                            tx1_data_hex = msg_data[18:22]
                            self.ascii_data_tx1 = tx1_data_hex.tobytes().decode('ascii')
                            self.log_signal.emit(1, f"Tx1 Power : {self.ascii_data_tx1} [dBm]")
                        # Tx2 Power
                        elif msg_data[7] == 0x50 and msg_data[8] == 0x6F and msg_data[9] == 0x77 and msg_data[10] == 0x65 and msg_data[11] == 0x72:
                            tx2_data_hex = msg_data[19:23]
                            self.ascii_data_tx2 = tx2_data_hex.tobytes().decode('ascii')
                            self.log_signal.emit(1, f"Tx2 Power : {self.ascii_data_tx2} [dBm]")
                        # Temperature
                        elif msg_data[8] == 0x54 and msg_data[9] == 0x65 and msg_data[10] == 0x6D and msg_data[11] == 0x70 and msg_data[12] == 0x65:
                            temp_data_hex = msg_data[21:26]
                            self.ascii_data_temp = temp_data_hex.tobytes().decode('ascii')
                            self.log_signal.emit(1, f"Temperature : {self.ascii_data_temp} [℃]")
                            if float(self.ascii_data_temp) > TEMP_LIMIT[1]:
                                # TODO :: 크리티컬 로그에 출력하도록 작성
                                pass
                        else:
                            pass
                        self.update_signal.emit(self.dev_id, str(self.ascii_data_tx0), str(self.ascii_data_tx1), str(self.ascii_data_tx2), str(self.ascii_data_temp))
                    
                    else:   # No message react from radar
                        if self.flag_on:
                            if msg_id == 999:
                                self.onOffErrorCount += 1
                                self.log_signal.emit(0, f"[CAN] Act Error count : {self.onOffErrorCount} / {MAX_ERROR_COUNT}")
                                self.check_onOff(self.flag_on)
                                time.sleep(0.1)  # 100 ms
                                if self.onOffErrorCount > MAX_ERROR_COUNT:
                                    # TODO :: 조치할 내용 추가
                                    self.log_signal.emit(0, f"[ERROR] Radar device act error")
                        else:   # OFF
                            if msg_id == 0:
                                self.offCount += 1
                                time.sleep(0.1)  # 100 ms
                                if self.offCount > CONFIRM_OFF_COUNT and self.flag_deact == False:
                                    self.log_signal.emit(0, "[CAN] Radar device is deactivated")
                                    self.flag_deact = True
            
            else:   # Manual start firmware
                if self.flag_door_test:
                    pass

                else:   # Talegate test                    
                    pass

            loop.processEvents(QEventLoop.AllEvents, 10)
        
        self.Timer_2ms.stop()
        self.Timer_500ms.stop()
        self.pcan_ctrl.CloseEvent(self.receive_event)
        self.finished.emit()
    
    def send_msg_2ms(self):
        # TODO :: On 인지 Off인지 확인해서 전송주기 조절
        if self.flag_door_test:
            pass

        else:   # Talegate test
            msg_id = TALEGATE_MSG_ID[1]
            dlc = len(TALEGATE_PWR_TEMP)
            msg_frame = TALEGATE_PWR_TEMP

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle, msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            # self.log_signal.emit(1, "[CAN] message write : TxPower/Temp request")
            pass
        else:
            # TODO :: 에러 메시지 출력
            self.log_signal.emit(1, "[CAN] message write : TxPower/Temp request failed")
            pass

        self.send_count += 1
        if self.send_count >= 2:
            self.Timer_2ms.stop()
            self.Timer_500ms.start()
    
    def send_msg_500ms(self):
        self.send_count = 0
        self.Timer_2ms.start()

    def send_act_msg(self):
        if self.flag_door_test:
            pass

        else:   # Talegate test
            msg_id = TALEGATE_MSG_ID[0]
            dlc = len(TALEGATE_ACT)
            msg_frame = TALEGATE_ACT

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle, msg_id, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                self.log_signal.emit(1, "[CAN] message write : Act")
                self.offCount = 0             
            else:                           # Failed to write CAN message
                # TODO :: 에러 메시지 출력
                self.log_signal.emit(1, "[ERROR] message write : Act")                
                pass            

    def send_deact_msg(self):
        if self.flag_door_test:
            pass

        else:   # Talegate test
            msg_id = TALEGATE_MSG_ID[0]
            dlc = len(TALEGATE_DEACT)
            msg_frame = TALEGATE_DEACT

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle, msg_id, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                self.log_signal.emit(1, "[CAN] message write : Deact")
            else:                           # Failed to write CAN message
                # TODO :: 에러 메시지 출력
                self.log_signal.emit(1, "[ERROR] message write : Deact")
                pass
        
        
        # TODO :: 실제로 Sleep인지 확인, 계속 깨어있으면 n번 Deact 반복 전송, 그래도 깨어있으면 오류 메시지 전송 (emit)
        pass

    def control_onOff(self, onOffStatus):
        self.log_signal.emit(0, f"[Worker] On/Off Signal recieved : {onOffStatus}")
        if onOffStatus: # ON
            self.flag_on = True
        else:           # OFF
            self.flag_on = False
    
    def check_onOff(self, onOffStatus):
        if onOffStatus: # ON
            self.send_act_msg()
            time.sleep(0.05)
        else:           # OFF
            self.send_act_msg()
            time.sleep(0.05)
            self.send_deact_msg()
            time.sleep(1)

    def stop(self):
        self.running = False

class StatusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("Status_Logging_GUI.ui", self)   # Load GUI file
        self.init_ui()      # Initialize
        self.thread_list = []   # Only for thread managing
        self.worker_dict = {}
        self.crnt_val = None
        
        # Timer setting
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000) # 1000ms = 1s
                
        # Activate PCAN
        self.pcan_ctrl = PCANControl()
        
    def init_ui(self):
        # Get date, time info
        date = datetime.datetime.now()
        self.select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")

        # Initialize flag
        self.flag_start = False
        self.flag_lock = False
        self.flag_innerCycle = True
        self.flag_innerOnTime = True
        self.flag_work_outer_cycle = False
        self.flag_saveSyslog = True
        self.flag_door_test = True
        self.flag_test_finished = False
        self.flag_auto_start = True
        self.flag_on = False
        
        # Initialize variables
        self.connected_dev_id = []
        self.connected_dev_dict = {1:0, 2:0, 3:0}
        self.operation_timer = 0
        self.innerOnTime = 0
        self.innerOffTime = 0
        self.numInnerCycle = 0
        self.outerOffTime = 0
        self.numOuterCycle = 0
        self.crntInnerCycle = 0
        self.crntOuterCycle = 0
        self.inner_cycle_timer = 0
        self.outer_cycle_timer = 0
        self.max_logFile_size = 10*1024*1024

        # Initial font setting
        self.lab_programStatus.setFont(QFont("한컴 고딕", 16, QFont.Bold))
        self.lab_programStatus.setAlignment(Qt.AlignCenter)
        
        # Initialize status
        self.lab_timer.hide()
        self.lab_timer.setAlignment(Qt.AlignCenter)
        self.btn_stop.setEnabled(False)
        self.btn_unlock.setEnabled(False)

        # Initialize system related buttons/labels
        self.cmb_modeSelection.currentTextChanged.connect(self.func_modeSelection)
        self.checkBox_InnerMode.stateChanged.connect(self.toggle_test_mode_setting)

        self.btn_clearFileName.clicked.connect(self.func_clearFileName)
        self.btn_folder.clicked.connect(self.func_oper_path)
        self.btn_folder_sysLog.clicked.connect(self.func_sys_path)
        self.btn_start.clicked.connect(self.func_start)
        self.btn_stop.clicked.connect(self.func_stop)
        self.btn_unlock.clicked.connect(self.func_unlock)
        self.btn_clearCycleSetting.clicked.connect(self.clear_cycle_setting)
        self.btn_device1.clicked.connect(self.update_can_dev1)
        self.btn_device2.clicked.connect(self.update_can_dev2)
        self.btn_device3.clicked.connect(self.update_can_dev3)
        self.btn_canConnectionCheck.clicked.connect(self.can_connection_check)

        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{self.select_date}_{select_time}")
        self.line_logFilePath.setText("./LogFiles")
        self.line_sysLogFilePath.setText("./LogFiles/SysLog")
        self.line_innerOnTime.textChanged.connect(self.update_test_setting)
        self.line_innerOffTime.textChanged.connect(self.update_test_setting)
        self.line_numInnerCycle.textChanged.connect(self.update_test_setting)
        self.line_outerOffTime.textChanged.connect(self.update_test_setting)
        self.line_numOuterCycle.textChanged.connect(self.update_test_setting)

        self.radioBtn_door.toggled.connect(self.update_num_dev)
        self.radioBtn_talegate.toggled.connect(self.update_num_dev)
        self.radioBtn_manualMode.toggled.connect(self.update_operation_mode)
        self.radioBtn_autoMode.toggled.connect(self.update_operation_mode)
        self.radioBtn_sysLogMon.toggled.connect(self.update_syslog_mode)
        self.radioBtn_sysLogSave.toggled.connect(self.update_syslog_mode)
        self.lab_version.setText(version)
        # self.progressBar

        # Generate logger instance for logging
        self.oper_logger = logging.getLogger('OPERTATION_LOG')
        self.oper_logger.setLevel(logging.DEBUG)

        self.sys_logger = logging.getLogger('SYSTEM_LOG')
        self.sys_logger.setLevel(logging.DEBUG)
        sys_logger_filename = self.line_sysLogFilePath.text() + '/SYSTEM_LOG_' + self.select_date + '.log'
        self.sys_log_handler = logging.handlers.RotatingFileHandler(filename=sys_logger_filename, mode='a', maxBytes=self.max_logFile_size)
        sys_formatter = logging.Formatter(fmt='%(asctime)s > %(message)s')
        self.sys_log_handler.setFormatter(sys_formatter)
        self.sys_logger.addHandler(self.sys_log_handler)

    def update_operation_display(self):
        hours = self.operation_timer // 3600
        mins = (self.operation_timer % 3600) // 60
        secs = self.operation_timer % 60
        self.lab_timer.setText(f"{hours:04}:{mins:02}:{secs:02}")

    def func_emit_onOffStatus(self, onOffStatus):
        # Emit signal to stop read can message
        for dev_id, worker in self.worker_dict.items():
            worker.onOff_signal.emit(onOffStatus)
            self.print_log(0, f"All workers have been signaled to check On/Off : {onOffStatus}")

    def inner_cycle_work(self):
        if self.flag_innerOnTime:
            if self.inner_cycle_timer < self.innerOnTime - 1:
                self.inner_cycle_timer += 1
            else:
                self.print_log(0, "write [Deact] Message")
                self.inner_cycle_timer = 0
                self.flag_on = False
                self.func_emit_onOffStatus(self.flag_on)
                self.flag_innerOnTime = False
        else:
            if self.inner_cycle_timer < self.innerOffTime - 1:
                self.inner_cycle_timer += 1
            else:
                self.inner_cycle_timer = 0
                self.crntInnerCycle += 1                
                
                if self.crntInnerCycle < self.numInnerCycle:
                    self.flag_on = True
                    self.func_emit_onOffStatus(self.flag_on)
                    self.flag_innerOnTime = True
                    self.print_log(0, "write [Act] Message")
                else:                    
                    self.crntInnerCycle = 0
                    if self.flag_innerCycle:
                        self.flag_test_finished = True
                        self.print_log(0, "Test completed")
                        self.func_unlock()
                        self.func_stop()
                        
                    else:
                        self.flag_work_outer_cycle = True
                        self.print_log(0, "Inner cycle completed")
    
    def outer_cycle_work(self):
        if self.flag_work_outer_cycle == False:
                self.inner_cycle_work()
        else:
            if self.outer_cycle_timer < self.outerOffTime - 1:
                self.outer_cycle_timer += 1
            else:
                self.outer_cycle_timer = 0
                self.crntOuterCycle += 1
                self.flag_work_outer_cycle = False

                if self.crntOuterCycle < self.numOuterCycle:
                    self.flag_on = True
                    self.func_emit_onOffStatus(self.flag_on)
                    self.print_log(0, "write [Act] Message")
                    self.print_log(0, f"Current Outer Cycle : {self.crntOuterCycle} / Total Outer Cycle : {self.numOuterCycle}")
                else:
                    self.crntOuterCycle = 0
                    self.flag_test_finished = True
                    self.print_log(0, "Test completed")
                    self.func_unlock()
                    self.func_stop()

    def cycle_counter(self):
        if self.line_innerOnTime.text().strip():
            if self.flag_innerCycle:
                self.inner_cycle_work()
            else:
                self.outer_cycle_work()
        else:   # Case that user want continuous operation
            pass

    def update_time(self):
        if self.flag_start:
            self.operation_timer += 1
            self.print_log(0, f"{self.operation_timer}")
            self.update_operation_display()
            self.cycle_counter()

        date = datetime.datetime.now()
        crnt_date = (f'{date.year}년 {date.month}월 {date.day}일')
        self.lab_crntDate.setText(crnt_date)
        current_time = QTime.currentTime().toString("hh:mm")
        self.lab_crntTime.setText(current_time)
    
    def toggle_test_mode_setting(self, state):
        if state == Qt.Checked:
            self.group_outerSetting.setDisabled(True)
            self.flag_innerCycle = True
        else:
            self.group_outerSetting.setDisabled(False)
            self.flag_innerCycle = False

    def update_test_setting(self):
        try:
            # If input value is not integer, consider 0
            self.innerOnTime = int(self.line_innerOnTime.text()) if self.line_innerOnTime.text().isdigit() else 0
            self.innerOffTime = int(self.line_innerOffTime.text()) if self.line_innerOffTime.text().isdigit() else 0
            self.numInnerCycle = int(self.line_numInnerCycle.text()) if self.line_numInnerCycle.text().isdigit() else 0
            
            # Update result to line_totalInnerCycleTime
            total_time = (self.innerOnTime + self.innerOffTime) * self.numInnerCycle
            self.line_totalInnerCycleTime.setText(str(total_time))

            hours = total_time // 3600
            mins = (total_time % 3600) // 60
            secs = total_time % 60
            self.line_totalTestTime.setText(f"{hours}시간{mins}분{secs}초")

        # If occur exclude case, consider 0
        except ValueError:
            self.line_totalInnerCycleTime.setText("0")
        
        if self.flag_innerCycle == False:
            try:
                self.outerOffTime = int(self.line_outerOffTime.text()) if self.line_outerOffTime.text().isdigit() else 0
                self.numOuterCycle = int(self.line_numOuterCycle.text()) if self.line_numOuterCycle.text().isdigit() else 0

                total_time_outer = (total_time + self.outerOffTime) * self.numOuterCycle
                self.line_totalOuterCycleTime.setText(str(total_time_outer))

                hours = total_time_outer // 3600
                mins = (total_time_outer % 3600) // 60
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

    def update_num_dev(self):
        if self.radioBtn_door.isChecked():
            self.flag_door_test = True
            self.radioBtn_talegate.setChecked(False)
            self.groupBox_canDev2.setEnabled(False)
            self.groupBox_canDev3.setEnabled(False)
        else:   # Talegate test
            self.flag_door_test = False
            self.radioBtn_door.setChecked(False)
            self.groupBox_canDev2.setEnabled(True)
            self.groupBox_canDev3.setEnabled(True)

    def update_operation_mode(self):
        if self.radioBtn_manualMode.isChecked():
            self.radioBtn_autoMode.setChecked(False)
            self.group_customModeSetting.setEnabled(True)
        else:
            self.radioBtn_manualMode.setChecked(False)
            self.group_customModeSetting.setDisabled(True)
    
    def update_syslog_mode(self):
        if self.radioBtn_sysLogMon.isChecked():
            self.radioBtn_sysLogSave.setChecked(False)
            self.flag_saveSyslog = False
        else:
            self.radioBtn_sysLogMon.setChecked(False)
            self.flag_saveSyslog = True

    def disconnect_can_dev(self, dev_id, radar_id):
        disconnect_result = self.pcan_ctrl.uninitialize(dev_id=dev_id)
        
        if disconnect_result:
            self.connected_dev_id.remove(dev_id)
            self.connected_dev_dict[radar_id] = 99

            sysLogMsg = f"CAN device disconnected : {dev_id}"
            self.print_log(0, sysLogMsg)
            return True
        else:
            sysLogMsg = f"CAN device disconnect failed : {dev_id}"
            self.print_log(0, sysLogMsg)
            return False

    def connect_can_dev(self, dev_id, radar_id):
        if dev_id in self.connected_dev_id:
            sysLogMsg = f"CAN device already connected : {dev_id}"
            self.print_log(0, sysLogMsg)
            return False
        else:
            connect_result = self.pcan_ctrl.initialize(dev_id=dev_id)
            
            if connect_result:
                self.connected_dev_id.append(dev_id)
                self.connected_dev_dict[radar_id] = dev_id
                sysLogMsg = f"CAN device connected : {dev_id}"
                self.print_log(0, sysLogMsg)
                return True
            else:
                sysLogMsg = f"CAN device connect failed : {dev_id}"
                self.print_log(0, sysLogMsg)
                return False
    
    def update_can_dev1(self):
        dev_id = self.spinBox_devID1.value()
        if self.btn_device1.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 1)
            if retVal:  # Succeed
                self.spinBox_devID1.setEnabled(False)
            else:       # Failed
                self.btn_device1.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 1)
            if retVal:  # Succeed
                self.spinBox_devID1.setEnabled(False)
            else:       # Failed
                self.btn_device1.toggle()

    def update_can_dev2(self):
        dev_id = self.spinBox_devID2.value()
        if self.btn_device2.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 2)
            if retVal:  # Succeed
                    self.spinBox_devID2.setEnabled(False)
            else:       # Failed
                self.btn_device2.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 2)
            if retVal:  # Succeed
                self.spinBox_devID2.setEnabled(False)
            else:       # Failed
                self.btn_device2.toggle()
    
    def update_can_dev3(self):
        dev_id = self.spinBox_devID3.value()
        if self.btn_device3.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 3)
            if retVal:  # Succeed
                self.spinBox_devID3.setEnabled(False)
            else:       # Failed
                self.btn_device3.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 3)
            if retVal:  # Succeed
                self.spinBox_devID3.setEnabled(True)
            else:       # Failed
                self.btn_device3.toggle()

    def send_act_sequence(self, pcan_handle):
        self.pcan_ctrl.send_actSensor(pcan_handle, self.flag_door_test)
        
    def send_deact_sequence(self, pcan_handle):
        self.pcan_ctrl.send_deactSensor(pcan_handle, self.flag_door_test)
    
    def confirm_msg_id(self, pcan_handle, receive_event):
        num_radar_dev = 0
        
        if self.flag_door_test:
            for count in range(10):
                _, _, recv_msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=pcan_handle,recv_event=receive_event,wait_time=1000,output_mode='numpy',evt_mode=False)
                # print(f"recv_msg_id : {recv_msg_id}")
                if str(hex(recv_msg_id)) in DOOR_RCV_MSG_ID_FL:
                    # Print system log
                    sysLogMsg = "Radar connected : CAN ID " + str(self.connected_dev_id[0]) + "_FL"
                    self.print_log(0, sysLogMsg)
                    num_radar_dev += 1
                    if num_radar_dev > 3:
                        break
                elif str(hex(recv_msg_id)) in DOOR_RCV_MSG_ID_FR:
                    # Print system log
                    sysLogMsg = "Radar connected : CAN ID " + str(self.connected_dev_id[0]) + "_FR"
                    self.print_log(0, sysLogMsg)
                    num_radar_dev += 1
                    if num_radar_dev > 3:
                        break
                elif str(hex(recv_msg_id)) in DOOR_RCV_MSG_ID_RL:
                    # Print system log
                    sysLogMsg = "Radar connected : CAN ID " + str(self.connected_dev_id[0]) + "_RL"
                    self.print_log(0, sysLogMsg)
                    num_radar_dev += 1
                    if num_radar_dev > 3:
                        break
                elif str(hex(recv_msg_id)) in DOOR_RCV_MSG_ID_RR:
                    # Print system log
                    sysLogMsg = "Radar connected : CAN ID " + str(self.connected_dev_id[0]) + "_RR"
                    self.print_log(0, sysLogMsg)
                    num_radar_dev += 1
                    if num_radar_dev > 3:
                        break
                time.sleep(0.1)  # CPU 점유율 방지

        else:   # Talegate test
            flag_findDev = 0
            while (True):
            # for count in range(10):
                _, _, recv_msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=pcan_handle,recv_event=receive_event,wait_time=1000,output_mode='numpy',evt_mode=False)
                if flag_findDev == 0:
                    if str(hex(recv_msg_id)) in TALEGATE_RCV_MSG_ID:
                        # Print system log
                        sysLogMsg = "Radar connected : CAN ID " + str(self.connected_dev_id) + "_TG"
                        self.print_log(0, sysLogMsg)
                        flag_findDev = 1
                        # break
                else:
                    pass

                # time.sleep(0.1)  # CPU 점유율 방지

    def can_connection_check(self):
        if self.flag_door_test:
            if self.btn_device1.isChecked():
                _, pcan_handle = self.pcan_ctrl.get_handle_from_id(self.connected_dev_id[0])
                _, receive_event = self.pcan_ctrl.InitializeEvent(Channel=pcan_handle)

                self.send_act_sequence(pcan_handle)
                time.sleep(0.05)
                self.confirm_msg_id(pcan_handle, receive_event)
                self.send_deact_sequence(pcan_handle)
            else:
                sysLogMsg = f"CAN device is not connected. Please check connection."
                self.print_log(0, sysLogMsg)

        else:   # Talegate test
            if self.btn_device1.isChecked() or self.btn_device2.isChecked() or self.btn_device3.isChecked():
                for dev_id in self.connected_dev_id:
                    _, pcan_handle = self.pcan_ctrl.get_handle_from_id(dev_id)
                    _, receive_event = self.pcan_ctrl.InitializeEvent(Channel=pcan_handle)

                    self.send_act_sequence(pcan_handle)
                    time.sleep(0.05)
                    self.confirm_msg_id(pcan_handle, receive_event)
                    self.send_deact_sequence(pcan_handle)
                else:
                    sysLogMsg = f"CAN device is not connected. Please check connection."
                    self.print_log(0, sysLogMsg)
            else:
                sysLogMsg = f"CAN device is not connected. Please connect all the 3 devices."
                self.print_log(0, sysLogMsg)

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
                sys_cursor = self.txtEdit_sysLog.textCursor()
                sys_cursor.movePosition(sys_cursor.Start)
                sys_cursor.select(sys_cursor.BlockUnderCursor)
                sys_cursor.removeSelectedText()
            if self.flag_saveSyslog:
                self.sys_logger.debug(message)
        # category 1 : CAN log
        elif category == 1:
            self.txtEdit_canLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_canLog.ensureCursorVisible()     # Automatically scroll to the bottom of the textEdit
            if self.txtEdit_canLog.document().blockCount() > max_log_lines:
                can_cursor = self.txtEdit_canLog.textCursor()
                can_cursor.movePosition(can_cursor.Start)
                can_cursor.select(can_cursor.BlockUnderCursor)
                can_cursor.removeSelectedText()   
            self.oper_logger.debug(message)

    def func_modeSelection(self):
        date = datetime.datetime.now()
        select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")
        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{select_date}_{select_time}")

    def func_clearFileName(self):
        self.line_logFileName.setText("")

    def func_oper_path(self):
        folder_path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        # Only executed when user select path
        if folder_path:
            self.line_logFilePath.setText(folder_path)
    
    def func_sys_path(self):
        folder_path = QFileDialog.getExistingDirectory(self, "폴더 선택")
        # Only executed when user select path
        if folder_path:
            self.line_sysLogFilePath.setText(folder_path)

    def pcan_activate(self):
        self.pcan_ctrl = PCANControl()

    def pcan_deactivate(self):
        self.pcan_ctrl = None

    def read_can_buf_thread(self, dev_id):
        # Generate QThread and Worker
        thread = QThread()
        worker = CANReadWorker(self.pcan_ctrl, dev_id, self.flag_door_test, self.flag_auto_start)

        # Connect signals
        worker.log_signal.connect(self.print_log)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(worker.deleteLater)

        # Move worker to thread
        worker.moveToThread(thread)

        # Function for CAN read data update
        worker.update_signal.connect(self.update_worker_data)
        
        # Call run when thread is started
        thread.started.connect(lambda: QTimer.singleShot(0, worker.run))
        thread.start()
        
        # Add thread and worker into the list for manage
        self.thread_list.append(thread)
        self.worker_dict[dev_id] = worker
    
    def update_worker_data(self, dev_id, tx0, tx1, tx2, temp):
        # print(tx0, tx1, tx2, temp)
        if self.connected_dev_dict[1] == dev_id:
            self.lab_Rdr1_txPwr1.setText(tx0)
            self.lab_Rdr1_txPwr2.setText(tx1)
            self.lab_Rdr1_txPwr3.setText(tx2)
            self.lab_Rdr1_tmp.setText(temp)
        elif self.connected_dev_dict[2] == dev_id:
            self.lab_Rdr2_txPwr1.setText(tx0)
            self.lab_Rdr2_txPwr2.setText(tx1)
            self.lab_Rdr2_txPwr3.setText(tx2)
            self.lab_Rdr2_tmp.setText(temp)
        elif self.connected_dev_dict[3] == dev_id:
            self.lab_Rdr3_txPwr1.setText(tx0)
            self.lab_Rdr3_txPwr2.setText(tx1)
            self.lab_Rdr3_txPwr3.setText(tx2)
            self.lab_Rdr3_tmp.setText(temp)
        else:
            sysLogMsg = "Dev_id is not matched with any Radar_id"
            self.print_log(0, sysLogMsg)

    def process_start(self):
        # Generate thread as num of connected dev
        for dev_id in self.connected_dev_id:
            self.read_can_buf_thread(dev_id)

    def func_start(self):
        # When clicked start button, poped up a messageBox to confirm
        reply = QMessageBox.question(self, "확인 메시지", "테스트를 시작하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Process start
            self.process_start()

            # Interlock Start/Stop/Unlock button
            self.flag_start = True
            self.flag_lock = True
            self.flag_on = True
            self.func_emit_onOffStatus(self.flag_on)
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
            
            # Lock other functions
            self.group_modeSelection.setEnabled(False)
            self.group_canConnect.setEnabled(False)
            self.group_logConfig.setEnabled(False)
            self.group_customModeSetting.setEnabled(False)            
            
            # Save operation log
            oper_logger_filename = self.line_logFilePath.text() + '/' + self.line_logFileName.text() + '.log'
            self.oper_log_handler = logging.handlers.RotatingFileHandler(filename=oper_logger_filename, mode='a', maxBytes=self.max_logFile_size)
            oper_formatter = logging.Formatter(fmt='%(asctime)s > %(message)s')
            self.oper_log_handler.setFormatter(oper_formatter)
            self.oper_logger.addHandler(self.oper_log_handler)
            
            # Print system log
            sysLogMsg = "START button clicked (Mode : " + self.cmb_modeSelection.currentText() + ")"
            self.print_log(0, sysLogMsg)
            
    def func_stop(self):
        if self.flag_start and self.flag_test_finished == False:
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

                # Unlock other functions
                self.group_modeSelection.setEnabled(True)
                self.group_canConnect.setEnabled(True)
                self.group_logConfig.setEnabled(True)
                self.group_customModeSetting.setEnabled(True)

                # Print and save system log
                self.print_log(0, "STOP button clicked")
                self.sys_logger.debug("STOP button clicked")

                # Emit signal to stop read can message
                for dev_id, worker in self.worker_dict.items():
                    worker.stop_signal.emit()
                    self.print_log(0, "All workers have been signaled to stop")

                # Remove logger handler
                self.oper_logger.removeHandler(self.oper_log_handler)

        elif self.flag_start and self.flag_test_finished:
            # Print and save system log
            self.print_log(0, "STOP button auto clicked")
            self.sys_logger.debug("STOP button auto clicked")

            # Emit signal to stop read can message
            for dev_id, worker in self.worker_dict.items():
                worker.stop_signal.emit()
                self.print_log(0, "All workers have been signaled to stop")        

            # Remove logger handler
            self.oper_logger.removeHandler(self.oper_log_handler)
            self.flag_test_finished = False
            
            reply = QMessageBox.question(self, "확인 메시지", "테스트가 완료되었습니다.", QMessageBox.Yes)
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

                # Unlock other functions
                self.group_modeSelection.setEnabled(True)
                self.group_canConnect.setEnabled(True)
                self.group_logConfig.setEnabled(True)
                self.group_customModeSetting.setEnabled(True)

    def func_unlock(self):
        # Interlock Start/Stop/Unlock button
        if self.flag_start:
            if self.flag_lock:
                self.flag_lock = False
                self.btn_unlock.setStyleSheet(color_lock)
                self.btn_unlock.setText("LOCK")
                self.btn_stop.setEnabled(True)
                self.btn_stop.setStyleSheet(color_enable)
            else:
                self.flag_lock = True
                self.btn_unlock.setStyleSheet(color_enable)
                self.btn_unlock.setText("UNLOCK")
                self.btn_stop.setEnabled(False)
                self.btn_stop.setStyleSheet(color_disable)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = StatusGUI()
    window.show()
    sys.exit(app.exec_())