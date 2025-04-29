import os
import csv
import sys
import logging
import datetime
import numpy as np
import img_source_rc
import logging.handlers

from Status_DEF import *
from SRC_PCAN.PCANBasic import *
from SRC_PCAN.PCAN_CONTROLLER import PCANControl

from PyQt5.QtGui import QFont
from PyQt5 import QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from PyQt5.QtCore import QTimer, QTime, QThread, Qt, pyqtSignal, QObject, QEventLoop, pyqtSlot

# Only for developer mode (Ignore deprecation warning)
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

update_date = "25.04.29"
version = "Ver_1.0.4"
'''
# NOTE Ver_1.0.4
1. Data log 
   > 테스트별로 분리되어 '테스트명_날짜_시간'으로 저장되도록 수정
   > 센서 Deact 시 0이 저장되도록 수정
   > 센서 Status가 함께 저장되도록 수정(IDLE, MEASURING 등)
2. GUI 레이더 데이터 출력 부분에 센서 Status가 출력되도록 수정
3. Tailgate 시험시 CAN ID가 0, 1, 2가 아닌 경우에도 정상 동작하도록 수정
4. 자동모드에서 테스트사이클에 자동으로 값이 입력된 후 비워져있는 테스트 모드 클릭 시 값이 비워지지 않고 여전히 채워져 있는 문제 수정

# TODO
# NOTE :: DUE DATE : 05.07 전까지 전달
* 프로그래머블 테스트모드 추가
* 엑셀에서 테스트 모드 데이터 로드하는 방안 강구

* 실행파일 생성 : pyinstaller --onefile --noconsole --add-data "Status_Logging_GUI.ui;." Status_Logging_GUI.py
'''

# Style Sheet Preset
color_disable = "background-color: rgb(156, 156, 156);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_enable = "background-color: rgb(170, 0, 0);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
color_lock = "background-color: rgb(90, 90, 90);\ncolor: rgb(255, 255, 255);\nborder-radius: 6px;"
activate = "image: url(:/etc/UI_IMG/Activate.png);"
sleep = "image: url(:/etc/UI_IMG/Sleep.png);"

# NOTE :: CANWriteWorker
class CANWriteWorker(QObject):
    log_signal = pyqtSignal(int, str)                       # Signal for print log
    finished = pyqtSignal()                                 # Signal for worker finish
    onOff_signal = pyqtSignal(bool)                         # Signal for check radar on/off
    stop_signal = pyqtSignal()                              # Signal for worker stop

    def __init__(self, pcan_ctrl, connected_dev_id, pcan_handle_dict, flag_door_test, read_worker_dict, parent=None):
        super().__init__(parent)
        self.pcan_ctrl = pcan_ctrl
        self.connected_dev_id = connected_dev_id
        self.pcan_handle_dict = pcan_handle_dict
        self.stop_signal.connect(self.stop)
        self.running = True
        self.flag_door_test = flag_door_test
        self.read_worker_dict = read_worker_dict
        self.send_count = 0        
        
    def run(self):
        self.timer_tx_power = QTimer()
        self.timer_tx_power.setSingleShot(True)
        self.timer_tx_power.timeout.connect(self.act_sequence)
        self.timer_tx_power.moveToThread(QThread.currentThread())
    
    @pyqtSlot(bool)
    def write_act_deact(self, onOffStatus):
        if onOffStatus: # ON
            self.write_act_msg()
            QThread.msleep(150)
            self.write_pre_pwr_tmp_request()

            # Send act message to read thread
            for dev_id, worker in self.read_worker_dict.items():
                worker.onOff_signal.emit(onOffStatus)
            self.act_sequence()

        else:           # OFF
            self.timer_tx_power.stop()
            self.write_deact_msg()
            
            # Send act message to read thread
            for dev_id, worker in self.read_worker_dict.items():
                worker.onOff_signal.emit(onOffStatus)
    
    @pyqtSlot(int)
    def write_resend(self, dev_id):
        # Door test
        if dev_id == 0x1FF100A2:
            self.write_pwr_tmp_request(FL)
        elif dev_id == 0x1FF100A3:
            self.write_pwr_tmp_request(FR)
        elif dev_id == 0x1FF100A5:
            self.write_pwr_tmp_request(RR)

        elif dev_id == 111:     # Write FL power/temp request message
            self.write_FL_pre_request()

        elif dev_id == 222:     # Write FR power/temp request message
            self.write_FR_pre_request()

        elif dev_id == 333:     # Write RR power/temp request message
            self.write_RR_pre_request()
        
        # Tailgate test
        elif dev_id in self.connected_dev_id:
            self.write_pwr_tmp_request(dev_id)
        
        elif dev_id == 444:
            self.write_TG_pre_request(dev_id=self.connected_dev_id[0])
        
        elif dev_id == 555:
            self.write_TG_pre_request(dev_id=self.connected_dev_id[1])
        
        elif dev_id == 666:
            self.write_TG_pre_request(dev_id=self.connected_dev_id[2])
    
    def act_sequence(self):
        self.write_act_msg()
        self.timer_tx_power.start(500)

    def write_FL_pre_request(self):
        msg_id = DOOR_FL_MSG_ID[1]
        dlc = len(RQST_PWR_TEMP_PRE1)
        msg_frame_pre1 = RQST_PWR_TEMP_PRE1
        msg_frame_pre2 = RQST_PWR_TEMP_PRE2
        msg_frame_pre3 = RQST_PWR_TEMP_PRE3

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)            
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FL")

    def write_FR_pre_request(self):
        msg_id = DOOR_FR_MSG_ID[1]
        dlc = len(RQST_PWR_TEMP_PRE1)
        msg_frame_pre1 = RQST_PWR_TEMP_PRE1
        msg_frame_pre2 = RQST_PWR_TEMP_PRE2
        msg_frame_pre3 = RQST_PWR_TEMP_PRE3

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)            
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FR")
    
    def write_RR_pre_request(self):
        msg_id = DOOR_RR_MSG_ID[1]
        dlc = len(RQST_PWR_TEMP_PRE1)
        msg_frame_pre1 = RQST_PWR_TEMP_PRE1
        msg_frame_pre2 = RQST_PWR_TEMP_PRE2
        msg_frame_pre3 = RQST_PWR_TEMP_PRE3

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)            
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : RR")
    
    def write_TG_pre_request(self, dev_id):
        msg_id = TAILGATE_MSG_ID[1]
        dlc = len(RQST_PWR_TEMP_PRE1)
        msg_frame_pre1 = RQST_PWR_TEMP_PRE1
        msg_frame_pre2 = RQST_PWR_TEMP_PRE2
        msg_frame_pre3 = RQST_PWR_TEMP_PRE3

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre1)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre2)
        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre3)
        # print(f"dev_id : {dev_id}, pcan_handle : {self.pcan_handle_dict[dev_id]}")
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, f"[ERROR] TxPower/Temp pre request failed : TG#{dev_id + 1}")
                
    def write_FL_deact(self):
        msg_id = DOOR_FL_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] Deact failed : FL")

    def write_FR_deact(self):
        msg_id = DOOR_FR_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] Deact failed : FR")

    def write_RR_deact(self):
        msg_id = DOOR_RR_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            pass
        else:
            self.log_signal.emit(0, "[ERROR] Deact failed : RR")

    def write_pre_pwr_tmp_request(self):
        if self.flag_door_test:
            msg_id_FL = DOOR_FL_MSG_ID[1]
            msg_id_FR = DOOR_FR_MSG_ID[1]
            msg_id_RR = DOOR_RR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre3)            
            if error_ok == PCAN_ERROR_OK:
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FL")
            QThread.msleep(30)

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FR")
            QThread.msleep(30)

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : RR")
            QThread.msleep(30)

        else:   # Tailgate test
            msg_id = TAILGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre1)
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre2)
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre3)
                QThread.msleep(50)
                if error_ok == PCAN_ERROR_OK:
                    pass
                else:
                    self.log_signal.emit(0, f"[ERROR] TxPower/Temp pre request failed : TG #{dev_id}")

    def write_pwr_tmp_request(self, sensorType):
        if self.flag_door_test:
            if sensorType == FL:
                msg_id = DOOR_FL_MSG_ID[1]
            elif sensorType == FR:
                msg_id = DOOR_FR_MSG_ID[1]
            elif sensorType == RL:
                msg_id = DOOR_RL_MSG_ID[1]
            else:
                msg_id = DOOR_RR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP)
            msg_frame = RQST_PWR_TEMP

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:
                pass
            else:
                self.log_signal.emit(0, f"[ERROR] TxPower/Temp request failed : {sensorType}")

        else:   # Tailgate test
            msg_id = TAILGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP)
            msg_frame = RQST_PWR_TEMP

            # for dev_id in self.connected_dev_id:
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[sensorType], msg_id, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:
                pass
            else:
                self.log_signal.emit(0, "[ERROR] message write : TxPower/Temp request failed")

    def write_act_msg(self):
        if self.flag_door_test:
            msg_id_FL = DOOR_FL_MSG_ID[0]
            msg_id_FR = DOOR_FR_MSG_ID[0]
            msg_id_RR = DOOR_RR_MSG_ID[0]
            dlc = DOOR_ACT[0]
            msg_frame = DOOR_ACT[1]

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, f"[ERROR] message write : FL Act {error_ok}")

            QThread.msleep(50)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, "[ERROR] message write : FR Act")

            QThread.msleep(50)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, "[ERROR] message write : RR Act")

        else:   # Tailgate test
            msg_id = TAILGATE_MSG_ID[0]
            dlc = len(TAILGATE_ACT)
            msg_frame = TAILGATE_ACT

            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    pass
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : Act")

    def write_deact_msg(self):
        if self.flag_door_test:
            msg_id_FL = DOOR_FL_MSG_ID[0]
            msg_id_FR = DOOR_FR_MSG_ID[0]
            msg_id_RR = DOOR_RR_MSG_ID[0]
            dlc = DOOR_DEACT[0]
            msg_frame = DOOR_DEACT[1]

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, "[ERROR] message write : FL Deact")

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, "[ERROR] message write : FR Deact")

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame)
            if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                pass
            else:                           # Failed to write CAN message
                self.log_signal.emit(0, "[ERROR] message write : RR Deact")

        else:   # Tailgate test
            msg_id = TAILGATE_MSG_ID[0]
            dlc = len(TAILGATE_DEACT)
            msg_frame = TAILGATE_DEACT
            
            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    pass
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : Deact")

    def stop(self):
        self.running = False

