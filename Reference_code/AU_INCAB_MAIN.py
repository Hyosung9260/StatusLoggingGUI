import numpy as np
import os
from threading import Thread
import struct as st
import datetime
import time
from tqdm import tqdm
from multiprocessing import Process, Manager
import pandas as pd

from SRC_PCAN.PCAN_CONTROLLER import PCANControl
from AU_INCAB_QUEUE_MANAGER import *
from PRE_DEF import *
from SRC_DSP.CPD.AWRL6432_CPD_SP import DspCPD
from SRC_DSP.CPD.AWRL6432_CPD_INTEG import DspCPDInteg
from SRC_DSP.IA.AWRL6432_IA_SP import DspIA
from SRC_DSP.IA.AWRL6432_IA_INTEG import DspIAInteg
from SRC_DSP.DATC.AWRL6432_DATC_SP import DspDATC
from SRC_DSP.DATC.AWRL6432_DATC_INTEG import DspDATCInteg

def int_to_4byte_hex(value):
    hex_representation = value.to_bytes(4, byteorder='little').hex()
    arr_4byte_hex = np.array([str(hex_representation[i:i + 2]) for i in range(0, len(hex_representation), 2)], dtype=str)
    return arr_4byte_hex

def float_to_4byte_hex(value):
    hex_representation = st.pack('f', value).hex()
    arr_4byte_hex = np.array([str(hex_representation[i:i + 2]) for i in range(0, len(hex_representation), 2)], dtype=str)
    return arr_4byte_hex


