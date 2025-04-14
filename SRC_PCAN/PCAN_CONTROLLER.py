import numpy as np
from SRC_PCAN.PCANBasic import *
import json
from Status_DEF import *

IS_WINDOWS = platform.system() == 'Windows'

try:
    if IS_WINDOWS:
        import win32event
        import win32api
    else:
        import os
        import select
        __LIBC_OBJ = cdll.LoadLibrary("libc.so.6")

        def event_fd(init_val, flags):
            return __LIBC_OBJ.eventfd(init_val, flags)
except Exception as ex:
    print("Failed to support interoperable-event, exception=(" + str(ex) + ")")


class PCANControl:
    def __init__(self, ):
        self.m_objPCANBasic = PCANBasic()
        self.start_flag = False

        self.m_BitrateTXT = BITRATE
        # self.MSG_ID = self.pcan_config['MSG_ID']

    ''' Below: CAN Status Related Functions'''
    def initialize(self, dev_id):
        _, m_PCANHandle = self.get_handle_from_id(dev_id)  # id에 상응하는 USBBUS handle 값 찾기
        error_ok = self.m_objPCANBasic.InitializeFD(m_PCANHandle, bytes(self.m_BitrateTXT, 'utf-8'))    # 해당 handle에 대해 CAN Connection 수행
        if error_ok == PCAN_ERROR_OK:               # CAN 연결 성공
            print('[Message] PCAN USB FD Device ID:{} has been \033[92mCONNECTED\033[0m'.format(dev_id))
            return True
        else:                                       # CAN 연결 실패
            print("\033[91mError: Something wrong during connecting PCAN USB FD Device ID:\033[0m{}".format(dev_id))
            return False

    def uninitialize(self, dev_id):
        _, m_PCANHandle = self.get_handle_from_id(dev_id)  # id에 상응하는 USBBUS handle 값 찾기
        error_ok = self.m_objPCANBasic.Uninitialize(m_PCANHandle)  # 해당 handle에 대해 CAN DisConnection 수행
        if error_ok == PCAN_ERROR_OK:
            print('\n[Message] PCAN USB FD Device ID:{} has been \033[91mDISCONNECTED\033[0m'.format(dev_id))
            return True
        else:
            print("\033[91mError: Disconnecting CAN:{} is failed. 'PCAN_ERROR_CODE:{}'\033[0m".format(dev_id, error_ok))
            return False

    def get_id_from_handle(self, m_PCANHandle):
        error, dev_id = self.m_objPCANBasic.GetValue(m_PCANHandle, PCAN_DEVICE_ID)
        return error, dev_id

    def get_handle_from_id(self, dev_id):
        id_bytes = LOOKUP_DEVICE_ID + b'=' + bytes(str(dev_id), 'utf-8')  # LookUpChannel은 인풋으로 bytes를 옆 형태와 같이 받음
        error, m_PCANHandle = self.m_objPCANBasic.LookUpChannel(id_bytes)  # CAN_connector_id에 해당하는 USBBUS Handle 값을 찾음
        return error, m_PCANHandle

    def read_unit_buf(self, m_PCANHandle, recv_event=None, wait_time=300, output_mode='numpy', evt_mode=True):
        if evt_mode:
            if IS_WINDOWS:
                if win32event.WaitForSingleObject(recv_event, wait_time) == win32event.WAIT_OBJECT_0:
                    error_OK, theMsg, timestamp = self.m_objPCANBasic.ReadFD(m_PCANHandle)
            else:
                stsResult = self.WaitForEvent(recv_event, wait_time)
                if stsResult == PCAN_ERROR_OK:
                    error_OK, theMsg, timestamp = self.m_objPCANBasic.ReadFD(m_PCANHandle)
        else:
            error_OK, theMsg, timestamp = self.m_objPCANBasic.ReadFD(m_PCANHandle)

        if error_OK in [PCAN_ERROR_OK, PCAN_ERROR_QRCVEMPTY]:
            if error_OK == PCAN_ERROR_QRCVEMPTY:
                # print('Warn: PCAN_ERROR_QRCVEMPTY')
                pass

            # flag = theMsg.DATA[:8]
            msg_id = theMsg.ID
            if output_mode == 'numpy':
                gMemData = np.frombuffer(theMsg.DATA, dtype=np.uint8)
            elif output_mode == 'bytes':
                gMemData = theMsg.DATA
            else:
                print("Available Mode: 'numpy' or 'bytes'")
            # gMemData = np.array([int(b, 16) for b in gMemData])
            return gMemData, msg_id

        else:
            # raise ValueError('\033[91m[Error] Error happens during receiving CAN-FD data: {}\033[0m'.format(error_OK))
            gMemData = 0
            msg_id = 0
            return gMemData, msg_id

    def GetLengthFromDLC(self, dlc):
        if dlc <= 8:
            return dlc
        if dlc == 9:
            return 12
        elif dlc == 10:
            return 16
        elif dlc == 11:
            return 20
        elif dlc == 12:
            return 24
        elif dlc == 13:
            return 32
        elif dlc == 14:
            return 48
        elif dlc == 15:
            return 64
        return dlc

    def InitializeEvent(self, Channel:TPCANHandle=None):
        if IS_WINDOWS:
            stsResult = PCAN_ERROR_OK
            event = win32event.CreateEvent(None, 0, 0, None)
            event_id = int(event)
            if event and Channel != None:
                stsResult = self.m_objPCANBasic.SetValue(Channel, PCAN_RECEIVE_EVENT, event_id)
            return stsResult, event
        else:
            if Channel != None:
                (stsResult, event) = self.m_objPCANBasic.GetValue(Channel, PCAN_RECEIVE_EVENT)
            else:
                event = event_fd(0, os.EFD_NONBLOCK)
            return stsResult, event

    def CloseEvent(self, event):
        # win32api.CloseHandle(event)
        event.close()

    def write_msg_frame(self, m_PCANHandle, m_ID, m_DLC, msg_frame):
        CANMsg = TPCANMsgFD()               # CAN Message 전송을 위한 structure class로 다음 업무를 수행:1. msg_frame을 ctypes로 변경, 2. CAN ID 전달, 3. DLC를 이용한 데이터 변환
        CANMsg.ID = int(m_ID, 16)           # 입력 받은 CAN Message ID를 hex to integer로 변경        
        CANMsg.DLC = int(m_DLC)             # 입력 받은 DLC를 hex to integer로 변경
        CANMsg_length = len(msg_frame)      # DLC를 통해 메세지 프레임의 길이를 파악
        if CANMsg.ID > 0xFFFF:
            CANMsg.MSGTYPE = PCAN_MESSAGE_EXTENDED.value | PCAN_MESSAGE_FD.value | PCAN_MESSAGE_BRS.value
        else:
            CANMsg.MSGTYPE = PCAN_MESSAGE_FD

        for i in range(CANMsg_length):                      # 메세지 프레임 길이 만큼 msg_frame 값을 CANMsg 구조체에 값을 복사함
            CANMsg.DATA[i] = int(msg_frame[i], 16)          # 전송 할 메세지 복사
        return self.m_objPCANBasic.WriteFD(m_PCANHandle, CANMsg)    # 전송하고자하는 PcanHandle 채널로 CANMsg를 전송 후, 전송 여부를 반납

    def send_actSensor(self, m_PCANHandle, kind_of_test):
        if kind_of_test:    # Door test
            for msg_id in DOOR_MSG_ID_LIST.keys():
                m_DLC = DOOR_DLC 
                msg_frame = DOOR_ACT
                error_ok = self.write_msg_frame(m_PCANHandle, msg_id, m_DLC, msg_frame)

                if error_ok == PCAN_ERROR_OK:
                    _, dev_id = self.get_id_from_handle(m_PCANHandle)
                    print('\n[Message] Device {} has been successfully send message "actSensor"'.format(dev_id))
                else:
                    raise ValueError('\033[91m[Error] Error occured while sending the message "actSensor"\033[0m')
                
        else:               # Talegate test
            msg_id = TALEGATE_MSG_ID[0]
            m_DLC = TALEGATE_DLC
            msg_frame = TALEGATE_ACT
            error_ok = self.write_msg_frame(m_PCANHandle, msg_id, m_DLC, msg_frame)
        
            if error_ok == PCAN_ERROR_OK:
                _, dev_id = self.get_id_from_handle(m_PCANHandle)
                print('\n[Message] Device {} has been successfully send message "actSensor"'.format(dev_id))
            else:
                raise ValueError('\033[91m[Error] Error occured while sending the message "actSensor"\033[0m')

    def send_deactSensor(self, m_PCANHandle, kind_of_test):
        if kind_of_test:    # Door test
            for msg_id in DOOR_MSG_ID_LIST.keys():
                m_DLC = DOOR_DLC
                msg_frame = DOOR_ACT
                error_ok = self.write_msg_frame(m_PCANHandle, msg_id, m_DLC, msg_frame)

                if error_ok == PCAN_ERROR_OK:
                    _, dev_id = self.get_id_from_handle(m_PCANHandle)
                    print('[Message] Device {} has been successfully operated "deactSensor"'.format(dev_id))
                else:
                    raise ValueError('\033[91m[Error] Error happens during operating "deactSensor"\033[0m')
                
        else:               # Talegate test
            msg_id = TALEGATE_MSG_ID[0]
            m_DLC = TALEGATE_DLC
            msg_frame = TALEGATE_ACT
            error_ok = self.write_msg_frame(m_PCANHandle, msg_id, m_DLC, msg_frame)
        
            if error_ok == PCAN_ERROR_OK:
                _, dev_id = self.get_id_from_handle(m_PCANHandle)
                print('[Message] Device {} has been successfully operated "sensorStop"'.format(dev_id))
            else:
                raise ValueError('\033[91m[Error] Error happens during operating "sensorStop"\033[0m')

    def send_pcan_cli(self, dev_id, cmd, msg):
        _, m_PCANHandle = self.get_handle_from_id(dev_id)

        DLC_MSG = self.pcan_config['DLC_MSG_BUNDLE'][cmd]
        m_DLC = DLC_MSG[0]
        CLI_header = DLC_MSG[1]
        msg_frame = CLI_header + msg

        error_ok = self.write_msg_frame(m_PCANHandle, self.MSG_ID, m_DLC, msg_frame)
        if error_ok == PCAN_ERROR_OK:
            print('[Message] Device {} has been successfully operated "{}"'.format(dev_id, cmd))
        else:
            print('\033[91m[Error] Error happens during operating "{}". Error Code: {}\033[0m'.format(cmd, error_ok))

    def WaitForEvent(self, receiveEvent, waitTimeout: int = None, abortEvent=None):
        events = [receiveEvent]

        if abortEvent != None:
            events.append(abortEvent)

        readable, _, _ = select.select(events, [], [], waitTimeout / 1000)

        if len(readable) > 0:
            if receiveEvent in readable:
                stsResult = PCAN_ERROR_OK
            elif abortEvent in readable:
                stsResult = PCAN_ERROR_QRCVEMPTY
            else:
                stsResult = PCAN_ERROR_RESOURCE
        else:
            stsResult = PCAN_ERROR_QRCVEMPTY

        return stsResult

    def check_all_handle_status(self):
        stsResult = self.m_objPCANBasic.GetValue(PCAN_NONEBUS, PCAN_ATTACHED_CHANNELS_COUNT)

        if stsResult[0] == PCAN_ERROR_OK:
            stsResult = self.m_objPCANBasic.GetValue(PCAN_NONEBUS, PCAN_ATTACHED_CHANNELS)

            if stsResult[0] == PCAN_ERROR_OK:
                print("-----------------------------------------------------------------------------------------")
                print("Get PCAN_ATTACHED_CHANNELS:")
                print('stsResult:', stsResult[1])
                for currentChannelInformation in stsResult[1]:
                    print('currentChannelInformation.channel_handle):', currentChannelInformation.channel_handle)
                    print("---------------------------")
                    print("channel_handle:      " + self.ConvertToChannelHandle(currentChannelInformation.channel_handle))
                    print("device_features:     " + self.ConvertToChannelFeatures(currentChannelInformation.device_features))
                    print("device_id:           " + str(currentChannelInformation.device_id))
                    print("channel_condition:   " + self.ConvertToChannelCondition(currentChannelInformation.channel_condition))
        if stsResult[0] != PCAN_ERROR_OK:
            print('Failed to check handles status')

    def ConvertToChannelCondition(self,value):
        """
        Convert uint value to readable string value
        """
        switcher = {PCAN_CHANNEL_UNAVAILABLE:"PCAN_CHANNEL_UNAVAILABLE",
                    PCAN_CHANNEL_AVAILABLE:"PCAN_CHANNEL_AVAILABLE",
                    PCAN_CHANNEL_OCCUPIED:"PCAN_CHANNEL_OCCUPIED",
                    PCAN_CHANNEL_PCANVIEW:"PCAN_CHANNEL_PCANVIEW"}

        if value in switcher:
            return switcher[value]
        else:
            return "Status unknown: " + str(value)

    def ConvertToChannelFeatures(self,value):
        """
        Convert uint value to readable string value
        """
        sFeatures = ""

        if (value & FEATURE_FD_CAPABLE) == FEATURE_FD_CAPABLE:
            sFeatures += "FEATURE_FD_CAPABLE"
        if ((value & FEATURE_DELAY_CAPABLE) == FEATURE_DELAY_CAPABLE):
                if (sFeatures != ""):
                    sFeatures += ", FEATURE_DELAY_CAPABLE"
                else:
                    sFeatures += "FEATURE_DELAY_CAPABLE"
        if ((value & FEATURE_IO_CAPABLE) == FEATURE_IO_CAPABLE):
            if (sFeatures != ""):
                sFeatures += ", FEATURE_IO_CAPABLE"
            else:
                sFeatures += "FEATURE_IO_CAPABLE"
        return sFeatures;

    def ConvertToChannelHandle(self, value):
        switcher = {PCAN_USBBUS1.value: "PCAN_USBBUS1",
                    PCAN_USBBUS2.value: "PCAN_USBBUS2",
                    PCAN_USBBUS3.value: "PCAN_USBBUS3",
                    PCAN_USBBUS4.value: "PCAN_USBBUS4",
                    PCAN_USBBUS5.value: "PCAN_USBBUS5",
                    PCAN_USBBUS6.value: "PCAN_USBBUS6",
                    PCAN_USBBUS7.value: "PCAN_USBBUS7",
                    PCAN_USBBUS8.value: "PCAN_USBBUS8",
                    PCAN_USBBUS9.value: "PCAN_USBBUS9",
                    PCAN_USBBUS10.value: "PCAN_USBBUS10",
                    PCAN_USBBUS11.value: "PCAN_USBBUS11",
                    PCAN_USBBUS12.value: "PCAN_USBBUS12",
                    PCAN_USBBUS13.value: "PCAN_USBBUS13",
                    PCAN_USBBUS14.value: "PCAN_USBBUS14",
                    PCAN_USBBUS15.value: "PCAN_USBBUS15",
                    PCAN_USBBUS16.value: "PCAN_USBBUS16",

                    PCAN_LANBUS1.value: "PCAN_LANBUS1",
                    PCAN_LANBUS2.value: "PCAN_LANBUS2",
                    PCAN_LANBUS3.value: "PCAN_LANBUS3",
                    PCAN_LANBUS4.value: "PCAN_LANBUS4",
                    PCAN_LANBUS5.value: "PCAN_LANBUS5",
                    PCAN_LANBUS6.value: "PCAN_LANBUS6",
                    PCAN_LANBUS7.value: "PCAN_LANBUS7",
                    PCAN_LANBUS8.value: "PCAN_LANBUS8",
                    PCAN_LANBUS9.value: "PCAN_LANBUS9",
                    PCAN_LANBUS10.value: "PCAN_LANBUS10",
                    PCAN_LANBUS11.value: "PCAN_LANBUS11",
                    PCAN_LANBUS12.value: "PCAN_LANBUS12",
                    PCAN_LANBUS13.value: "PCAN_LANBUS13",
                    PCAN_LANBUS14.value: "PCAN_LANBUS14",
                    PCAN_LANBUS15.value: "PCAN_LANBUS15",
                    PCAN_LANBUS16.value: "PCAN_LANBUS16",

                    PCAN_PCIBUS1.value: "PCAN_PCIBUS1",
                    PCAN_PCIBUS2.value: "PCAN_PCIBUS2",
                    PCAN_PCIBUS3.value: "PCAN_PCIBUS3",
                    PCAN_PCIBUS4.value: "PCAN_PCIBUS4",
                    PCAN_PCIBUS5.value: "PCAN_PCIBUS5",
                    PCAN_PCIBUS6.value: "PCAN_PCIBUS6",
                    PCAN_PCIBUS7.value: "PCAN_PCIBUS7",
                    PCAN_PCIBUS8.value: "PCAN_PCIBUS8",
                    PCAN_PCIBUS9.value: "PCAN_PCIBUS9",
                    PCAN_PCIBUS10.value: "PCAN_PCIBUS10",
                    PCAN_PCIBUS11.value: "PCAN_PCIBUS11",
                    PCAN_PCIBUS12.value: "PCAN_PCIBUS12",
                    PCAN_PCIBUS13.value: "PCAN_PCIBUS13",
                    PCAN_PCIBUS14.value: "PCAN_PCIBUS14",
                    PCAN_PCIBUS15.value: "PCAN_PCIBUS15",
                    PCAN_PCIBUS16.value: "PCAN_PCIBUS16", }

        if value in switcher:
            return switcher[value]
        else:
            return "Handle unknown: " + str(value)

    def reset_handle(self, m_PCANHandle=None, dev_id=None, input_type='handle'):
        if input_type == 'handle':
            pass
        elif input_type == 'dev_id':
            m_PCANHandle = self.get_handle_from_id(dev_id)
        else:
            print("Input type for reset_handle is incorrect")
        print(f"[Message] DEV {self.get_id_from_handle(m_PCANHandle)[1]}: Tx/Rx msg queues has been reset")
        status = self.m_objPCANBasic.Reset(m_PCANHandle)
        return status

