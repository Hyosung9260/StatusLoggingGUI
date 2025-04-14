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
from PyQt5.QtCore import QTimer, QTime, QThread, Qt, pyqtSignal, QObject, QEventLoop, pyqtSlot

update_date = "25.04.07"
version = "version 0.0.6"
'''
# NOTE Ver_0.1.0
1. CAN Thread 분기
    > Main GUI thread, CAN write thread, CAN read thread(Max 3 thread)
    > Radar Act/Deact 자동 체크
2. Radar 구동방식 변경
    > ON time 동안 500ms 주기로 act 신호 전송


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
        # self.log_signal.emit(0, f"[WRITE] On/Off Signal recieved : {onOffStatus}")

        if onOffStatus: # ON
            # QTimer.singleShot(200, lambda: self.write_pre_pwr_tmp_request())
            self.write_act_msg(False, 0)
            QThread.msleep(150)
            self.write_pre_pwr_tmp_request()

            # Send act message to read thread
            for dev_id, worker in self.read_worker_dict.items():
                worker.onOff_signal.emit(onOffStatus)

            self.act_sequence()
        else:           # OFF
            self.timer_tx_power.stop()
            # self.write_act_msg(False, 0)
            self.write_deact_msg(False, 0)
            # QTimer.singleShot(200, lambda: self.write_deact_msg(False, 0))
            
            # Send act message to read thread
            for dev_id, worker in self.read_worker_dict.items():
                worker.onOff_signal.emit(onOffStatus)
    
    @pyqtSlot(int, bool)
    def write_resend(self, dev_id, resend_act):
        # self.log_signal.emit(0, f"[WRITE] dev_id={dev_id} request act(true)/deact(False) = {resend_act}")
        
        if dev_id == 0x1FF100A2:
            self.write_pwr_tmp_request(FL)
        elif dev_id == 0x1FF100A3:
            self.write_pwr_tmp_request(FR)
        elif dev_id == 0x1FF100A5:
            self.write_pwr_tmp_request(RR)
        elif dev_id == 555:
            msg_id = DOOR_FL_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)
        elif dev_id == 666:
            msg_id = DOOR_FR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)
        elif dev_id == 777:
            msg_id = DOOR_RR_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame_pre3)
        else:
            pcan_handle = self.pcan_handle_dict[dev_id]
            if pcan_handle is None:
                self.log_signal.emit(2, f"[WRITE] Invalid dev_id: {dev_id}")
                return
            if resend_act:
                self.write_act_msg(True, dev_id)
                # QTimer.singleShot(200, lambda: self.write_act_msg(True, dev_id))
            else:
                self.timer_tx_power.stop()
                self.write_deact_msg(True, dev_id)
                # QTimer.singleShot(200, lambda: self.write_deact_msg(True, dev_id))
    
    def act_sequence(self):
        self.write_act_msg(False, 0)
        self.timer_tx_power.start(500)

    '''
    def start_power_temp_loop(self):
        # self.send_count = 0
        self._send_power_temp_step()

    def _send_power_temp_step(self):
        self.write_power_temp_request()
        
        # RQST → 500ms → RQST (repeat)
        self.timer_tx_power.start(250)

        # # RQST → 2ms → RQST → 500ms (Repeat)
        # self.send_count += 1
        # if self.send_count < 2:
        #     self.timer_tx_power.start(2)
        # else:
        #     self.send_count = 0
        #     self.timer_tx_power.start(500)
    '''

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
            # self.log_signal.emit(0, "Message write : TxPower/Temp request resend FL")
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
            # self.log_signal.emit(0, "Message write : TxPower/Temp request resend FR")
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
            # self.log_signal.emit(0, "Message write : TxPower/Temp request resend RR")
            pass
        else:
            self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : RR")
    
    def write_FL_deact(self):
        msg_id = DOOR_FL_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            # self.log_signal.emit(0, "Message write : FL deact")
            pass
        else:
            self.log_signal.emit(0, "[ERROR] Deact failed : FL")

    def write_FR_deact(self):
        msg_id = DOOR_FR_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            # self.log_signal.emit(0, "Message write : FR deact")
            pass
        else:
            self.log_signal.emit(0, "[ERROR] Deact failed : FR")

    def write_RR_deact(self):
        msg_id = DOOR_RR_MSG_ID[0]
        dlc = DOOR_DEACT[0]
        msg_frame = DOOR_DEACT[1]

        error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id, dlc, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            # self.log_signal.emit(0, "Message write : RR deact")
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
                # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FL")
            QThread.msleep(30)

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : FR")
            QThread.msleep(30)

            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre1)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre2)
            error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame_pre3)
            if error_ok == PCAN_ERROR_OK:
                # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                pass
            else:
                self.log_signal.emit(0, "[ERROR] TxPower/Temp pre request failed : RR")
            QThread.msleep(30)

        else:   # Talegate test
            msg_id = TALEGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP_PRE1)
            msg_frame_pre1 = RQST_PWR_TEMP_PRE1
            msg_frame_pre2 = RQST_PWR_TEMP_PRE2
            msg_frame_pre3 = RQST_PWR_TEMP_PRE3

            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre1)
                if error_ok == PCAN_ERROR_OK:
                    # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                    pass
                else:
                    self.log_signal.emit(0, "[ERROR] TxPower/Temp request failed : Pre request 1")

            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre2)
                if error_ok == PCAN_ERROR_OK:
                    # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                    pass
                else:
                    self.log_signal.emit(0, "[ERROR] TxPower/Temp request failed : Pre request 2")
            
            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame_pre3)
                if error_ok == PCAN_ERROR_OK:
                    # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                    pass
                else:
                    self.log_signal.emit(0, "[ERROR] TxPower/Temp request failed : Pre request 3")

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
                # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                pass
            else:
                self.log_signal.emit(0, f"[ERROR] TxPower/Temp request failed : {sensorType}")

        else:   # Talegate test
            msg_id = TALEGATE_MSG_ID[1]
            dlc = len(RQST_PWR_TEMP)
            msg_frame = RQST_PWR_TEMP

            for dev_id in self.connected_dev_id:
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:
                    # self.log_signal.emit(0, "[THREAD] message write : TxPower/Temp request")
                    pass
                else:
                    self.log_signal.emit(0, "[ERROR] message write : TxPower/Temp request failed")

    def write_act_msg(self, isResend, dev_id_re):
        if isResend:    # 재전송 요청 시 해당 dev_id에만 전송
            if self.flag_door_test:
                msg_id_FL = DOOR_FL_MSG_ID[0]
                msg_id_FR = DOOR_FR_MSG_ID[0]
                msg_id_RR = DOOR_RR_MSG_ID[0]
                dlc = DOOR_ACT[0]
                msg_frame = DOOR_ACT[1]

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : Act")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : Act")

            else:   # Talegate test
                msg_id = TALEGATE_MSG_ID[0]
                dlc = len(TALEGATE_ACT)
                msg_frame = TALEGATE_ACT

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id_re], msg_id, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : Act")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : Act")
        else:
            if self.flag_door_test:
                msg_id_FL = DOOR_FL_MSG_ID[0]
                msg_id_FR = DOOR_FR_MSG_ID[0]
                msg_id_RR = DOOR_RR_MSG_ID[0]
                dlc = DOOR_ACT[0]
                msg_frame = DOOR_ACT[1]

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id_FL, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FL Act")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, f"[ERROR] message write : FL Act {error_ok}")

                QThread.msleep(50)
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id_FR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FR Act")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : FR Act")

                QThread.msleep(50)
                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[0], msg_id_RR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : RR Act")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : RR Act")

            else:   # Talegate test
                msg_id = TALEGATE_MSG_ID[0]
                dlc = len(TALEGATE_ACT)
                msg_frame = TALEGATE_ACT

                for dev_id in self.connected_dev_id:
                    error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame)
                    if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                        self.log_signal.emit(0, "[THREAD_WRITE] message write : Act")
                    else:                           # Failed to write CAN message
                        self.log_signal.emit(0, "[ERROR] message write : Act")

    def write_deact_msg(self, isResend, dev_id_re):
        if isResend:
            if self.flag_door_test:
                msg_id_FL = DOOR_FL_MSG_ID[0]
                msg_id_FR = DOOR_FR_MSG_ID[0]
                msg_id_RR = DOOR_RR_MSG_ID[0]
                dlc = DOOR_DEACT[0]
                msg_frame = DOOR_DEACT[1]

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id_FL, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FL Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : FL Deact")

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id_FR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FR Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : FR Deact")

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id_RR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : RR Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : RR Deact")

            else:   # Talegate test
                msg_id = TALEGATE_MSG_ID[0]
                dlc = len(TALEGATE_DEACT)
                msg_frame = TALEGATE_DEACT

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id_re], msg_id, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : Deact")
        else:
            if self.flag_door_test:
                msg_id_FL = DOOR_FL_MSG_ID[0]
                msg_id_FR = DOOR_FR_MSG_ID[0]
                msg_id_RR = DOOR_RR_MSG_ID[0]
                dlc = DOOR_DEACT[0]
                msg_frame = DOOR_DEACT[1]

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FL, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FL Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : FL Deact")

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_FR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : FR Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : FR Deact")

                error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[self.connected_dev_id[0]], msg_id_RR, dlc, msg_frame)
                if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                    self.log_signal.emit(0, "[THREAD_WRITE] message write : RR Deact")
                else:                           # Failed to write CAN message
                    self.log_signal.emit(0, "[ERROR] message write : RR Deact")

            else:   # Talegate test
                msg_id = TALEGATE_MSG_ID[0]
                dlc = len(TALEGATE_DEACT)
                msg_frame = TALEGATE_DEACT

                for dev_id in self.connected_dev_id:
                    error_ok = self.pcan_ctrl.write_msg_frame(self.pcan_handle_dict[dev_id], msg_id, dlc, msg_frame)
                    if error_ok == PCAN_ERROR_OK:   # Successfully write CAN message
                        self.log_signal.emit(0, "[THREAD_WRITE] message write : Deact")
                    else:                           # Failed to write CAN message
                        self.log_signal.emit(0, "[ERROR] message write : Deact")
    
    def stop(self):
        self.running = False

class CANReadWorker(QObject):
    log_signal = pyqtSignal(int, str)                                # Signal for print log
    finished = pyqtSignal()                                          # Signal for worker finish
    update_data_signal = pyqtSignal(bool, int, str, str, str, str)     # Signal for update TxPower, Temperature
    onOff_signal = pyqtSignal(bool)                                  # Signal for check radar on/off
    resend_signal = pyqtSignal(int, bool)                            # Signal for Act/Deact resend request
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
        self.count_FL_pre_request = 0
        self.count_FR_pre_request = 0
        self.count_RR_pre_request = 0
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

        self.log_signal.emit(0, "CAN read thread started")
        while self.running:
            # CAN message read
            msg_data, msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=self.pcan_handle, output_mode='numpy')
            event_loop.processEvents(QEventLoop.AllEvents, 50)
            # Main request ACT
            if self.flag_act:
                if msg_id:
                    self.flag_radar_act = True
                    self.flag_cmd_resend = False
                    self.data_processing(msg_id, msg_data)
                else:
                    if not self.flag_radar_act and not self.flag_cmd_resend:
                        self.flag_cmd_resend = True
            
            # Main request DEACT
            else:
                if msg_id:
                    if self.flag_radar_act and not self.flag_cmd_resend:
                        self.flag_cmd_resend = True
                else:
                    self.flag_radar_act = False
                    self.flag_cmd_resend = False
                    self.flag_FL_on = False
                    self.flag_FR_on = False
                    self.flag_RR_on = False
                    self.count_FL_pre_request = 0

        self.finished.emit()

    def data_processing(self, msg_id, msg_data):
        if self.flag_door_test:
            self.door_data_processing(msg_id, msg_data)
        else:   # Talegate test
            self.talegate_data_processing(msg_id, msg_data)

    def door_data_processing(self, msg_id, msg_data):
        # FL
        if msg_id == 0x1FF100A2:
            if not self.flag_FL_on:
                self.flag_FL_on = True
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
        # FR
        elif msg_id == 0x1FF100A3:
            if not self.flag_FR_on:
                self.flag_FR_on = True
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
        # RL (Not used in this test)
        elif msg_id == 0x1FF100A4:
            data_code, result = self.get_txpower_temp(msg_id, msg_data)
            # self.update_data_signal.emit(self.dev_id, str(self.ascii_data_tx0), str(self.ascii_data_tx1), str(self.ascii_data_tx2), str(self.ascii_data_temp))
        # RR
        elif msg_id == 0x1FF100A5:
            if not self.flag_RR_on:
                self.flag_RR_on = True
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
        # Error (msg_id == 999)
        else:
            pass
    def talegate_data_processing(self, msg_id, msg_data):
        if msg_id == 0x1FF11400:
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
        # Error (msg_id == 999)
        else:
            pass

    def get_txpower_temp(self, msg_id, msg_data):
        # Tx0 Power
        if msg_data[4] == 0x30 and msg_data[5] == 0x50 and msg_data[6] == 0x6F and msg_data[7] == 0x77 and msg_data[8] == 0x65 and msg_data[9] == 0x72:
            data_code = "Tx0"
            tx0_data_hex = msg_data[17:21]
            ascii_data_tx0 = tx0_data_hex.tobytes().decode('ascii')
            self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx0 Power : {ascii_data_tx0} [dBm]")
            if float(ascii_data_tx0) < TX_POWER_LIMIT[0] or float(ascii_data_tx0) > TX_POWER_LIMIT[1]:
                self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx0 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            return data_code, ascii_data_tx0
        # Tx1 Power
        elif msg_data[5] == 0x31 and msg_data[6] == 0x50 and msg_data[7] == 0x6F and msg_data[8] == 0x77 and msg_data[9] == 0x65 and msg_data[10] == 0x72:
            data_code = "Tx1"
            tx1_data_hex = msg_data[18:22]
            ascii_data_tx1 = tx1_data_hex.tobytes().decode('ascii')
            self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx1 Power : {ascii_data_tx1} [dBm]")
            if float(ascii_data_tx1) < TX_POWER_LIMIT[0] or float(ascii_data_tx1) > TX_POWER_LIMIT[1]:
                self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx1 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            return data_code, ascii_data_tx1
        # Tx2 Power
        elif msg_data[6] == 0x32 and msg_data[7] == 0x50 and msg_data[8] == 0x6F and msg_data[9] == 0x77 and msg_data[10] == 0x65 and msg_data[11] == 0x72:
            data_code = "Tx2"
            tx2_data_hex = msg_data[19:23]
            ascii_data_tx2 = tx2_data_hex.tobytes().decode('ascii')
            self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx2 Power : {ascii_data_tx2} [dBm]")
            if float(ascii_data_tx2) < TX_POWER_LIMIT[0] or float(ascii_data_tx2) > TX_POWER_LIMIT[1]:
                self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Tx2 Power over the limit (MIN/MAX : {TX_POWER_LIMIT[0]}/{TX_POWER_LIMIT[1]})")
            return data_code, ascii_data_tx2
        # Temperature
        elif msg_data[8] == 0x54 and msg_data[9] == 0x65 and msg_data[10] == 0x6D and msg_data[11] == 0x70 and msg_data[12] == 0x65:
            data_code = "Temp"
            temp_data_hex = msg_data[21:26]
            ascii_data_temp = temp_data_hex.tobytes().decode('ascii')
            self.log_signal.emit(1, f"[{RECV_MSG_ID_LIST[msg_id]}] Temperature : {ascii_data_temp} [℃]")
            self.resend_signal.emit(msg_id, True)
            if float(ascii_data_temp) < TEMP_LIMIT[0] or float(ascii_data_temp) > TEMP_LIMIT[1]:
                self.log_signal.emit(2, f"[{RECV_MSG_ID_LIST[msg_id]}] Temperature over the limit (MIN/MAX : {TEMP_LIMIT[0]}/{TEMP_LIMIT[1]})")
            return data_code, ascii_data_temp
        # GPADC
        # elif msg_data[8] == 0x47 and msg_data[9] == 0x50 and msg_data[10] == 0x41 and msg_data[11] == 0x44 and msg_data[12] == 0x43:
            # pass
        elif msg_data[9] == 0x5B and msg_data[10] == 0x54 and msg_data[11] == 0x65 and msg_data[12] == 0x6D and msg_data[13] == 0x70:
            # Send ACK message
            self.resend_signal.emit(msg_id, True)
            data_code = "etc"
            result = 0
            return data_code, result
        elif  msg_data[8] == 0x57 and msg_data[9] == 0x61 and msg_data[10] == 0x72 and msg_data[11] == 0x6E and msg_data[12] == 0x69:
            # Send ACK message
            self.resend_signal.emit(msg_id, True)
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
        # TODO :: 사용하지 않는 코드 추후 정리
        if self.flag_act:
            if not self.flag_FL_on:
                self.count_FL_pre_request += 1
            elif not self.flag_FR_on:
                self.count_FR_pre_request += 1
            elif not self.flag_RR_on:
                self.count_RR_pre_request += 1
            
            # if self.flag_FL_on and self.flag_FR_on and self.flag_RR_on:
            #     self.count_FL_pre_request = 0
            #     self.count_FR_pre_request = 0
            #     self.count_RR_pre_request = 0

            if self.count_FL_pre_request > 3:
                self.log_signal.emit(0, "[THREAD_READ] FL pre resend request")
                self.resend_signal.emit(555, True)
                self.count_FL_pre_request = 0
            elif self.count_FR_pre_request > 3:
                self.log_signal.emit(0, "[THREAD_READ] FR pre resend request")
                self.resend_signal.emit(666, True)
                self.count_FR_pre_request = 0
            elif self.count_RR_pre_request > 3:
                self.log_signal.emit(0, "[THREAD_READ] RR pre resend request")
                self.resend_signal.emit(777, True)
                self.count_RR_pre_request = 0

            if self.flag_cmd_resend:
                if self.flag_act and not self.flag_radar_act:
                    self.log_signal.emit(0, "[THREAD_READ] Act resend request")
                    self.resend_signal.emit(self.dev_id, True)   # Act request

                elif not self.flag_act and self.flag_radar_act:
                    self.log_signal.emit(0, "[THREAD_READ] Deact resend request")
                    self.resend_signal.emit(self.dev_id, False)  # Deact request
                

    def stop(self):
        self.running = False

class StatusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("Status_Logging_GUI.ui", self)   # Load GUI file
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
        self.flag_innerOnTime = True
        self.flag_work_outer_cycle = False
        self.flag_saveSyslog = True
        self.flag_door_test = True
        self.flag_test_finished = False
        self.flag_on = False
        
        # Initialize variables
        self.connected_dev_id = []
        self.pcan_handle_dict = {}
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
        self.totalTestTime = 0
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
        # self.btn_canConnectionCheck.clicked.connect(self.can_connection_check)
        self.btn_clearSysLog.clicked.connect(self.clearSysLog)
        self.btn_clearCanLog.clicked.connect(self.clearCanLog)
        self.btn_clearCriLog.clicked.connect(self.clearCriLog)
        self.btn_R1_preRqst.clicked.connect(self.send_pre_rqst1)
        self.btn_R2_preRqst.clicked.connect(self.send_pre_rqst2)
        self.btn_R3_preRqst.clicked.connect(self.send_pre_rqst3)

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

    def send_pre_rqst2(self):
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

    def send_pre_rqst3(self):
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

    def inner_cycle_work(self):
        if self.flag_innerOnTime:
            if self.inner_cycle_timer < self.innerOnTime - 1:
                self.inner_cycle_timer += 1
            else:
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
                
                # Update current/remain cycle in GUI
                self.line_currentCycle.setText(f"{self.crntInnerCycle}")
                self.line_remainCycle.setText(f"{self.numInnerCycle-self.crntInnerCycle}")

                if self.crntInnerCycle < self.numInnerCycle:
                    self.flag_on = True
                    self.func_emit_onOffStatus(self.flag_on)
                    self.flag_innerOnTime = True
                    self.print_log(0, f"[MAIN] Current Inner Cycle : {self.crntInnerCycle} / Total Inner Cycle : {self.numInnerCycle}")
                else:                    
                    self.crntInnerCycle = 0
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
                self.outer_cycle_timer += 1
            else:
                self.outer_cycle_timer = 0
                self.crntOuterCycle += 1
                self.flag_work_outer_cycle = False

                if self.crntOuterCycle < self.numOuterCycle:
                    self.flag_on = True
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
            total_time_inner = (self.innerOnTime + self.innerOffTime) * self.numInnerCycle
            self.line_totalInnerCycleTime.setText(str(total_time_inner))

            hours = total_time_inner // 3600
            mins = (total_time_inner % 3600) // 60
            secs = total_time_inner % 60
            self.line_totalTestTime.setText(f"{hours}시간{mins}분{secs}초")

            self.totalTestTime = total_time_inner
        # If occur exclude case, consider 0
        except ValueError:
            self.line_totalInnerCycleTime.setText("0")
        
        if self.flag_innerCycle == False:
            try:
                self.outerOffTime = int(self.line_outerOffTime.text()) if self.line_outerOffTime.text().isdigit() else 0
                self.numOuterCycle = int(self.line_numOuterCycle.text()) if self.line_numOuterCycle.text().isdigit() else 0

                total_time_outer = (total_time_inner + self.outerOffTime) * self.numOuterCycle
                self.line_totalOuterCycleTime.setText(str(total_time_outer))

                hours = total_time_outer // 3600
                mins = (total_time_outer % 3600) // 60
                secs = total_time_outer % 60
                self.line_totalTestTime.setText(f"{hours}시간{mins}분{secs}초")

                self.totalTestTime = total_time_outer
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
            self.line_radar1.setText("FL")
            self.line_radar2.setText("FR")
            self.line_radar3.setText("RR")
        else:   # Talegate test
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

    '''def send_act_sequence(self, pcan_handle):
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
                QThread.msleep(100)  # CPU 점유율 방지

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

                # QThread.msleep(0.1)  # CPU 점유율 방지

    def can_connection_check(self):
        if self.flag_door_test:
            if self.btn_device1.isChecked():
                _, pcan_handle = self.pcan_ctrl.get_handle_from_id(self.connected_dev_id[0])
                _, receive_event = self.pcan_ctrl.InitializeEvent(Channel=pcan_handle)

                self.send_act_sequence(pcan_handle)
                QThread.msleep(500)
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
                    QThread.msleep(500)
                    self.confirm_msg_id(pcan_handle, receive_event)
                    self.send_deact_sequence(pcan_handle)
                else:
                    sysLogMsg = f"CAN device is not connected. Please check connection."
                    self.print_log(0, sysLogMsg)
            else:
                sysLogMsg = f"CAN device is not connected. Please connect all the 3 devices."
                self.print_log(0, sysLogMsg)'''

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

    def read_can_thread(self, dev_id, pcan_handle):
        # Generate QThread and Worker
        thread = QThread()
        worker = CANReadWorker(self.pcan_ctrl, dev_id, pcan_handle, self.flag_door_test)

        # Connect signals
        worker.log_signal.connect(self.print_log)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(worker.deleteLater)

        # Move worker to thread
        worker.moveToThread(thread)

        # Function for CAN read data update
        worker.update_data_signal.connect(self.update_data)
        
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

        else:   # Talegate test
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
            pcan_handle = self.pcan_ctrl.get_handle_from_id(dev_id)
            self.pcan_handle_dict[dev_id] = pcan_handle
            self.read_can_thread(dev_id, pcan_handle)
        
        # Generate CAN write thread
        self.write_can_thread(self.connected_dev_id, self.pcan_handle_dict)
        
        for dev_id in self.connected_dev_id:
            read_worker = self.read_worker_dict[dev_id]
            read_worker.resend_signal.connect(self.write_worker.write_resend)

    def func_start(self):
        # When clicked start button, poped up a messageBox to confirm
        if self.btn_device1.isChecked():
            reply = QMessageBox.question(self, "확인 메시지", "테스트를 시작하시겠습니까?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # Print system log
                sysLogMsg = "[MAIN] Button clicked : START\t(Mode : " + self.cmb_modeSelection.currentText() + ")"
                self.print_log(0, sysLogMsg)

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

                # Update current/remain cycle in GUI
                self.line_currentCycle.setText(f"{self.crntInnerCycle}")
                self.line_remainCycle.setText(f"{self.numInnerCycle-self.crntInnerCycle}")
                
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

                # Save critial log
                cri_logger_filename = self.line_logFilePath.text() + '/' + self.line_logFileName.text() + '_crit.log'
                self.cri_log_handler = logging.handlers.RotatingFileHandler(filename=cri_logger_filename, mode='a', maxBytes=self.max_logFile_size)
                cri_formatter = logging.Formatter(fmt='%(asctime)s > %(message)s')
                self.cri_log_handler.setFormatter(cri_formatter)
                self.cri_logger.addHandler(self.cri_log_handler)
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
                self.operation_timer = 0
                self.lab_timer.setText("0000:00:00")

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

                # Remove logger handler
                self.oper_logger.removeHandler(self.oper_log_handler)

        elif self.flag_start and self.flag_test_finished:
            # Print and save system log
            self.print_log(0, "[MAIN] Button clicked : auto STOP")
            self.sys_logger.debug("[MAIN] Button clicked : auto STOP")

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