class Main:
    def __init__(self):
        self.start_flag = False
        self.pcan_ctrl = PCANControl()

        self.app_mode = APP_CPD
        self.op_mode = OPMODE_RT

        self.dev_id_list = []
        self.dev_strt_dict = {}

        self.dsp_integ = None
        self.sel_dict = {}
        self.save_frm = 0

        self.save_data = False
        self.save_name = ''
        self.save_cnt = 0
        self.path_data_load = ''
        self.batch_data_path = ''

        self.batch_result_dict = Manager().dict()
        self.instant_batch_result_dict = Manager().dict()

    def run(self):
        if self.op_mode == OPMODE_BATCH:
            run_batch = Thread(target=self.run_batch_proc, args=())
            run_batch.start()
        else:
            self.run_normal_proc()

    def run_normal_proc(self):
        clear_queue(q_dict)
        self.start_flag = True
        self.init_dev_strt_dict()
        self.init_sel_dict()

        for dev_id in self.dev_id_list:
            dsp_thread = Thread(target=self.dsp_process,
                                args=(self.dev_strt_dict[f'DEV{dev_id}'], ),
                                daemon=True)
            dsp_thread.start()

        if self.op_mode == OPMODE_RT:
            for dev_id in self.dev_id_list:
                read_can_buf_thread = Thread(target=self.read_can_buffer,
                                             args=(dev_id, self.dev_strt_dict[f'DEV{dev_id}']),
                                             daemon=True)
                read_can_buf_thread.start()

        elif self.op_mode == OPMODE_DL:
            data_load_thread = Thread(target=self.data_load,
                                      args=(self.dev_strt_dict, self.path_data_load),
                                      daemon=True)
            data_load_thread.start()

        elif self.op_mode == OPMODE_BATCH:
            data_load_thread = Thread(target=self.data_load,
                                      args=(self.dev_strt_dict, self.batch_data_path),
                                      daemon=True)
            data_load_thread.start()
            data_load_thread.join()
            self.stop()

        else:
            raise ValueError('Wrong Operation Mode is selected')

    def stop(self):
        self.start_flag = False
        for key, dev_strt in self.dev_strt_dict.items():
            q_dict[f'APP_RUN{dev_strt.dev_id}'].put(INVALID)
        time.sleep(0.05)
        self.dev_strt_dict.clear()
        self.sel_dict.clear()
        self.dsp_integ = None

    def run_batch_proc(self):
        if self.path_data_load == '':
            rawdata_storage = RAWDATA_PATH
        else:
            rawdata_storage = self.path_data_load

        try:
            entries = os.listdir(rawdata_storage)
            rawdata_dirs = [entry for entry in entries if os.path.isdir(os.path.join(rawdata_storage, entry))]
        except FileNotFoundError:
            raise ValueError(f"Error: The directory {rawdata_storage} does not exist.")
        except Exception as e:
            raise ValueError(f"An error occurred: {e}")
        # print('rawdata_dirs:', rawdata_dirs)
        batch_progress = tqdm(total=len(rawdata_dirs), desc='BATCH_PROGRESS', maxinterval=100, unit='case')

        processes = []
        for cnt, rawdata_dir in enumerate(rawdata_dirs):
            self.batch_data_path = os.path.join(rawdata_storage, rawdata_dir)
            p = Process(target=self.run_normal_proc, args=())
            processes.append(p)
            p.start()

            if ((cnt + 1) % 10 == 0) or (cnt + 1) == len(rawdata_dirs):
                for p in processes:
                    p.join()
                    batch_progress.update(1)
                processes.clear()
        for proc in processes:
            proc.kill()
        # print('self.batch_data_path:', self.batch_data_path)
        self.extract_batch_result(rawdata_dirs)

    def extract_batch_result(self, rawdata_dirs):
        output_dict = {'NAME': [],
                       STR_MOTION: [],
                       STR_VITAL: [],
                       STR_NONE: [],
                       STR_UNKNOWN: [],
                       STR_ROCKING: [],
                       'Frame': []}

        instant_output_dict = {'NAME': [],
                       STR_MOTION: [],
                       STR_VITAL: [],
                       STR_NONE: [],
                       STR_UNKNOWN: [],
                       STR_ROCKING: [],
                       'Frame': []}

        for rawdata_dir in rawdata_dirs:
            for dev_id in self.dev_id_list:
                output_dict['NAME'].append(f'{rawdata_dir}_DEV{dev_id}')
                output_dict[STR_MOTION].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_MOTION])
                output_dict[STR_VITAL].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_VITAL])
                output_dict[STR_NONE].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_NONE])
                output_dict[STR_UNKNOWN].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_UNKNOWN])
                output_dict[STR_ROCKING].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_ROCKING])
                output_dict['Frame'].append(self.batch_result_dict[f'{rawdata_dir}_DEV{dev_id}']['Frame'])

                instant_output_dict['NAME'].append(f'{rawdata_dir}_DEV{dev_id}')
                instant_output_dict[STR_MOTION].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_MOTION])
                instant_output_dict[STR_VITAL].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_VITAL])
                instant_output_dict[STR_NONE].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_NONE])
                instant_output_dict[STR_UNKNOWN].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_UNKNOWN])
                instant_output_dict[STR_ROCKING].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}'][STR_ROCKING])
                instant_output_dict['Frame'].append(self.instant_batch_result_dict[f'{rawdata_dir}_DEV{dev_id}']['Frame'])

        print('[Message] Extracting the batch result...')
        if not os.path.exists(f"./{BATCH_RESULT_PATH}"):
            os.makedirs(f"./{BATCH_RESULT_PATH}")
        now = datetime.datetime.now()
        formatted_date = now.strftime("%m_%d_%H_%M_%S")
        df = pd.DataFrame(output_dict)
        df.to_excel(f"./{BATCH_RESULT_PATH}/{formatted_date}_batch_result.xlsx", index=False)

        df_inst = pd.DataFrame(instant_output_dict)
        df_inst.to_excel(f"./{BATCH_RESULT_PATH}/{formatted_date}_instant_batch_result.xlsx", index=False)
        print('[Message] Extracting the batch result is completed')

    def pcan_activate(self):
        self.pcan_ctrl = PCANControl()

    def pcan_deactivate(self):
        self.pcan_ctrl = None

    def dev_connect(self, dev_id):
        if dev_id in self.dev_id_list:
            print('Already Connected Device')
            print(f'Connected Device List:{self.dev_id_list}')
            retval = False
        else:
            if self.op_mode == OPMODE_RT:
                connect_result = self.pcan_ctrl.initialize(dev_id=dev_id)
            else:
                connect_result = True

            if connect_result:
                self.dev_id_list.append(dev_id)
                print('Connected Device List:{}'.format(self.dev_id_list))
                retval = True
            else:
                retval = False
        return retval

    def dev_disconnect(self, dev_id):
        if dev_id in self.dev_id_list:
            if self.op_mode == OPMODE_RT:
                disconnect_result = self.pcan_ctrl.uninitialize(dev_id=dev_id)
            else:
                disconnect_result = True

            if disconnect_result:
                self.dev_id_list.remove(dev_id)
                print('Connected Device List:{}'.format(self.dev_id_list))
                retval = True
            else:
                retval = False
        else:
            print('Not Connected Device')
            print('Connected Device List:{}'.format(self.dev_id_list))
            retval = False
        return retval

    def init_dev_strt_dict(self):
        if self.app_mode == APP_CPD:
            dsp = DspCPD
            self.dsp_integ = DspCPDInteg()
        elif self.app_mode == APP_IA:
            dsp = DspIA
            self.dsp_integ = DspIAInteg()
        elif self.app_mode == APP_DATC:
            dsp = DspDATC
            self.dsp_integ = DspDATCInteg()
        else:
            raise ValueError("Such application mode doesn't exit")

        for dev_id in self.dev_id_list:
            self.dev_strt_dict['DEV{}'.format(dev_id)] = dsp(dev_id=dev_id)

    def init_sel_dict(self):
        # if self.app_mode == APP_CPD:
        self.sel_dict['DEVID'] = self.dev_id_list[0]
        self.sel_dict['FRMIDX'] = 0
        self.sel_dict['RNGIDX'] = 0
        self.sel_dict['CHPIDX'] = 0
        self.sel_dict['DPLIDX'] = 0
        self.sel_dict['TARGIDX'] = 0
        # else:
        #     raise ValueError("Such application mode doesn't exit")

    def update_save_cfg(self, enable=False, name='', save_cnt=6000):
        dt = datetime.datetime.now()
        month = f'{dt.month}' if dt.month >= 10 else f'0{dt.month}'
        day = f'{dt.day}' if dt.day >= 10 else f'0{dt.day}'
        mmdd_name = month + day + '_' + name

        if os.path.exists('{}/{}'.format(RAWDATA_PATH, mmdd_name)):
            for i in range(100):
                if not os.path.exists(f"{RAWDATA_PATH}/{mmdd_name}_new{i}"):
                    mmdd_name = f'{mmdd_name}_new{i}'
                    break

        self.save_name = mmdd_name
        self.save_cnt = save_cnt
        self.save_data = enable

    def get_graph_data(self, plot_option):
        # print('get_graph_data')
        dsp_inst = self.dev_strt_dict['DEV{}'.format(self.sel_dict['DEVID'])]
        pen_color = None
        text = None
        pos_conf = False
        position = 0

        if plot_option == 'CPD_RichUI':
            # integ_stat = self.dsp_integ.final_result_stat[self.sel_dict['FRMIDX']]
            # class_cnt_arr = self.dsp_integ.class_cnt_arr[self.sel_dict['FRMIDX']]
            graph_data = [[],
                          [],
                          []]

            # 0. Target Position + Magnitude
            num_target = np.where(dsp_inst.target_info[self.sel_dict['FRMIDX']]['CLASS3'])[0]
            target_info = dsp_inst.target_info[self.sel_dict['FRMIDX'], num_target]

            if not np.any(num_target):
                X = []
                Z = []
                size = 0
                color = (0, 0, 0, 0)
            else:
                X = target_info['X']
                Z = target_info['Z']
                size = 3 * np.sqrt(target_info['POW'])

                if target_info['CLASS3'][0] == CLS_MOTION:
                    color = (0, 0, 255, 180)
                elif target_info['CLASS3'][0] == CLS_VITAL:
                    color = (0, 255, 0, 180)
                elif target_info['CLASS3'][0] == CLS_ROCKING:
                    color = (255, 165, 0, 180)
                else:
                    color = (0, 0, 0, 0)

            init_warn = dsp_inst.init_warn[self.sel_dict['FRMIDX']]
            if init_warn[0] == CLS_MOTION:
                result_text = '  Adult\nDetected'
                result_color = (0, 0, 255, 180)
            elif init_warn[0] == CLS_VITAL:
                result_text = '   Baby\nDetected'
                result_color = (0, 255, 0, 180)
            else:
                result_text = '  None  '
                result_color = (0, 0, 0, 180)

            graph_data[0] += [Z, X, size, color, result_text, result_color]

            # 1. Classification Percentage
            result_history = dsp_inst.result_history[self.sel_dict['FRMIDX']]
            C_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_COLLECT)) / len(result_history)
            A_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_MOTION)) / len(result_history)
            B_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_VITAL)) / len(result_history)
            E_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_NONE)) / len(result_history)
            U_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_UNKNOWN)) / len(result_history)
            R_hist = 100 * np.sum(np.count_nonzero(result_history == CLS_ROCKING)) / len(result_history)
            result_list = [C_hist, A_hist, B_hist, E_hist, U_hist, R_hist]

            class_cnt_arr = dsp_inst.class_cnt_arr[self.sel_dict['FRMIDX']]
            total_sum = sum(class_cnt_arr[field] for field in class_cnt_arr.dtype.names)

            if total_sum == 0:
                C = A = B = E = U = R = 0
            else:
                C = class_cnt_arr[STR_COLLECT] * (100 / total_sum)
                A = class_cnt_arr[STR_MOTION] * (100 / total_sum)
                B = class_cnt_arr[STR_VITAL] * (100 / total_sum)
                E = class_cnt_arr[STR_NONE] * (100 / total_sum)
                U = class_cnt_arr[STR_UNKNOWN] * (100 / total_sum)
                R = class_cnt_arr[STR_ROCKING] * (100 / total_sum)
            class_list = [C, A, B, E, U, R]
            graph_data[1] += [result_list, class_list]

            # 3. Slow Time & Doppler Graph
            time_dpl_arr = dsp_inst.time_dpl_arr[self.sel_dict['FRMIDX']]
            for time_dpl in time_dpl_arr:
                graph_data[2].append(time_dpl)
            # graph_data[4] = integ_stat['Result']

        elif plot_option == 'IA_RichUI':
            graph_data = [[],
                          [],
                          []]

            num_target = dsp_inst.target_info[self.sel_dict['FRMIDX'], 0]['TGT']
            target_info = dsp_inst.frm_xyz_coords[self.sel_dict['FRMIDX'], :num_target]
            num_cluster = dsp_inst.target_info[self.sel_dict['FRMIDX'], 0]['CLS']
            cluster_info = dsp_inst.XYZ_cluster_mean[self.sel_dict['FRMIDX'], :num_cluster]

            if not np.any(num_target):
                X = []
                Y = []
                Z = []
                cluster_X = []
                cluster_Y = []
                cluster_Z = []
                size = 0
                color = (0, 0, 0, 0)
                cluster_color = (0, 0, 0, 0)
            else:
                X = target_info[:,0]
                Y = target_info[:,1]
                Z = target_info[:,2]
                cluster_X = cluster_info[:, 0]
                cluster_Y = cluster_info[:, 1]
                cluster_Z = cluster_info[:, 2]
                # size = 3 * np.sqrt(target_info['POW'])
                color = (0, 255, 0, 80)
                cluster_color = (255, 0, 0, 250)

            graph_data[0] += [Z, X, color, cluster_Z, cluster_X, cluster_color]
            graph_data[1] += [Z, Y, color, cluster_Z, cluster_Y, cluster_color]
            graph_data[2] = dsp_inst.final_result_history[self.sel_dict['FRMIDX']]

        elif plot_option == 'Range-Azimuth(Fast)':
            graph_data = dsp_inst.anty_az_rg[self.sel_dict['FRMIDX']]
        elif plot_option == 'Range-Elevation(Fast)':
            graph_data = dsp_inst.antx_el_rg[self.sel_dict['FRMIDX']]
        elif plot_option == 'Range-Doppler(Fast)':
            graph_data = np.abs(dsp_inst.dpl_vrx_rg[self.sel_dict['FRMIDX']]).transpose(1, 0, 2)
        elif plot_option == 'RD_NCI':
            graph_data = np.abs(dsp_inst.dpl_vrx_rg[self.sel_dict['FRMIDX']]).transpose(1, 0, 2)
        elif plot_option == 'Range-EachRX(Fast)':
            graph_data = np.abs(dsp_inst.chp_vrx_rg[self.sel_dict['FRMIDX'], self.sel_dict['CHPIDX'], :, :])
        elif plot_option == 'Chirp-EachRX(Fast)':
            graph_data = dsp_inst.chp_vrx_rg[self.sel_dict['FRMIDX'], :, :, self.sel_dict['RNGIDX']].transpose()
        elif plot_option == 'Range-Azimuth(Slow)':
            graph_data = dsp_inst.anty_az_rg_slow[self.sel_dict['FRMIDX']]
        elif plot_option == 'Range-Elevation(Slow)':
            graph_data = dsp_inst.antx_el_rg_slow[self.sel_dict['FRMIDX']]
        elif plot_option == 'Range-Doppler(Slow)':
            graph_data = np.abs(dsp_inst.dpl_vrx_rg_slow[self.sel_dict['FRMIDX']]).transpose(1, 0, 2)
        elif plot_option == 'Range-EachRX(Slow)':
            graph_data = np.sum(np.abs(dsp_inst.chp_vrx_rg_slow[self.sel_dict['FRMIDX'], :, :, :]), axis=0)
        elif plot_option == 'Chirp-EachRX(Slow)':
            chp_vrx_rg_slow = dsp_inst.chp_vrx_rg_slow[self.sel_dict['FRMIDX'], :, :, self.sel_dict['RNGIDX']].transpose()
            graph_data = chp_vrx_rg_slow - np.mean(chp_vrx_rg_slow, axis=1, keepdims=True)
        elif plot_option == 'Doppler-EachRX(Slow)':
            graph_data = np.abs(dsp_inst.dpl_vrx_rg_slow[self.sel_dict['FRMIDX'], :, :, self.sel_dict['RNGIDX']].transpose())
        elif plot_option == 'Chirp_Repres(1D)':
            graph_org = dsp_inst.chp_repres[self.sel_dict['FRMIDX']]
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = graph_org[-6:, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], -6:]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], -6:]
            else:
                graph_data = graph_org[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6]

            pen_color = []
            for i in range(6):
                if feat[STR_ROCKING][i] >= dsp_inst.th_rock_suspect:
                    pen_color.append('w')
                else:
                    pen_color.append('g')

        elif plot_option == 'Chirp_Repres(2D)':
            graph_org = dsp_inst.chp_repres[self.sel_dict['FRMIDX']]
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = graph_org[-6:, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], -6:]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], -6:]
            else:
                graph_data = graph_org[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6]

            pen_color = []
            for i in range(6):
                if feat[STR_ROCKING][i] >= dsp_inst.th_rock_suspect:
                    pen_color.append('r')
                else:
                    pen_color.append('g')

        elif plot_option == 'Doppler_Repres':
            graph_org = dsp_inst.dpl_repres[self.sel_dict['FRMIDX']]
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = graph_org[-6:, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], -6:]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], -6:]
            else:
                graph_data = graph_org[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6]
                feat = dsp_inst.feature[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX'] + 6]
            pen_color = []
            for i in range(6):
                if feat[STR_ROCKING][i] >= dsp_inst.th_rock_suspect:
                    pen_color.append('r')
                else:
                    pen_color.append('g')

        elif plot_option == 'Azimuth-Elevation(Fast)':
            el_az_rg = np.sum(np.abs(dsp_inst.dpl_el_az_rg[self.sel_dict['FRMIDX']]), axis=0)
            if (dsp_inst.roi[1] - 6) < self.sel_dict['RNGIDX']:
                el_az_roi = el_az_rg[:, :, -6:]
            else:
                el_az_roi = el_az_rg[:, :, self.sel_dict['RNGIDX']:self.sel_dict['RNGIDX']+6]
            graph_data = el_az_roi.transpose(2, 1, 0)

        elif plot_option == 'Azimuth-Elevation(Slow)':
            el_az_rg = np.sum(np.abs(dsp_inst.dpl_el_az_rg_slow[self.sel_dict['FRMIDX']]), axis=0).transpose((1, 0, 2))
            if (dsp_inst.roi[1] - 6) < self.sel_dict['RNGIDX']:
                el_az_roi = el_az_rg[:, :, -6:]
            else:
                el_az_roi = el_az_rg[:, :, self.sel_dict['RNGIDX']:self.sel_dict['RNGIDX'] + 6]
            graph_data = el_az_roi.transpose(2, 1, 0)

        elif plot_option == 'STFT_Heatmap':
            stft_repres = dsp_inst.stft_repres[self.sel_dict['FRMIDX']]
            # stft_repres = np.abs(dsp_inst.conv_stft_repres[self.sel_dict['FRMIDX']])
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = stft_repres[-6:, :, :]
            else:
                graph_data = stft_repres[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6, :, :]

        elif plot_option == 'STFT_Track':
            graph_org = dsp_inst.stft_track[self.sel_dict['FRMIDX']]['FIDX']
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = graph_org[-6:, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], -6:]
            else:
                graph_data = graph_org[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6]

        elif plot_option == 'STFT_Track_FFT':
            graph_org = dsp_inst.stft_track_fft[self.sel_dict['FRMIDX']]
            if (dsp_inst.DEF_NUM_MAX_TARGET - 6) < self.sel_dict['TARGIDX']:
                graph_data = graph_org[-6:, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], -6:]
            else:
                graph_data = graph_org[self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6, :]
                text = dsp_inst.target_info[self.sel_dict['FRMIDX'], self.sel_dict['TARGIDX']:self.sel_dict['TARGIDX']+6]

        elif plot_option == 'G-Sensor':
            graph_data = []
            for i in range(3):
                g_sens_hist = dsp_inst.g_sens_xyz_hist[self.sel_dict['FRMIDX'], :, i]
                g_sens_feat = dsp_inst.g_sens_min_max[self.sel_dict['FRMIDX'], i]
                graph_data.append([g_sens_hist, g_sens_feat])
            for i in range(3):
                g_sens_hist = dsp_inst.g_sens_fft[self.sel_dict['FRMIDX'], :, i]
                g_sens_feat = np.max(dsp_inst.g_sens_fft[self.sel_dict['FRMIDX'], :, i])
                graph_data.append([g_sens_hist, g_sens_feat])
        elif plot_option == 'ETC':
            graph_data = dsp_inst.motion_spectrum[self.sel_dict['FRMIDX']]

        return graph_data, pen_color, text, pos_conf, position


    def get_info(self):
        dsp_inst = self.dev_strt_dict['DEV{}'.format(self.sel_dict['DEVID'])]
        info = dsp_inst.target_info[self.sel_dict['FRMIDX']]
        rock_th = dsp_inst.th_rock_suspect
        feat = dsp_inst.feature[self.sel_dict['FRMIDX']]
        stat = dsp_inst.final_result_stat[self.sel_dict['FRMIDX']]
        mara = dsp_inst.chp_repres_mag_rad[self.sel_dict['FRMIDX']]
        init_warn = dsp_inst.init_warn[self.sel_dict['FRMIDX']]
        return info, rock_th, feat, stat, mara, init_warn

    def get_ia_info(self):
        dsp_inst = self.dev_strt_dict['DEV{}'.format(self.sel_dict['DEVID'])]
        stat = dsp_inst.final_result_stat[self.sel_dict['FRMIDX']]
        return stat

    def apply_cfg_via_pcan(self, cfg_dict:dict):
        if not self.dev_id_list:
            print('[Message] Device is not connected')
        elif self.op_mode != OPMODE_RT:
            print('[Message] Operation mode is not "Python Real-time"')
        else:
            print('\n------------------------------------------')
            for key, val in cfg_dict.items():
                print('{}: {}'.format(key, val))
            print('------------------------------------------')

            for dev_id in self.dev_id_list:
                cmd = cfg_dict['command']
                msg = ['00'] * 64
                max_idx = 0
                for key, val in cfg_dict.items():
                    if key == 'command':
                        continue

                    if isinstance(val, int):
                        sub_msg = int_to_4byte_hex(val)
                    elif isinstance(val, float):
                        sub_msg = float_to_4byte_hex(val)
                    else:
                        sub_msg = None
                        print('Not allowed cfg_dict value type')

                    idx = int(key[-1])
                    if idx > max_idx:
                        max_idx = idx
                    msg[idx * 4: (idx + 1) * 4] = sub_msg
                msg = msg[:(max_idx + 1) * 4]
                self.pcan_ctrl.send_pcan_cli(dev_id, cmd, msg)

    def get_min_max_sel_dict(self):
        dsp_inst = self.dev_strt_dict['DEV{}'.format(self.sel_dict['DEVID'])]
        ret_dict = dict()
        ret_dict['DEVIDLIST'] = self.dev_id_list
        # if self.app_mode == APP_CPD:
        ret_dict['FRMMIN'] = 0
        ret_dict['FRMMAX'] = dsp_inst.num_frame
        ret_dict['RNGMIN'] = 0
        ret_dict['RNGMAX'] = dsp_inst.DEF_DATA_NUM_RFFT
        ret_dict['CHPMIN'] = 0
        ret_dict['CHPMAX'] = dsp_inst.DEF_NUM_CHP_PER_FRAME // dsp_inst.DEF_ANT_TX_NUM
        ret_dict['DPLMIN'] = 0
        ret_dict['DPLMAX'] = dsp_inst.DEF_NUM_FFT_DPL
        ret_dict['TARGMIN'] = 0
        ret_dict['TARGMAX'] = dsp_inst.DEF_NUM_MAX_TARGET
        return ret_dict

    def dsp_process(self, dev_struct):
        dev_id = dev_struct.dev_id
        print(f'[Message] Device{dev_id} DSP Start')

        while True:
            payload = q_dict[f'APP_RUN{dev_id}'].get()
            remaining_q = q_dict[f'APP_RUN{dev_id}'].qsize()
            if remaining_q:
                print(f"\033[91mWarn: Device{dev_id} Data processing is slow. Number of remaining is :{remaining_q} \033[0m")

            if payload != INVALID:
                if self.save_data:
                    self.save_data_buffer(dev_struct)
                else:
                    dev_struct.save_cnt = 0
                dev_struct.app_run()
            else:
                break

            self.dsp_integ.app_run()

            if self.op_mode == OPMODE_RT:
                q_dict['graph_update'].put(True)
            elif self.op_mode in [OPMODE_DL, OPMODE_BATCH]:
                q_dict['data_load'].put(True)
            else:
                #TODO Embedded mode
                q_dict['graph_update'].put(True)
            print(f'Device{dev_id} {dev_struct.loop_cnt}th DSP has been processed')

        print(f'[Message] "Device{dev_id} dsp_process" has been terminated\n')

    def save_data_buffer(self, dev_struct):
        if dev_struct.save_cnt >= self.save_cnt:
            print(f'\033[92m[Message] {self.save_cnt} frame data is saved\033[0m')
        else:
            if not os.path.exists(f"{RAWDATA_PATH}/{self.save_name}"):
                os.makedirs(f"{RAWDATA_PATH}/{self.save_name}")

            filename = f"{RAWDATA_PATH}/{self.save_name}/rawdata_DEV{dev_struct.dev_id}.bin"
            data_buffer = dev_struct.rawdata_buffer[:dev_struct.DEF_DATA_LENGTH_PER_FRAME]

            gsens_filename = f"{RAWDATA_PATH}/{self.save_name}/rawdata_DEV{dev_struct.dev_id}_gsens.bin"
            gsens_data_buffer = dev_struct.g_sens_xyz_buffer[:]

            with open(filename, 'ab') as file:
                data_buffer.tofile(file)
            with open(gsens_filename, 'ab') as file:
                gsens_data_buffer.tofile(file)

            dev_struct.save_cnt += 1
            print(f"[RAWDATA-SAVE] <{self.save_name}_DEV{dev_struct.dev_id}> {dev_struct.save_cnt} th data is saved")

    def data_load(self, DevStructDict:dict, path_data_load):
        if path_data_load == '':
            for dev_name, dev_struct in DevStructDict.items():
                q_dict[f'APP_RUN{dev_struct.dev_id}'].put(INVALID)
                print('[MESSAGE] Path for data load is not selected')
        else:
            data_list = os.listdir(path_data_load)

            selected_path_dict = {}
            load_gsens_data_dict = {}
            for dev_name in DevStructDict.keys():
                data_name = 'rawdata_{}.bin'.format(dev_name)
                if data_name in data_list:
                    selected_path_dict[dev_name] = os.path.join(path_data_load, data_name)

                gsens_data_name = 'rawdata_{}_gsens.bin'.format(dev_name)
                if gsens_data_name in data_list:
                    load_gsens_data_dict[dev_name] = np.fromfile(os.path.join(path_data_load, gsens_data_name), dtype=np.int16)

            load_data_dict = {}
            num_frame_list = []
            for dev_name, path in selected_path_dict.items():
                load_data_dict[dev_name] = np.fromfile(path, dtype=np.int16)
                num_frame = len(load_data_dict[dev_name]) // DevStructDict[dev_name].DEF_DATA_LENGTH_PER_FRAME
                num_frame_list.append(num_frame)
            num_frame = min(num_frame_list)

            for dev_name, dev_struct in DevStructDict.items():
                dev_struct.num_frame = num_frame
                dev_struct.update_strt()
                dev_struct.frame_report = True

            for idx in range(num_frame):
                if self.start_flag:
                    for dev_name, dev_struct in DevStructDict.items():
                        dev_struct.rawdata_buffer = np.append(dev_struct.rawdata_buffer,
                                                              load_data_dict[dev_name][idx * dev_struct.DEF_DATA_LENGTH_PER_FRAME:
                                                                                       (idx + 1) * dev_struct.DEF_DATA_LENGTH_PER_FRAME])
                        if dev_name in load_gsens_data_dict:
                            dev_struct.g_sens_xyz_buffer[:] = load_gsens_data_dict[dev_name][idx * 3:(idx + 1) * 3]
                        q_dict[f'APP_RUN{dev_struct.dev_id}'].put(True)
                    q_dict[f'data_load'].get()
                else:
                    for dev_name, dev_struct in DevStructDict.items():
                        q_dict[f'APP_RUN{dev_struct.dev_id}'].put(INVALID)
                    break
                print('\n')

            for dev_name, dev_struct in DevStructDict.items():
                if self.op_mode == OPMODE_BATCH:
                    data_name = self.batch_data_path.split("\\")[-1]
                    self.batch_result_dict[f'{data_name}_{dev_name}'] = dev_struct.final_result_stat[-1]
                    self.instant_batch_result_dict[f'{data_name}_{dev_name}'] = dev_struct.instant_result_stat[-1]
                q_dict[f'APP_RUN{dev_struct.dev_id}'].put(INVALID)
        print('[Message] data_load has been terminated')

    def read_can_buffer(self, dev_id=None, dev_struct=None):
        _, pcan_handle = self.pcan_ctrl.get_handle_from_id(dev_id)
        _, receive_event = self.pcan_ctrl.InitializeEvent(Channel=pcan_handle)

        if self.pcan_ctrl.reset_handle(pcan_handle) != 0:
            raise ValueError('Reset PCAN Handle is failed')
        self.pcan_ctrl.send_sensorStart(pcan_handle)
        time.sleep(0.05)

        buf_array = np.zeros(0, dtype=np.int16)
        buf_enable = False

        t2 = 0
        while self.start_flag:
            flag, buf_unit, msg_id = self.pcan_ctrl.read_unit_buf(m_PCANHandle=pcan_handle,
                                                          recv_event=receive_event,
                                                          wait_time=1000,
                                                          output_mode='numpy',
                                                          evt_mode=False)

            if msg_id == int(self.pcan_ctrl.pcan_config['RECV_MSG_ID'], 16):
                if (flag[0] == flag[1] == flag[2] == int(self.pcan_ctrl.pcan_config['data_start_flag'], 16)) and (flag[4] == 0x00):  # data block의 시작을 알림 (유의미 데이터 X)
                    buf_array = np.zeros(0, dtype=np.int16)

                elif (flag[0] == flag[1] == flag[2] == int(self.pcan_ctrl.pcan_config['data_end_flag'], 16)) and (flag[4] == 0x00):  # data block의 끝을 알림 (유의미 데이터 X)
                    if buf_enable:
                        t1 = time.time()
                        print('data time:', t1 - t2)
                        t2 = t1

                        dev_struct.rawdata_buffer = np.append(dev_struct.rawdata_buffer, buf_array)
                        q_dict[f'APP_RUN{dev_id}'].put(True)
                    else:
                        buf_enable = True

                else:  # data block의 실제 유의미 데이터 수신
                    if buf_enable:
                        buf_array = np.append(buf_array, buf_unit)
            elif msg_id == int(self.pcan_ctrl.pcan_config['RECV_GSENS_ID'], 16):
                dev_struct.g_sens_xyz_buffer[:] = buf_unit[:3]
            else:
                continue


        self.pcan_ctrl.CloseEvent(receive_event)
        self.pcan_ctrl.send_sensorStop(pcan_handle)
        print("[Message] 'read_can_buffer' has been terminated")