# NOTE :: CANReadWorker
class CANReadWorker(QObject):
    log_signal = pyqtSignal(int, str)                                # Signal for print log
    status_signal = pyqtSignal(int, int, bool)                       # Signal for show radar signal
    finished = pyqtSignal()                                          # Signal for worker finish
    update_data_signal = pyqtSignal(bool, int, str, str, str, str)   # Signal for update TxPower, Temperature
    update_status_signal = pyqtSignal(int, int, int)                 # Signal for update radar status
    onOff_signal = pyqtSignal(bool)                                  # Signal for check radar on/off
    resend_signal = pyqtSignal(int)                                  # Signal for Act/Deact resend request
    stop_signal = pyqtSignal()                                       # Signal for worker stop

    def __init__(self, pcan_ctrl, dev_id, pcan_handle, flag_door_test, parent=None):
        super().__init__(parent)
        self.pcan_ctrl = pcan_ctrl
        self.dev_id = dev_id
        self.flag_door_test = flag_door_test
        self.onOff_signal.connect(self.control_act_deact)
        self.stop_signal.connect(self.stop)

        self.running = True
        self.flag_act = True            # Act/Deact status change from Main thread
        self.flag_radar_act = False     # Realtime radar Act/Deact status
        self.flag_cmd_resend = False    # Main에서 요구한 상태와 Radar의 실제 상태가 달라 명령 재전송 필요 여부
        self.flag_deact = False
        self.flag_status_update_FL = False
        self.flag_status_update_FR = False
        self.flag_status_update_RR = False
        self.flag_status_update_TG = False
        self.send_count = 0
        self.ascii_data_tx0 = 0
        self.ascii_data_tx1 = 0
        self.ascii_data_tx2 = 0
        self.ascii_data_temp = 0
        self.ascii_data_tx0_r2 = 0
        self.ascii_data_tx1_r2 = 0
        self.ascii_data_tx2_r2 = 0
        self.ascii_data_temp_r2 = 0
        self.ascii_data_tx0_r3 = 0
        self.ascii_data_tx1_r3 = 0
        self.ascii_data_tx2_r3 = 0
        self.ascii_data_temp_r3 = 0
        self.offCount = 0
        self.flag_FL_on = False
        self.flag_FR_on = False
        self.flag_RR_on = False
        self.flag_TG_on = False
        self.flag_FL_on_once = False
        self.flag_FR_on_once = False
        self.flag_RR_on_once = False
        self.flag_TG_on_once = False
        self.flag_act_once   = False
        self.flag_deact_once = False
        self.count_FL_pre_request = 0
        self.count_FR_pre_request = 0
        self.count_RR_pre_request = 0
        self.count_TG_pre_request = 0
        self.pcan_handle = pcan_handle
            
    def run(self):
        if self.pcan_ctrl.reset_handle(self.pcan_handle) != 0:
            self.log_signal.emit(0, "Reset failed")
            self.finished.emit()
            return
        
        self.resend_request_timer = QTimer()
        self.resend_request_timer.setInterval(500)  # 1000ms = 1초
        self.resend_request_timer.timeout.connect(self.resend_request)
        self.resend_request_timer.moveToThread(QThread.currentThread())
        self.resend_request_timer.start()
        event_loop = QEventLoop()

        self.log_signal.emit(0, f"CAN read thread#{self.dev_id} started")
        while self.running:
            # CAN message read
            msg_data, msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=self.pcan_handle, output_mode='numpy')
            event_loop.processEvents(QEventLoop.AllEvents, 50)
            self.check_status_processing(msg_id, msg_data)

            # Main request ACT
            if self.flag_act:
                if msg_id:
                    self.data_processing(msg_id, msg_data)
                    
                    if not self.flag_act_once:
                        self.flag_radar_act = True
                        self.flag_cmd_resend = False
                        self.flag_act_once = True
                        self.flag_deact_once = False                        
                else:
                    if not self.flag_radar_act and not self.flag_cmd_resend:
                        self.flag_cmd_resend = True
            
            # Main request DEACT
            else:
                if msg_id:
                    if self.flag_radar_act and not self.flag_cmd_resend:
                        self.flag_cmd_resend = True
                else:
                    if not self.flag_deact_once:
                        # Check if radar has no response within 1 cycle
                        if self.flag_door_test:
                            if self.flag_FL_on_once == False:
                                self.log_signal.emit(2, "Radar has no response : FL")
                            elif self.flag_FR_on_once == False:
                                self.log_signal.emit(2, "Radar has no response : FR")
                            elif self.flag_RR_on_once == False:
                                self.log_signal.emit(2, "Radar has no response : RR")
                        else:   # Tailgate test
                            if self.flag_TG_on_once == False:
                                self.log_signal.emit(2, f"Radar has no response : TG#{self.dev_id}")

                        self.flag_radar_act = False
                        self.flag_cmd_resend = False
                        self.flag_FL_on = False
                        self.flag_FR_on = False
                        self.flag_RR_on = False
                        self.flag_TG_on = False
                        self.flag_FL_on_once = False
                        self.flag_FR_on_once = False
                        self.flag_RR_on_once = False
                        self.flag_TG_on_once = False
                        self.flag_act_once   = False
                        self.flag_deact_once = True
                        self.count_FL_pre_request = 0
                        if self.flag_door_test:
                            self.status_signal.emit(FL, self.dev_id, False)
                            self.status_signal.emit(FR, self.dev_id, False)
                            self.status_signal.emit(RR, self.dev_id, False)
                        else:
                            self.status_signal.emit(TG, self.dev_id, False)
                    else:
                        pass

        self.finished.emit()

    def check_status_processing(self, msg_id, msg_data):
        if self.flag_door_test:
            if msg_id == 0x04000000 and not self.flag_status_update_FL:
                if msg_data[3] == 0:
                    self.flag_status_update_FL = True
                    status = IDLE
                elif msg_data[3] == 1:
                    self.flag_status_update_FL = True
                    status = MEASURING
                elif msg_data[3] == 2:
                    self.flag_status_update_FL = True
                    status = DEGRADED
                elif msg_data[3] == 3:
                    self.flag_status_update_FL = True
                    status = FAULT
                elif msg_data[3] == 4:
                    self.flag_status_update_FL = True
                    status = BLOCKAGE
                else:
                    pass
                self.update_status_signal.emit(FL, 99, status)
            elif msg_id == 0x04000002 and not self.flag_status_update_FR:
                if msg_data[3] == 0:
                    self.flag_status_update_FR = True
                    status = IDLE
                elif msg_data[3] == 1:
                    self.flag_status_update_FR = True
                    status = MEASURING
                elif msg_data[3] == 2:
                    self.flag_status_update_FR = True
                    status = DEGRADED
                elif msg_data[3] == 3:
                    self.flag_status_update_FR = True
                    status = FAULT
                elif msg_data[3] == 4:
                    self.flag_status_update_FR = True
                    status = BLOCKAGE
                else:
                    pass
                self.update_status_signal.emit(FR, 99, status)
            elif msg_id == 0x04000006 and not self.flag_status_update_RR:
                if msg_data[3] == 0:
                    self.flag_status_update_RR = True
                    status = IDLE
                elif msg_data[3] == 1:
                    self.flag_status_update_RR = True
                    status = MEASURING
                elif msg_data[3] == 2:
                    self.flag_status_update_RR = True
                    status = DEGRADED
                elif msg_data[3] == 3:
                    self.flag_status_update_RR = True
                    status = FAULT
                elif msg_data[3] == 4:
                    self.flag_status_update_RR = True
                    status = BLOCKAGE
                else:
                    pass
                self.update_status_signal.emit(RR, 99, status)
        else:   # Tailgate test
            if msg_id == 0x17C5F801:
                if msg_data[3] == 0:
                    self.flag_status_update_TG = True
                    status = IDLE
                elif msg_data[3] == 1:
                    self.flag_status_update_TG = True
                    status = MEASURING
                elif msg_data[3] == 2:
                    self.flag_status_update_TG = True
                    status = DEGRADED
                elif msg_data[3] == 3:
                    self.flag_status_update_TG = True
                    status = FAULT
                elif msg_data[3] == 4:
                    self.flag_status_update_TG = True
                    status = BLOCKAGE
                else:
                    pass
                self.update_status_signal.emit(TG, self.dev_id, status)

    def data_processing(self, msg_id, msg_data):
        if self.flag_door_test:
            self.door_data_processing(msg_id, msg_data)
        else:   # Tailgate test
            self.tailgate_data_processing(msg_id, msg_data)

    def door_data_processing(self, msg_id, msg_data):
        # FL
        if msg_id == 0x1FF100A2:
            if not self.flag_FL_on:
                self.flag_FL_on = True
                self.flag_FL_on_once = True
                self.count_FL_pre_request = 0
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            if data_code == "Tx0":
                self.ascii_data_tx0 = result
            elif data_code == "Tx1":
                self.ascii_data_tx1 = result
            elif data_code == "Tx2":
                self.ascii_data_tx2 = result
            elif data_code == "Temp":
                self.ascii_data_temp = result
            self.update_data_signal.emit(self.flag_door_test, 0, str(self.ascii_data_tx0), str(self.ascii_data_tx1), str(self.ascii_data_tx2), str(self.ascii_data_temp))
            self.status_signal.emit(FL, self.dev_id, True)
        # FR
        elif msg_id == 0x1FF100A3:
            if not self.flag_FR_on:
                self.flag_FR_on = True
                self.flag_FR_on_once = True
                self.count_FR_pre_request = 0
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            if data_code == "Tx0":
                self.ascii_data_tx0_r2 = result
            elif data_code == "Tx1":
                self.ascii_data_tx1_r2 = result
            elif data_code == "Tx2":
                self.ascii_data_tx2_r2 = result
            elif data_code == "Temp":
                self.ascii_data_temp_r2 = result
            self.update_data_signal.emit(self.flag_door_test, 1, str(self.ascii_data_tx0_r2), str(self.ascii_data_tx1_r2), str(self.ascii_data_tx2_r2), str(self.ascii_data_temp_r2))
            self.status_signal.emit(FR, self.dev_id, True)
        # RL (Not used in this test)
        elif msg_id == 0x1FF100A4:
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            # self.update_data_signal.emit(self.dev_id, str(self.ascii_data_tx0), str(self.ascii_data_tx1), str(self.ascii_data_tx2), str(self.ascii_data_temp))
        # RR
        elif msg_id == 0x1FF100A5:
            if not self.flag_RR_on:
                self.flag_RR_on = True
                self.flag_RR_on_once = True
                self.count_RR_pre_request = 0
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            if data_code == "Tx0":
                self.ascii_data_tx0_r3 = result
            elif data_code == "Tx1":
                self.ascii_data_tx1_r3 = result
            elif data_code == "Tx2":
                self.ascii_data_tx2_r3 = result
            elif data_code == "Temp":
                self.ascii_data_temp_r3 = result
            self.update_data_signal.emit(self.flag_door_test, 2, str(self.ascii_data_tx0_r3), str(self.ascii_data_tx1_r3), str(self.ascii_data_tx2_r3), str(self.ascii_data_temp_r3))
            self.status_signal.emit(RR, self.dev_id, True)
        else:
            pass
    def tailgate_data_processing(self, msg_id, msg_data):
        if msg_id == 0x1FF11400:
            if not self.flag_TG_on:
                self.flag_TG_on = True
                self.flag_TG_on_once = True
                self.count_TG_pre_request = 0
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            if data_code == "Tx0":
                self.ascii_data_tx0 = result
            elif data_code == "Tx1":
                self.ascii_data_tx1 = result
            elif data_code == "Tx2":
                self.ascii_data_tx2 = result
            elif data_code == "Temp":
                self.ascii_data_temp = result
            self.update_data_signal.emit(self.flag_door_test, self.dev_id, str(self.ascii_data_tx0), str(self.ascii_data_tx1), str(self.ascii_data_tx2), str(self.ascii_data_temp))
            self.status_signal.emit(TG, self.dev_id, True)        
        else:
            pass

    def get_txpower_temp(self, msg_id, msg_data):
        # Tx0 Power
        if msg_data[4] == 0x30 and msg_data[5] == 0x50 and msg_data[6] == 0x6F and msg_data[7] == 0x77 and msg_data[8] == 0x65 and msg_data[9] == 0x72:
            data_code = "Tx0"
            tx0_data_hex = msg_data[17:21]
            ascii_data_tx0 = tx0_data_hex.tobytes().decode('ascii')
            if self.flag_door_test:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx0 Power : {ascii_data_tx0} [dBm]")
            else:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}_{self.dev_id}] Tx0 Power : {ascii_data_tx0} [dBm]")
            try:
                if float(ascii_data_tx0) < TX_POWER_LIMIT[0] or float(ascii_data_tx0) > TX_POWER_LIMIT[1]:
                    self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx0 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            except ValueError:
                self.log_signal.emit(1, "Error occured : Tx0 Power")
            return data_code, ascii_data_tx0
        # Tx1 Power
        elif msg_data[5] == 0x31 and msg_data[6] == 0x50 and msg_data[7] == 0x6F and msg_data[8] == 0x77 and msg_data[9] == 0x65 and msg_data[10] == 0x72:
            data_code = "Tx1"
            tx1_data_hex = msg_data[18:22]
            ascii_data_tx1 = tx1_data_hex.tobytes().decode('ascii')
            if self.flag_door_test:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx1 Power : {ascii_data_tx1} [dBm]")
            else:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}_{self.dev_id}] Tx1 Power : {ascii_data_tx1} [dBm]")
            try:
                if float(ascii_data_tx1) < TX_POWER_LIMIT[0] or float(ascii_data_tx1) > TX_POWER_LIMIT[1]:
                    self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx1 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            except ValueError:
                self.log_signal.emit(1, "Error occured : Tx1 Power")            
            return data_code, ascii_data_tx1
        # Tx2 Power
        elif msg_data[6] == 0x32 and msg_data[7] == 0x50 and msg_data[8] == 0x6F and msg_data[9] == 0x77 and msg_data[10] == 0x65 and msg_data[11] == 0x72:
            data_code = "Tx2"
            tx2_data_hex = msg_data[19:23]
            ascii_data_tx2 = tx2_data_hex.tobytes().decode('ascii')
            if self.flag_door_test:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx2 Power : {ascii_data_tx2} [dBm]")
            else:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}_{self.dev_id}] Tx2 Power : {ascii_data_tx2} [dBm]")
            try:
                if float(ascii_data_tx2) < TX_POWER_LIMIT[0] or float(ascii_data_tx2) > TX_POWER_LIMIT[1]:
                    self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx2 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            except ValueError:
                self.log_signal.emit(1, "Error occured : Tx2 Power")
            return data_code, ascii_data_tx2
        # Temperature
        elif msg_data[8] == 0x54 and msg_data[9] == 0x65 and msg_data[10] == 0x6D and msg_data[11] == 0x70 and msg_data[12] == 0x65:
            data_code = "Temp"
            temp_data_hex = msg_data[21:26]
            ascii_data_temp = temp_data_hex.tobytes().decode('ascii')
            if self.flag_door_test:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Temperature : {ascii_data_temp} [℃]")
            else:
                self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}_{self.dev_id}] Temperature : {ascii_data_temp} [℃]")
            if self.flag_door_test:
                self.resend_signal.emit(msg_id)
            else:   # Tailgate test
                self.resend_signal.emit(self.dev_id)
            
            try:
                if float(ascii_data_temp) < TEMP_LIMIT[0] or float(ascii_data_temp) > TEMP_LIMIT[1]:
                    self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Temperature over the limit (MIN/MAX : {TEMP_LIMIT[0]}/{TEMP_LIMIT[1]})")
            except ValueError:
                self.log_signal.emit(1, "Error occured : Temperature")
            return data_code, ascii_data_temp
        # GPADC
        # elif msg_data[8] == 0x47 and msg_data[9] == 0x50 and msg_data[10] == 0x41 and msg_data[11] == 0x44 and msg_data[12] == 0x43:
            # pass
        elif msg_data[9] == 0x5B and msg_data[10] == 0x54 and msg_data[11] == 0x65 and msg_data[12] == 0x6D and msg_data[13] == 0x70:
            # Send ACK message
            if self.flag_door_test:
                self.resend_signal.emit(msg_id)
            else:   # Tailgate test
                self.resend_signal.emit(self.dev_id)
            data_code = "etc"
            result = 0
            return data_code, result
        elif  msg_data[8] == 0x57 and msg_data[9] == 0x61 and msg_data[10] == 0x72 and msg_data[11] == 0x6E and msg_data[12] == 0x69:
            # Send ACK message
            if self.flag_door_test:
                self.resend_signal.emit(msg_id)
            else:   # Tailgate test
                self.resend_signal.emit(self.dev_id)
            data_code = "etc"
            result = 0
            return data_code, result
        else:
            data_code = "etc"
            result = 0
            return data_code, result
        
    def control_act_deact(self, onOffStatus):
        # self.log_signal.emit(0, f"[THREAD_READ] On/Off Signal recieved : {onOffStatus}")
        if onOffStatus: # ON
            self.flag_act = True
        else:           # OFF
            self.flag_act = False

    def resend_request(self):
        self.flag_status_update_FL = False
        self.flag_status_update_FR = False
        self.flag_status_update_RR = False
        self.flag_status_update_TG = False

        if self.flag_act:
            if self.flag_door_test:
                if not self.flag_FL_on:
                    self.count_FL_pre_request += 1                    
                if not self.flag_FR_on:
                    self.count_FR_pre_request += 1
                if not self.flag_RR_on:
                    self.count_RR_pre_request += 1
            else:   # Tailgate test
                if not self.flag_TG_on:
                    self.count_TG_pre_request += 1

            if self.flag_door_test:
                self.flag_FL_on = False
                self.flag_FR_on = False
                self.flag_RR_on = False
            else:   # Tailgate test
                self.flag_TG_on = False                

            if self.flag_door_test:
                if self.count_FL_pre_request > 2:
                    # self.log_signal.emit(0, "[READ] FL pre resend request")
                    self.resend_signal.emit(111)
                    self.count_FL_pre_request = 0
                    self.status_signal.emit(FL, self.dev_id, False)
                elif self.count_FR_pre_request > 2:
                    # self.log_signal.emit(0, "[READ] FR pre resend request")
                    self.resend_signal.emit(222)
                    self.count_FR_pre_request = 0
                    self.status_signal.emit(FR, self.dev_id, False)
                elif self.count_RR_pre_request > 2:
                    # self.log_signal.emit(0, "[READ] RR pre resend request")
                    self.resend_signal.emit(333)
                    self.count_RR_pre_request = 0
                    self.status_signal.emit(RR, self.dev_id, False)
            else:   # Tailgate test
                if self.count_TG_pre_request > 2 and self.dev_id == 0:
                    # self.log_signal.emit(0, f"[READ] TG#1 pre resend request")
                    self.resend_signal.emit(444)
                    self.count_TG_pre_request = 0
                    self.status_signal.emit(TG, self.dev_id, False)
                elif self.count_TG_pre_request > 2 and self.dev_id == 1:
                    # self.log_signal.emit(0, f"[READ] TG#2 pre resend request")
                    self.resend_signal.emit(555)
                    self.count_TG_pre_request = 0
                    self.status_signal.emit(TG, self.dev_id, False)
                elif self.count_TG_pre_request > 2 and self.dev_id == 2:
                    # self.log_signal.emit(0, f"[READ] TG#3 pre resend request")
                    self.resend_signal.emit(666)
                    self.count_TG_pre_request = 0
                    self.status_signal.emit(TG, self.dev_id, False)
        
        # else:   # Deact
        #     if self.flag_cmd_resend:
        #         if self.flag_door_test:
        #             self.log_signal.emit(0, "[READ] Deact resend request")
        #             self.resend_signal.emit(self.dev_id, False)  # Deact request
        #         else:   # Tailgate test
        #             pass
                

    def stop(self):
        self.running = False

# NOTE :: StatusGUI
class StatusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # uic.loadUi("Status_Logging_GUI.ui", self)
        
        # Set fixed UI path for exe file
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")

        ui_path = os.path.join(base_path, "Status_Logging_GUI.ui")
        uic.loadUi(ui_path, self)

        # Check logfile path, if there is no directory, generate new folder
        self.data_logfolder_path = "./LogFiles/DataLog"
        if not os.path.exists(self.data_logfolder_path):
            os.makedirs(self.data_logfolder_path)

        self.can_logfolder_path = "./LogFiles/CanLog"
        if not os.path.exists(self.can_logfolder_path):
            os.makedirs(self.can_logfolder_path)

        self.sys_logfolder_path = "./LogFiles/SysLog"
        if not os.path.exists(self.sys_logfolder_path):
            os.makedirs(self.sys_logfolder_path)

        self.init_ui()      # Initialize
        self.thread_list = []   # Only for thread managing
        self.read_worker_dict = {}
        self.write_worker = None
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
        self.flag_inner_on_time = True
        self.flag_work_outer_cycle = False
        self.flag_saveSyslog = True
        self.flag_door_test = True
        self.flag_test_finished = False
        self.flag_on = False
        self.flag_pre_wait = False
        self.manualMode = True
        self.flag_preTest = False
        self.flag_pre_on = True
        self.flag_pre_test_finished = False        
        
        # Initialize variables
        self.connected_dev_id = []
        self.pcan_handle_dict = {}
        self.connected_dev_dict = {1:0, 2:0, 3:0}
        self.operation_timer = 0
        self.pre_on_time = 0
        self.pre_off_time = 0
        self.inner_on_time = 0
        self.inner_off_time = 0
        self.num_pre_cycle = 0
        self.num_inner_cycle = 0
        self.numOuterCycle = 0
        self.outerOffTime = 0
        self.crnt_pre_cycle = 0
        self.crnt_inner_cycle = 0
        self.crntOuterCycle = 0
        self.pre_test_timer = 0
        self.inner_cycle_timer = 0
        self.outer_cycle_timer = 0
        self.totalTestTime = 0
        self.total_time_pre = 0
        self.total_time_inner = 0
        self.total_time_outer = 0
        self.status_FL = None
        self.status_FR = None
        self.status_RR = None
        self.status_TG1 = None
        self.status_TG2 = None
        self.status_TG3 = None
        self.max_logFile_size = 10*1024*1024

        # Initial font setting
        self.lab_programStatus.setFont(QFont("한컴 고딕", 16, QFont.Bold))
        self.lab_programStatus.setAlignment(Qt.AlignCenter)
        
        # Initialize status
        self.lab_timer.hide()
        self.label_r1_status0.hide()
        self.label_r1_status1.hide()
        self.label_r1_status2.hide()
        self.label_r1_status3.hide()
        self.label_r1_status4.hide()
        self.label_r2_status0.hide()
        self.label_r2_status1.hide()
        self.label_r2_status2.hide()
        self.label_r2_status3.hide()
        self.label_r2_status4.hide()
        self.label_r3_status0.hide()
        self.label_r3_status1.hide()
        self.label_r3_status2.hide()
        self.label_r3_status3.hide()
        self.label_r3_status4.hide()
        self.lab_timer.setAlignment(Qt.AlignCenter)
        self.btn_stop.setEnabled(False)
        self.btn_unlock.setEnabled(False)

        # Initialize system related buttons/labels
        self.cmb_modeSelection.currentIndexChanged.connect(self.func_modeSelection)
        self.checkBox_InnerMode.stateChanged.connect(self.toggle_test_mode_setting)
        self.checkBox_preTestMode.stateChanged.connect(self.toggle_pre_test_mode_setting)

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
        # self.btn_canConnectionCheck.clicked.connect(self.can_connection_check)
        self.btn_clearSysLog.clicked.connect(self.clearSysLog)
        self.btn_clearCanLog.clicked.connect(self.clearCanLog)
        self.btn_clearCriLog.clicked.connect(self.clearCriLog)
        self.btn_R1_preRqst.clicked.connect(self.send_pre_rqst1)
        self.btn_R2_preRqst.clicked.connect(self.send_pre_rqst2)
        self.btn_R3_preRqst.clicked.connect(self.send_pre_rqst3)

        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{self.select_date}_{select_time}")
        self.line_logFilePath.setText(self.can_logfolder_path)
        self.line_sysLogFilePath.setText(self.sys_logfolder_path)
        self.line_innerOnTime.textChanged.connect(self.update_test_setting)
        self.line_innerOffTime.textChanged.connect(self.update_test_setting)
        self.line_numInnerCycle.textChanged.connect(self.update_test_setting)
        self.line_outerOffTime.textChanged.connect(self.update_test_setting)
        self.line_numOuterCycle.textChanged.connect(self.update_test_setting)
        self.line_preOnTime.textChanged.connect(self.update_test_setting)
        self.line_preOffTime.textChanged.connect(self.update_test_setting)
        self.line_numPreCycle.textChanged.connect(self.update_test_setting)
        self.line_preWaitTime.textChanged.connect(self.update_test_setting)

        self.radioBtn_door.toggled.connect(self.update_num_dev)
        self.radioBtn_tailgate.toggled.connect(self.update_num_dev)
        self.radioBtn_manualMode.toggled.connect(self.update_operation_mode)
        self.radioBtn_autoMode.toggled.connect(self.update_operation_mode)
        self.radioBtn_sysLogMon.toggled.connect(self.update_syslog_mode)
        self.radioBtn_sysLogSave.toggled.connect(self.update_syslog_mode)
        self.lab_version.setText(version)
        self.progressBar.setValue(0)
        
        # Generate logger instance for logging
        self.oper_logger = logging.getLogger('OPERTATION_LOG')
        self.oper_logger.setLevel(logging.DEBUG)

        self.cri_logger = logging.getLogger('CRITICAL_LOG')
        self.cri_logger.setLevel(logging.DEBUG)

        self.sys_logger = logging.getLogger('SYSTEM_LOG')
        self.sys_logger.setLevel(logging.DEBUG)
        sys_logger_filename = self.line_sysLogFilePath.text() + '/SYSTEM_LOG_' + self.select_date + '.log'
        self.sys_log_handler = logging.handlers.RotatingFileHandler(filename=sys_logger_filename, mode='a', maxBytes=self.max_logFile_size)
        sys_formatter = logging.Formatter(fmt='%(asctime)s > %(message)s')
        self.sys_log_handler.setFormatter(sys_formatter)
        self.sys_logger.addHandler(self.sys_log_handler)

    def clearSysLog(self):
        self.txtEdit_sysLog.clear()

    def clearCanLog(self):
        self.txtEdit_canLog.clear()

    def clearCriLog(self):
        self.txtEdit_criLog.clear()

    def send_pre_rqst1(self):
        if self.flag_door_test:
            msg_id_FL = DOOR_FL_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, "[MAIN] Button clicked : FL power, temp request")
            else:
                pass
        else:   # Tailgate test
            msg_id = TAILGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id, dlc, msg_frame_pre3)            
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, f"[MAIN] Button clicked : TG#1 power, temp request")
            else:
                pass

    def send_pre_rqst2(self):
        if self.flag_door_test:
            msg_id_FR = DOOR_FR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, "[MAIN] Button clicked : FR power, temp request")
            else:
                pass
        else:
            msg_id = TAILGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[1], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[1], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[1], msg_id, dlc, msg_frame_pre3)            
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, "[MAIN] Button clicked : TG#2 power, temp request")
            else:
                pass

    def send_pre_rqst3(self):
        if self.flag_door_test:
            msg_id_RR = DOOR_RR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, "[MAIN] Button clicked : RR power, temp request")
            else:
                pass
        else:
            msg_id = TAILGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[2], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[2], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[2], msg_id, dlc, msg_frame_pre3)            
            if error_ok == PCAN_ERROR_OK:
                self.print_log(0, "[MAIN] Button clicked : TG#3 power, temp request")
            else:
                pass

    def update_operation_display(self):
        hours = self.operation_timer // 3600
        mins = (self.operation_timer % 3600) // 60
        secs = self.operation_timer % 60
        self.lab_timer.setText(f"{hours:04}:{mins:02}:{secs:02}")

    def func_emit_onOffStatus(self, onOffStatus):
        # Emit on/off signal to CAN write worker
        # self.print_log(0, f"[MAIN] On/Off Signal send : {onOffStatus}")
        self.write_worker.onOff_signal.emit(onOffStatus)
        
        # self.lab_Rdr1_txPwr1.setText("0")
        # self.lab_Rdr1_txPwr2.setText("0")
        # self.lab_Rdr1_txPwr3.setText("0")
        # self.lab_Rdr1_tmp.setText("0")
        # self.lab_Rdr2_txPwr1.setText("0")
        # self.lab_Rdr2_txPwr2.setText("0")
        # self.lab_Rdr2_txPwr3.setText("0")
        # self.lab_Rdr2_tmp.setText("0")    
        # self.lab_Rdr3_txPwr1.setText("0")
        # self.lab_Rdr3_txPwr2.setText("0")
        # self.lab_Rdr3_txPwr3.setText("0")
        # self.lab_Rdr3_tmp.setText("0")

    def get_label_value(self, label: QtWidgets.QLabel) -> float:
        data = label.text()
        try:
            return float(data)
        except ValueError:
            return 0
        
    def save_csv_data(self):
        current_time = QTime.currentTime().toString("hh:mm:ss")
        if self.flag_on:
            r1_tx0 = self.get_label_value(self.lab_Rdr1_txPwr1)
            r1_tx1 = self.get_label_value(self.lab_Rdr1_txPwr2)
            r1_tx2 = self.get_label_value(self.lab_Rdr1_txPwr2)
            r1_temp = self.get_label_value(self.lab_Rdr1_tmp)
            r2_tx0 = self.get_label_value(self.lab_Rdr2_txPwr1)
            r2_tx1 = self.get_label_value(self.lab_Rdr2_txPwr2)
            r2_tx2 = self.get_label_value(self.lab_Rdr2_txPwr3)
            r2_temp = self.get_label_value(self.lab_Rdr2_tmp)
            r3_tx0 = self.get_label_value(self.lab_Rdr3_txPwr1)
            r3_tx1 = self.get_label_value(self.lab_Rdr3_txPwr2)
            r3_tx2 = self.get_label_value(self.lab_Rdr3_txPwr3)
            r3_temp = self.get_label_value(self.lab_Rdr3_tmp)

            if self.flag_door_test:
                r1_row = [current_time, r1_tx0, r1_tx1, r1_tx2, r1_temp, self.status_FL]
                r2_row = [current_time, r2_tx0, r2_tx1, r2_tx2, r2_temp, self.status_FR]
                r3_row = [current_time, r3_tx0, r3_tx1, r3_tx2, r3_temp, self.status_RR]
            else:   # Tailgate test
                r1_row = [current_time, r1_tx0, r1_tx1, r1_tx2, r1_temp, self.status_TG1]
                r2_row = [current_time, r2_tx0, r2_tx1, r2_tx2, r2_temp, self.status_TG2]
                r3_row = [current_time, r3_tx0, r3_tx1, r3_tx2, r3_temp, self.status_TG3]
        else:
            r1_row = [current_time, 0, 0, 0, 0, "IDLE"]
            r2_row = [current_time, 0, 0, 0, 0, "IDLE"]
            r3_row = [current_time, 0, 0, 0, 0, "IDLE"]

        with open(self.Radar1_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(r1_row)
        with open(self.Radar2_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(r2_row)
        with open(self.Radar3_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(r3_row)

    def preTest_work(self):
        if not self.flag_pre_wait:
            if self.flag_pre_on:
                if self.pre_test_timer < self.pre_on_time - 1:
                    self.line_remainTime.setText(f"{self.pre_on_time - self.pre_test_timer}")
                    self.line_currentMode.setText("PreOn")
                    self.pre_test_timer += 1
                else:
                    self.pre_test_timer = 0
                    self.line_remainTime.setText("1")
                    self.flag_on = False
                    self.func_emit_onOffStatus(self.flag_on)
                    self.flag_pre_on = False
            else:
                if self.pre_test_timer < self.pre_off_time - 1:
                    self.line_remainTime.setText(f"{self.pre_off_time - self.pre_test_timer}")
                    self.line_currentMode.setText("PreOff")
                    self.pre_test_timer += 1
                else:
                    self.pre_test_timer = 0
                    self.crnt_pre_cycle += 1
                    self.line_remainTime.setText("1")

                    # Update current/remain cycle in GUI
                    self.line_currentPreCycle.setText(f"{self.crnt_pre_cycle}")
                    self.line_remainPreCycle.setText(f"{self.num_pre_cycle-self.crnt_pre_cycle}")

                    if self.crnt_pre_cycle < self.num_pre_cycle:
                        self.flag_on = True
                        self.func_emit_onOffStatus(self.flag_on)
                        self.flag_pre_on = True
                        self.print_log(0, f"[MAIN] Current Pre Cycle : {self.crnt_pre_cycle} / Total Pre Cycle : {self.num_pre_cycle}")
                    else:
                        self.crnt_pre_cycle = 0
                        if self.pre_wait_time:
                            self.flag_pre_wait = True
                        else:
                            self.flag_on = True
                            self.func_emit_onOffStatus(self.flag_on)
                            self.flag_pre_test_finished = True
        else:
            if self.pre_test_timer < self.pre_wait_time - 1:
                self.line_remainTime.setText(f"{self.pre_wait_time - self.pre_test_timer}")
                self.line_currentMode.setText("PreWait")
                self.pre_test_timer += 1
            else:
                self.pre_test_timer = 0
                self.line_remainTime.setText("1")
                self.flag_on = True
                self.func_emit_onOffStatus(self.flag_on)
                self.flag_pre_on = True
                self.flag_pre_wait = False
                self.flag_pre_test_finished = True

    def inner_cycle_work(self):
        if self.flag_inner_on_time:
            if self.inner_cycle_timer < self.inner_on_time - 1:
                self.line_remainTime.setText(f"{self.inner_on_time - self.inner_cycle_timer}")
                self.line_currentMode.setText("InOn")
                self.inner_cycle_timer += 1
            else:                
                self.inner_cycle_timer = 0
                self.line_remainTime.setText("1")
                self.flag_on = False
                self.func_emit_onOffStatus(self.flag_on)
                self.flag_inner_on_time = False
        else:
            if self.inner_cycle_timer < self.inner_off_time - 1:
                self.line_remainTime.setText(f"{self.inner_off_time - self.inner_cycle_timer}")
                self.line_currentMode.setText("InOff")
                self.inner_cycle_timer += 1
            else:
                self.inner_cycle_timer = 0
                self.crnt_inner_cycle += 1
                self.line_remainTime.setText("1")
                
                # Update current/remain cycle in GUI
                self.line_currentCycle.setText(f"{self.crnt_inner_cycle}")
                self.line_remainCycle.setText(f"{self.num_inner_cycle-self.crnt_inner_cycle}")

                if self.crnt_inner_cycle < self.num_inner_cycle:
                    self.flag_on = True
                    self.func_emit_onOffStatus(self.flag_on)
                    self.flag_inner_on_time = True
                    self.print_log(0, f"[MAIN] Current Inner Cycle : {self.crnt_inner_cycle} / Total Inner Cycle : {self.num_inner_cycle}")
                else:                    
                    self.crnt_inner_cycle = 0
                    if self.flag_innerCycle:
                        self.flag_test_finished = True
                        self.print_log(0, "[MAIN] Test completed")
                        self.func_unlock()
                        self.func_stop()                        
                    else:
                        self.flag_work_outer_cycle = True
    
    def outer_cycle_work(self):
        if self.flag_work_outer_cycle == False:
                self.inner_cycle_work()
        else:
            if self.outer_cycle_timer < self.outerOffTime - 1:
                self.line_remainTime.setText(f"{self.outerOffTime - self.outer_cycle_timer}")
                self.line_currentMode.setText("OutOff")
                self.outer_cycle_timer += 1
            else:
                self.outer_cycle_timer = 0
                self.crntOuterCycle += 1
                self.line_remainTime.setText("1")
                self.flag_work_outer_cycle = False

                # Update current/remain cycle in GUI
                self.line_currentOutCycle.setText(f"{self.crntOuterCycle}")
                self.line_remainOutCycle.setText(f"{self.numOuterCycle-self.crntOuterCycle}")

                if self.crntOuterCycle < self.numOuterCycle:
                    self.flag_on = True
                    self.flag_inner_on_time = True
                    self.func_emit_onOffStatus(self.flag_on)
                    self.print_log(0, f"[MAIN] Current Outer Cycle : {self.crntOuterCycle} / Total Outer Cycle : {self.numOuterCycle}")
                else:
                    self.crntOuterCycle = 0
                    self.flag_test_finished = True
                    self.print_log(0, "[MAIN] Test completed")
                    self.func_unlock()
                    self.func_stop()

    def cycle_counter(self):
        if self.line_innerOnTime.text().strip():
            if self.flag_preTest:
                if not self.flag_pre_test_finished:
                    self.preTest_work()
                else:
                    if self.flag_innerCycle:
                        self.inner_cycle_work()
                    else:
                        self.outer_cycle_work()
            else:   # Without pretest
                if self.flag_innerCycle:
                    self.inner_cycle_work()
                else:
                    self.outer_cycle_work()
        else:   # Case that user want continuous operation
            pass

    def update_time(self):
        if self.flag_start:
            self.operation_timer += 1
            # self.print_log(0, f"{self.operation_timer}")
            if self.totalTestTime:
                progressVal = int((self.operation_timer / self.totalTestTime) * 100)
                self.progressBar.setValue(progressVal)
            self.update_operation_display()
            self.cycle_counter()
            self.save_csv_data()

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

    def toggle_pre_test_mode_setting(self, state):
        if state == Qt.Checked:
            self.groupBox_preTest.setDisabled(False)
            self.flag_preTest = True
        else:
            self.groupBox_preTest.setDisabled(True)
            self.flag_preTest = False

    def update_test_setting(self):
        if self.flag_preTest:
            try:    # If input value is not integer, consider 0
                self.pre_on_time = int(self.line_preOnTime.text()) if self.line_preOnTime.text().isdigit() else 0
                self.pre_off_time = int(self.line_preOffTime.text()) if self.line_preOffTime.text().isdigit() else 0
                self.num_pre_cycle = int(self.line_numPreCycle.text()) if self.line_numPreCycle.text().isdigit() else 0
                self.pre_wait_time = int(self.line_preWaitTime.text()) if self.line_preWaitTime.text().isdigit() else 0

                # Update result to line_totalInnerCycleTime
                self.total_time_pre = ((self.pre_on_time + self.pre_off_time) * self.num_pre_cycle) + self.pre_wait_time
                self.line_totalPreCycleTime.setText(str(self.total_time_pre))

            except ValueError:  # If occur exclude case, consider 0
                self.line_totalPreCycleTime.setText("0")
                
        try:
            self.inner_on_time = int(self.line_innerOnTime.text()) if self.line_innerOnTime.text().isdigit() else 0
            self.inner_off_time = int(self.line_innerOffTime.text()) if self.line_innerOffTime.text().isdigit() else 0
            self.num_inner_cycle = int(self.line_numInnerCycle.text()) if self.line_numInnerCycle.text().isdigit() else 0            
            
            self.total_time_inner = (self.inner_on_time + self.inner_off_time) * self.num_inner_cycle
            self.line_totalInnerCycleTime.setText(str(self.total_time_inner))

            if self.flag_preTest:
                self.total_time_inner += self.total_time_pre

            hours = self.total_time_inner // 3600
            mins = (self.total_time_inner % 3600) // 60
            secs = self.total_time_inner % 60
            self.line_totalTestTime.setText(f"{hours}시간 {mins}분 {secs}초")
            
            self.totalTestTime = self.total_time_inner
        
        except ValueError:
            self.line_totalInnerCycleTime.setText("0")
        
        if self.flag_innerCycle == False:
            try:
                self.outerOffTime = int(self.line_outerOffTime.text()) if self.line_outerOffTime.text().isdigit() else 0
                self.numOuterCycle = int(self.line_numOuterCycle.text()) if self.line_numOuterCycle.text().isdigit() else 0

                self.total_time_outer = ((self.inner_on_time + self.inner_off_time) * self.num_inner_cycle + self.outerOffTime) * self.numOuterCycle
                self.line_totalOuterCycleTime.setText(str(self.total_time_outer))

                if self.flag_preTest:
                    self.total_time_outer += self.total_time_pre

                hours = self.total_time_outer // 3600
                mins = (self.total_time_outer % 3600) // 60
                secs = self.total_time_outer % 60
                self.line_totalTestTime.setText(f"{hours}시간 {mins}분 {secs}초")

                self.totalTestTime = self.total_time_outer

            except ValueError:
                self.line_totalOuterCycleTime.setText("0")

    def clear_cycle_setting(self):
        if self.flag_preTest:
            self.line_preOnTime.setText("")
            self.line_preOffTime.setText("")
            self.line_numPreCycle.setText("")
            self.line_preWaitTime.setText("")
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
            self.radioBtn_tailgate.setChecked(False)
            self.groupBox_canDev2.setEnabled(False)
            self.groupBox_canDev3.setEnabled(False)
            self.line_radar1.setText("FL")
            self.line_radar2.setText("FR")
            self.line_radar3.setText("RR")
        else:   # Tailgate test
            self.flag_door_test = False
            self.radioBtn_door.setChecked(False)
            self.groupBox_canDev2.setEnabled(True)
            self.groupBox_canDev3.setEnabled(True)
            self.line_radar1.setText("TG1")
            self.line_radar2.setText("TG2")
            self.line_radar3.setText("TG3")

    def update_operation_mode(self):
        if self.radioBtn_manualMode.isChecked():
            self.radioBtn_autoMode.setChecked(False)
            self.group_customModeSetting.setEnabled(True)
            self.manualMode = True
        else:   # Auto mode
            self.radioBtn_manualMode.setChecked(False)
            self.group_customModeSetting.setDisabled(True)
            self.manualMode = False
    
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

            sysLogMsg = f"[MAIN] CAN device disconnected : {dev_id}"
            self.print_log(0, sysLogMsg)
            return True
        else:
            sysLogMsg = f"[MAIN] CAN device disconnect failed : {dev_id}"
            self.print_log(0, sysLogMsg)
            return False

    def connect_can_dev(self, dev_id, radar_id):
        if dev_id in self.connected_dev_id:
            sysLogMsg = f"[MAIN] CAN device already connected : {dev_id}"
            self.print_log(0, sysLogMsg)
            return False
        else:
            connect_result = self.pcan_ctrl.initialize(dev_id=dev_id)
            
            if connect_result:
                self.connected_dev_id.append(dev_id)
                self.connected_dev_dict[radar_id] = dev_id
                sysLogMsg = f"[MAIN] CAN device connected : {dev_id}"
                self.print_log(0, sysLogMsg)
                return True
            else:
                sysLogMsg = f"[MAIN] CAN device connect failed : {dev_id}"
                self.print_log(0, sysLogMsg)
                return False
    
    def update_can_dev1(self):
        dev_id = self.spinBox_devID1.value()
        if self.btn_device1.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 1)
            if retVal:  # Succeed
                self.spinBox_devID1.setEnabled(False)
                self.pcan_handle_dict[dev_id] = 0
            else:       # Failed
                self.btn_device1.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 1)
            if retVal:  # Succeed
                self.spinBox_devID1.setEnabled(False)
                del self.pcan_handle_dict[dev_id]
            else:       # Failed
                self.btn_device1.toggle()

    def update_can_dev2(self):
        dev_id = self.spinBox_devID2.value()
        if self.btn_device2.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 2)
            if retVal:  # Succeed
                self.spinBox_devID2.setEnabled(False)
                self.pcan_handle_dict[dev_id] = 0
            else:       # Failed
                self.btn_device2.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 2)
            if retVal:  # Succeed
                self.spinBox_devID2.setEnabled(False)
                del self.pcan_handle_dict[dev_id]
            else:       # Failed
                self.btn_device2.toggle()
    
    def update_can_dev3(self):
        dev_id = self.spinBox_devID3.value()
        if self.btn_device3.isChecked():    # Connect
            retVal = self.connect_can_dev(dev_id, 3)
            if retVal:  # Succeed
                self.spinBox_devID3.setEnabled(False)
                self.pcan_handle_dict[dev_id] = 0
            else:       # Failed
                self.btn_device3.toggle()
        else:                               # Disconnect
            retVal = self.disconnect_can_dev(dev_id, 3)
            if retVal:  # Succeed
                self.spinBox_devID3.setEnabled(True)
                del self.pcan_handle_dict[dev_id]
            else:       # Failed
                self.btn_device3.toggle()

    @pyqtSlot(int, int, bool)
    def show_status(self, sensorType, dev_id, status):
        if self.flag_door_test:
            if status:
                if sensorType == FL:
                    self.label_actDeact1.setStyleSheet(activate)
                elif sensorType == FR:
                    self.label_actDeact2.setStyleSheet(activate)
                elif sensorType == RR:
                    self.label_actDeact3.setStyleSheet(activate)
                else:
                    pass
            else:
                if sensorType == FL:
                    self.label_actDeact1.setStyleSheet(sleep)
                elif sensorType == FR:
                    self.label_actDeact2.setStyleSheet(sleep)
                elif sensorType == RR:
                    self.label_actDeact3.setStyleSheet(sleep)
                else:
                    pass
        else:   # Tailgate test
            if status:
                if dev_id == 0:
                    self.label_actDeact1.setStyleSheet(activate)
                elif dev_id == 1:
                    self.label_actDeact2.setStyleSheet(activate)
                elif dev_id == 2:
                    self.label_actDeact3.setStyleSheet(activate)
                else:
                    pass
            else:
                if dev_id == 0:
                    self.label_actDeact1.setStyleSheet(sleep)
                elif dev_id == 1:
                    self.label_actDeact2.setStyleSheet(sleep)
                elif dev_id == 2:
                    self.label_actDeact3.setStyleSheet(sleep)
                else:
                    pass


    def print_log(self, category, message):
        # Print log to the textEdit
        date = datetime.datetime.now()
        logging_date = date.strftime("%Y.%m.%d")
        logging_time = QTime.currentTime().toString("hh:mm:ss")

        # Limit the number of lines in the textEdit to avoid memory overflow
        max_log_lines = 1000

        # category 0 : System log 
        if category == 0:
            # self.txtEdit_sysLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_sysLog.append(f"[{logging_time}] {message}")
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
            # self.txtEdit_canLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_canLog.append(f"[{logging_time}] {message}")
            self.txtEdit_canLog.ensureCursorVisible()
            if self.txtEdit_canLog.document().blockCount() > max_log_lines:
                can_cursor = self.txtEdit_canLog.textCursor()
                can_cursor.movePosition(can_cursor.Start)
                can_cursor.select(can_cursor.BlockUnderCursor)
                can_cursor.removeSelectedText()   
            self.oper_logger.debug(message)
        # category 2 : CAN critical log
        elif category == 2:
            # self.txtEdit_criLog.append(f"[{logging_date}_{logging_time}] {message}")
            self.txtEdit_criLog.append(f"[{logging_time}] {message}")
            self.txtEdit_criLog.ensureCursorVisible()
            if self.txtEdit_criLog.document().blockCount() > max_log_lines:
                cri_cursor = self.txtEdit_criLog.textCursor()
                cri_cursor.movePosition(cri_cursor.Start)
                cri_cursor.select(cri_cursor.BlockUnderCursor)
                cri_cursor.removeSelectedText()
            self.cri_logger.debug(message)

    def func_modeSelection(self, index):
        date = datetime.datetime.now()
        select_date = date.strftime("%y.%m.%d")
        select_time = QTime.currentTime().toString("hh.mm.ss")
        self.line_logFileName.setText(self.cmb_modeSelection.currentText() + f"_{select_date}_{select_time}")

        if not self.manualMode:
            if index == 15:
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("1440")
            elif index == 16:
                self.checkBox_preTestMode.setChecked(True)
                self.line_preOnTime.setText("0")
                self.line_preOffTime.setText("7200")
                self.line_numPreCycle.setText("1")
                self.line_preWaitTime.setText("0")
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("3240")
            elif index == 20:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("30")
                self.line_outerOffTime.setText("3000")
                self.line_numOuterCycle.setText("96")
            elif index in [22, 29]:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("30")
                self.line_outerOffTime.setText("3000")
                self.line_numOuterCycle.setText("24")
            elif index == 25:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("15")
                self.line_outerOffTime.setText("300")
                self.line_numOuterCycle.setText("100")
            elif index == 26:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("45")
                self.line_outerOffTime.setText("900")
                self.line_numOuterCycle.setText("4")
            elif index == 28:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("360")
                self.line_outerOffTime.setText("604800")
                self.line_numOuterCycle.setText("4")
            elif index == 32:
                self.checkBox_InnerMode.setChecked(False)
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("30")
                self.line_outerOffTime.setText("3000")
                self.line_numOuterCycle.setText("1000")
            elif index == 21:
                self.checkBox_preTestMode.setChecked(True)
                self.line_preOnTime.setText("8")
                self.line_preOffTime.setText("12")
                self.line_numPreCycle.setText("2700")
                self.line_preWaitTime.setText("28800")
                self.line_innerOnTime.setText("8")
                self.line_innerOffTime.setText("12")
                self.line_numInnerCycle.setText("2880")
                self.line_outerOffTime.setText("28800")
                self.line_numOuterCycle.setText("10")
            else:
                self.line_preOnTime.setText("")
                self.line_preOffTime.setText("")
                self.line_numPreCycle.setText("")
                self.line_preWaitTime.setText("")
                self.line_innerOnTime.setText("")
                self.line_innerOffTime.setText("")
                self.line_numInnerCycle.setText("")
                self.line_outerOffTime.setText("")
                self.line_numOuterCycle.setText("")

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

    def read_can_thread(self, dev_id, pcan_handle):
        # Generate QThread and Worker
        thread = QThread()
        worker = CANReadWorker(self.pcan_ctrl, dev_id, pcan_handle, self.flag_door_test)

        # Connect signals
        worker.log_signal.connect(self.print_log)
        worker.status_signal.connect(self.show_status)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(worker.deleteLater)

        # Move worker to thread
        worker.moveToThread(thread)

        # Function for CAN read data update
        worker.update_data_signal.connect(self.update_data)
        worker.update_status_signal.connect(self.update_status)
        
        # Call run when thread is started
        thread.started.connect(worker.run)
        thread.start()

        # Add thread and worker into the list for manage
        self.thread_list.append(thread)
        self.read_worker_dict[dev_id] = worker

    def update_data(self, flag_door_test, dev_id, tx0, tx1, tx2, temp):
        if flag_door_test:
            if dev_id == 0:         # FL
                self.lab_Rdr1_txPwr1.setText(tx0)
                self.lab_Rdr1_txPwr2.setText(tx1)
                self.lab_Rdr1_txPwr3.setText(tx2)
                self.lab_Rdr1_tmp.setText(temp)
            elif dev_id == 1:       # FR
                self.lab_Rdr2_txPwr1.setText(tx0)
                self.lab_Rdr2_txPwr2.setText(tx1)
                self.lab_Rdr2_txPwr3.setText(tx2)
                self.lab_Rdr2_tmp.setText(temp)
            else: # dev_id == 2     # RR
                self.lab_Rdr3_txPwr1.setText(tx0)
                self.lab_Rdr3_txPwr2.setText(tx1)
                self.lab_Rdr3_txPwr3.setText(tx2)
                self.lab_Rdr3_tmp.setText(temp)

        else:   # Tailgate test
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

    @pyqtSlot(int, int, int)
    def update_status(self, sensorType, devID, status):
        if sensorType == FL:
            if status == IDLE:
                self.status_FL = "IDLE"
                self.label_r1_status0.show()
                self.label_r1_status1.hide()
                self.label_r1_status2.hide()
                self.label_r1_status3.hide()
                self.label_r1_status4.hide()
            elif status == MEASURING:
                self.status_FL = "MEASURING"
                self.label_r1_status0.hide()
                self.label_r1_status1.show()
                self.label_r1_status2.hide()
                self.label_r1_status3.hide()
                self.label_r1_status4.hide()
            elif status == DEGRADED:
                self.status_FL = "DEGRADED"
                self.label_r1_status0.hide()
                self.label_r1_status1.hide()
                self.label_r1_status2.show()
                self.label_r1_status3.hide()
                self.label_r1_status4.hide()
            elif status == FAULT:
                self.status_FL = "FAULT"
                self.label_r1_status0.hide()
                self.label_r1_status1.hide()
                self.label_r1_status2.hide()
                self.label_r1_status3.show()
                self.label_r1_status4.hide()
            elif status == BLOCKAGE:
                self.status_FL = "BLOCKAGE"
                self.label_r1_status0.hide()
                self.label_r1_status1.hide()
                self.label_r1_status2.hide()
                self.label_r1_status3.hide()
                self.label_r1_status4.show()
            else:
                pass
        elif sensorType == FR:
            if status == IDLE:
                self.status_FR = "IDLE"
                self.label_r2_status0.show()
                self.label_r2_status1.hide()
                self.label_r2_status2.hide()
                self.label_r2_status3.hide()
                self.label_r2_status4.hide()
            elif status == MEASURING:
                self.status_FR = "MEASURING"
                self.label_r2_status0.hide()
                self.label_r2_status1.show()
                self.label_r2_status2.hide()
                self.label_r2_status3.hide()
                self.label_r2_status4.hide()
            elif status == DEGRADED:
                self.status_FR = "DEGRADED"
                self.label_r2_status0.hide()
                self.label_r2_status1.hide()
                self.label_r2_status2.show()
                self.label_r2_status3.hide()
                self.label_r2_status4.hide()
            elif status == FAULT:
                self.status_FR = "FAULT"
                self.label_r2_status0.hide()
                self.label_r2_status1.hide()
                self.label_r2_status2.hide()
                self.label_r2_status3.show()
                self.label_r2_status4.hide()
            elif status == BLOCKAGE:
                self.status_FR = "BLOCKAGE"
                self.label_r2_status0.hide()
                self.label_r2_status1.hide()
                self.label_r2_status2.hide()
                self.label_r2_status3.hide()
                self.label_r2_status4.show()
            else:
                pass
        elif sensorType == RR:
            if status == IDLE:
                self.status_RR = "IDLE"
                self.label_r3_status0.show()
                self.label_r3_status1.hide()
                self.label_r3_status2.hide()
                self.label_r3_status3.hide()
                self.label_r3_status4.hide()
            elif status == MEASURING:
                self.status_RR = "MEASURING"
                self.label_r3_status0.hide()
                self.label_r3_status1.show()
                self.label_r3_status2.hide()
                self.label_r3_status3.hide()
                self.label_r3_status4.hide()
            elif status == DEGRADED:
                self.status_RR = "DEGRADED"
                self.label_r3_status0.hide()
                self.label_r3_status1.hide()
                self.label_r3_status2.show()
                self.label_r3_status3.hide()
                self.label_r3_status4.hide()
            elif status == FAULT:
                self.status_RR = "FAULT"
                self.label_r3_status0.hide()
                self.label_r3_status1.hide()
                self.label_r3_status2.hide()
                self.label_r3_status3.show()
                self.label_r3_status4.hide()
            elif status == BLOCKAGE:
                self.status_RR = "BLOCKAGE"
                self.label_r3_status0.hide()
                self.label_r3_status1.hide()
                self.label_r3_status2.hide()
                self.label_r3_status3.hide()
                self.label_r3_status4.show()
            else:
                pass
        elif sensorType == TG:
            if self.connected_dev_id[0] == devID:
                if status == IDLE:
                    self.status_TG1 = "IDLE"
                    self.label_r1_status0.show()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == MEASURING:
                    self.status_TG1 = "MEASURING"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.show()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == DEGRADED:
                    self.status_TG1 = "DEGRADED"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.show()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == FAULT:
                    self.status_TG1 = "FAULT"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.show()
                    self.label_r1_status4.hide()
                elif status == BLOCKAGE:
                    self.status_TG1 = "BLOCKAGE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.show()
                else:
                    pass
            elif self.connected_dev_id[1] == devID:
                if status == IDLE:
                    self.status_TG2 = "IDLE"
                    self.label_r1_status0.show()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == MEASURING:
                    self.status_TG2 = "IDLE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.show()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == DEGRADED:
                    self.status_TG2 = "IDLE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.show()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == FAULT:
                    self.status_TG2 = "IDLE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.show()
                    self.label_r1_status4.hide()
                elif status == BLOCKAGE:
                    self.status_TG2 = "IDLE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.show()
                else:
                    pass
            elif self.connected_dev_id[2] == devID:
                if status == IDLE:
                    self.status_TG3 = "IDLE"
                    self.label_r1_status0.show()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == MEASURING:
                    self.status_TG3 = "MEASURING"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.show()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == DEGRADED:
                    self.status_TG3 = "DEGRADED"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.show()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.hide()
                elif status == FAULT:
                    self.status_TG3 = "FAULT"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.show()
                    self.label_r1_status4.hide()
                elif status == BLOCKAGE:
                    self.status_TG3 = "BLOCKAGE"
                    self.label_r1_status0.hide()
                    self.label_r1_status1.hide()
                    self.label_r1_status2.hide()
                    self.label_r1_status3.hide()
                    self.label_r1_status4.show()
                else:
                    pass
            else:
                pass
        else:
            pass

    def write_can_thread(self, connected_dev_id, pcan_handle_dict):
        # Generate QThread and Worker
        thread = QThread()
        worker = CANWriteWorker(self.pcan_ctrl, connected_dev_id, pcan_handle_dict, self.flag_door_test, self.read_worker_dict)

        # Connect signals
        worker.log_signal.connect(self.print_log)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(worker.deleteLater)
        
        # Move worker to thread
        worker.moveToThread(thread)
        
        worker.onOff_signal.connect(worker.write_act_deact)

        # Call run when thread is started
        thread.started.connect(worker.run)
        thread.start()

        # Add thread and worker into the list for manage
        self.thread_list.append(thread)
        self.write_worker = worker

    def process_start(self):
        # Generate CAN read thread
        for dev_id in self.connected_dev_id:
            _, pcan_handle = self.pcan_ctrl.get_handle_from_id(dev_id)
            self.pcan_handle_dict[dev_id] = pcan_handle
            self.read_can_thread(dev_id, pcan_handle)

        # Generate CAN write thread
        self.write_can_thread(self.connected_dev_id, self.pcan_handle_dict)
        
        for dev_id in self.connected_dev_id:
            read_worker = self.read_worker_dict[dev_id]
            read_worker.resend_signal.connect(self.write_worker.write_resend)

    def func_start(self):
        # When clicked start button, poped up a messageBox to confirm
        if self.btn_device1.isChecked() or self.btn_device2.isChecked() or self.btn_device3.isChecked():
            reply = QMessageBox.question(self, "확인 메시지", "테스트를 시작하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # Print system log
                sysLogMsg = "[MAIN] Button clicked : START\t(Mode : " + self.cmb_modeSelection.currentText() + ")"
                self.print_log(0, sysLogMsg)
                self.update_test_setting()

                # Process start
                self.process_start()

                # Generate initial csv file
                if self.flag_door_test:
                    self.Radar1_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_FL.csv")
                    self.Radar2_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_FR.csv")
                    self.Radar3_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_RR.csv")
                else:   # Tailgate test
                    self.Radar1_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_TG#1.csv")
                    self.Radar2_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_TG#2.csv")
                    self.Radar3_data_csv_path = os.path.join(self.data_logfolder_path, self.line_logFileName.text() + "_TG#3.csv")

                if not os.path.exists(self.Radar1_data_csv_path):
                    with open(self.Radar1_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(["Time", "Tx0", "Tx1", "Tx2", "Temp", "Status"])
                if not os.path.exists(self.Radar2_data_csv_path):
                    with open(self.Radar2_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(["Time", "Tx0", "Tx1", "Tx2", "Temp", "Status"])
                if not os.path.exists(self.Radar3_data_csv_path):
                    with open(self.Radar3_data_csv_path, "a", newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(["Time", "Tx0", "Tx1", "Tx2", "Temp", "Status"])

                # Send ON signal
                if self.flag_preTest and self.pre_on_time == 0:
                    self.flag_pre_on = False
                    self.flag_on = False
                    self.func_emit_onOffStatus(self.flag_on)
                else:
                    self.flag_on = True
                    self.func_emit_onOffStatus(self.flag_on)

                # Interlock Start/Stop/Unlock button
                self.flag_start = True
                self.flag_lock = True
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

                # Update current/remain cycle in GUI
                if self.flag_preTest:
                    self.line_currentPreCycle.setText("0")
                    self.line_remainPreCycle.setText(f"{self.num_pre_cycle}")
                self.line_currentCycle.setText("0")
                self.line_remainCycle.setText(f"{self.num_inner_cycle}")
                if not self.flag_innerCycle:
                    self.line_currentOutCycle.setText("0")
                    self.line_remainOutCycle.setText(f"{self.numOuterCycle}")
                
                # Lock other functions
                self.group_modeSelection.setEnabled(False)
                self.group_canConnect.setEnabled(False)
                self.group_logConfig.setEnabled(False)
                self.group_customModeSetting.setEnabled(False)
                
                # Save operation log
                oper_logger_filename = self.line_logFilePath.text() + '/' + self.line_logFileName.text() + '.log'
                self.oper_log_handler = logging.handlers.RotatingFileHandler(filename=oper_logger_filename, mode='a', maxBytes=self.max_logFile_size)
                self.oper_logger.addHandler(self.oper_log_handler)
                # self.oper_logger.debug("Date\tTime\tTx0\tTx1\tTx2\tTemperature")
                oper_formatter = logging.Formatter(fmt='%(asctime)s\t%(message)s')
                self.oper_log_handler.setFormatter(oper_formatter)

                # Save critial log
                cri_logger_filename = self.line_logFilePath.text() + '/' + self.line_logFileName.text() + '_crit.log'
                self.cri_log_handler = logging.handlers.RotatingFileHandler(filename=cri_logger_filename, mode='a', maxBytes=self.max_logFile_size)
                self.cri_logger.addHandler(self.cri_log_handler)
                # self.cri_logger.debug("Date\tTime\tTx0\tTx1\tTx2\tTemperature")
                cri_formatter = logging.Formatter(fmt='%(asctime)s\t%(message)s')
                self.cri_log_handler.setFormatter(cri_formatter)
        else:
            reply = QMessageBox.question(self, "확인 메시지", "하나 이상의 CAN Device를 연결해주십시오.", QMessageBox.Yes)
                       
            
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
                self.flag_pre_test_finished = False
                self.operation_timer = 0
                self.lab_timer.setText("0000:00:00")
                self.label_actDeact1.setStyleSheet(sleep)
                self.label_actDeact2.setStyleSheet(sleep)
                self.label_actDeact3.setStyleSheet(sleep)

                # Unlock other functions
                self.group_modeSelection.setEnabled(True)
                self.group_canConnect.setEnabled(True)
                self.group_logConfig.setEnabled(True)
                self.group_customModeSetting.setEnabled(True)

                # Print and save system log
                self.print_log(0, "[MAIN] Button clicked : STOP")
                self.sys_logger.debug("[MAIN] Button clicked : STOP")

                # Emit signal to stop worker
                self.write_worker.stop_signal.emit()
                # self.print_log(0, "Write workers have been signaled to stop")
                
                for dev_id, worker in self.read_worker_dict.items():
                    worker.stop_signal.emit()
                    # self.print_log(0, "All read workers have been signaled to stop")

                # Terminate all thread
                for thread in self.thread_list:
                    thread.quit()
                    thread.wait()

                self.label_r1_status0.hide()
                self.label_r1_status1.hide()
                self.label_r1_status2.hide()
                self.label_r1_status3.hide()
                self.label_r1_status4.hide()
                self.label_r2_status0.hide()
                self.label_r2_status1.hide()
                self.label_r2_status2.hide()
                self.label_r2_status3.hide()
                self.label_r2_status4.hide()
                self.label_r3_status0.hide()
                self.label_r3_status1.hide()
                self.label_r3_status2.hide()
                self.label_r3_status3.hide()
                self.label_r3_status4.hide()

                # Remove logger handler
                self.oper_logger.removeHandler(self.oper_log_handler)
                self.cri_logger.removeHandler(self.cri_log_handler)

        elif self.flag_start and self.flag_test_finished:
            # Print and save system log
            self.print_log(0, "[MAIN] Button clicked : auto STOP")

            # Emit signal to stop worker        
            self.write_worker.stop_signal.emit()
            # self.print_log(0, "Write workers have been signaled to stop")

            for dev_id, worker in self.read_worker_dict.items():
                worker.stop_signal.emit()
                # self.print_log(0, "All read workers have been signaled to stop")

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