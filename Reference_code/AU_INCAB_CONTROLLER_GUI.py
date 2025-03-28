import sys
import datetime
from functools import partial
import json
import platform
import ctypes

import pyqtgraph as pg
from PyQt5.QtWidgets import *
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, QThread, Qt
from PyQt5.QtTest import *
from PyQt5.QtGui import QColor, QPixmap, QTransform, QBrush, QFont

from AU_INCAB_MAIN import Main
from AU_INCAB_QUEUE_MANAGER import *
from PRE_DEF import *

UIClass = uic.loadUiType('AWRL6432_INCAB_UI.ui')[0]      # .ui 파일을 load하여 Class로 변환 함
DialogClass = uic.loadUiType('DIALOG.ui')[0]

with open("variables.json") as file:
    variables = json.load(file)


class GuiMain(QMainWindow, UIClass):
    def __init__(self):
        super().__init__()          # 부모 클래스(QMainWindow)로부터 instance와 method를 상속 받음
        self.setupUi(self)          # uic를 화면에 출력 할 수 있도록 셋업

        self.init_button()          # initialize button, combobox, tab

        self.plot_obj_list = []
        self.type_list = []
        self.text_list = []
        self.plot_option = ''

        self.dialog = None
        self.start_time = datetime.datetime.now()

        self.main = Main()
        self.main.op_mode = self.CMBB_OP_MODE.currentIndex()
        self.select_app_mode()

    def init_button(self):
        ''' Connect Each Button to Corresponding Function '''
        self.BTN_START.clicked.connect(self.func_start)
        self.BTN_STOP.clicked.connect(self.func_stop)
        self.BTN_EXIT.clicked.connect(self.func_exit)
        self.TOGGLE_SAVE.clicked.connect(self.func_save)
        self.BTN_DATALOAD.clicked.connect(self.get_path_for_data_load)
        self.BTN_PLOTSETTING.clicked.connect(partial(self.open_dialog, self.BTN_PLOTSETTING))

        self.BTN_START.setShortcut("F5")
        self.BTN_STOP.setShortcut("F6")
        self.BTN_EXIT.setShortcut("F7")
        self.BTN_PLOTSETTING.setShortcut("F8")
        self.BTN_DATALOAD.setShortcut("F9")

        self.CMBB_OP_MODE.currentTextChanged.connect(self.read_op_mode)
        self.CMBB_CPD_PLOT_SELECT.currentTextChanged.connect(self.plot_select)
        self.CMBB_IA_PLOT_SELECT.currentTextChanged.connect(self.plot_select)
        self.CMBB_DATC_PLOT_SELECT.currentTextChanged.connect(self.plot_select)

        for radio in self.GROUP_APPMODE.findChildren(QRadioButton):
            radio.clicked.connect(self.select_app_mode)

        for push in self.CAN_CONNECTION_GROUP.findChildren(QPushButton):
            push.clicked.connect(partial(self.toggle_dev_connection, push))     # partial 함수를 통해 connect으로 호출 되는 함수에 args를 전달 할 수 있음

        for push in self.FIXED_FRAME_TAB_BACKGROUND_CFG.findChildren(QPushButton):
            if type(push.parent()) == QGroupBox:
                push.clicked.connect(partial(self.cfg_value_to_main, push))

        self.BUTTON_CFGLOAD.clicked.connect(self.load_cfg_file)
        self.BUTTON_CFGSAVE.clicked.connect(self.save_cfg_file)

        self.CHK_FEAT.stateChanged.connect(self.graph_update)
        self.CHK_INIT_WARN.stateChanged.connect(self.graph_update)

    def init_graph(self):
        self.plot_select()

    def toggle_dev_connection(self, toggle_obj):
        toggle_name = toggle_obj.objectName()       # TOGGLE_DEVICE'X' 를 반환 함, 'X'는 숫자
        spinbox_obj = self.CAN_CONNECTION_GROUP.findChild(QSpinBox, 'SPINBOX_DEVICE' + toggle_name[-1])     # objName이 SPINBOX_DEIVCE'X'에 해당하는 object 반환
        dev_id = spinbox_obj.value()  # spinbox 값 읽어오기

        if toggle_obj.isChecked():                                                  # Enabling Process (현재 OFF 일 경우)
            connect_result = self.main.dev_connect(dev_id=dev_id)
            if connect_result:
                self.update_spinbox_status(True, spinbox_obj)
            else:
                if toggle_obj.isChecked():
                    toggle_obj.toggle()
        else:                                                                           # Disabling Process (현재 ON 일 경우)
            disconnect_result = self.main.dev_disconnect(dev_id=dev_id)
            if disconnect_result:
                self.update_spinbox_status(False, spinbox_obj)
            else:
                print('\033[35mNotice: dev_id:\033[0m{}\033[35m is abnormally disconnected.Recommend reset all the PCAN handle\033[0m\n'.format(dev_id))

    def update_spinbox_status(self, enabling, spinbox_obj):
        if enabling:
            spinbox_obj.setReadOnly(True)
            spinbox_obj.setStyleSheet('color: black; background-color: lightgray;')
        else:
            spinbox_obj.setReadOnly(False)
            spinbox_obj.setStyleSheet('color: black; background-color: white;')

    def select_app_mode(self):
        if self.RADIO_CPD.isChecked():
            self.main.app_mode = APP_CPD
        elif self.RADIO_IA.isChecked():
            self.main.app_mode = APP_IA
        elif self.RADIO_DATC.isChecked():
            self.main.app_mode = APP_DATC
        else:
            print('App mode should be selected')
        self.print_current_mode()
        self.init_graph()

    def read_op_mode(self):
        for dev_id in self.main.dev_id_list:
            self.main.dev_disconnect(dev_id)
        for toggle in self.CAN_CONNECTION_GROUP.findChildren(QPushButton):
            if toggle.isChecked():
                toggle.toggle()
        for spin in self.CAN_CONNECTION_GROUP.findChildren(QSpinBox):
            spin.setReadOnly(False)
            spin.setStyleSheet('color: black; background-color: white;')
        self.main.dev_id_list.clear()
        self.main.op_mode = self.CMBB_OP_MODE.currentIndex()
        self.print_current_mode()
        if self.main.op_mode == OPMODE_BATCH:
            self.main.pcan_deactivate()
        else:
            self.main.pcan_activate()

    def print_current_mode(self):
        for rb in self.GROUP_APPMODE.findChildren(QRadioButton):
            if rb.isChecked():
                rb_text = rb.text()
        print('""" Opration Mode --> [ App_Mode:\033[91m{:>5}\033[0m,  Input_Type:\033[91m{:>20}\033[0m ] """'.format(rb_text, self.CMBB_OP_MODE.currentText()))

    def activate_btn(self, btn):
        btn.setEnabled(True)

    def deactivate_btn(self, btn):
        btn.setEnabled(False)

    def activate_tab(self):
        for i in range(self.FUNCTION_TAB.count()):
            self.FUNCTION_TAB.setTabEnabled(i, True)

    def deactivate_tab(self):
        for i in range(self.FUNCTION_TAB.count()):
            if i != self.main.app_mode:
                self.FUNCTION_TAB.setTabEnabled(i, False)

    def activate_objects_in_widget(self, widget=None):
        for obj in widget.findChildren((QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QCheckBox, QPushButton)):
            obj.setEnabled(True)

    def deactivate_objects_in_widget(self, widget=None):
        for obj in widget.findChildren((QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QCheckBox, QPushButton)):
            obj.setEnabled(False)

    def activate_target_object_in_widget(self, widget=None, target=None):
        for obj in widget.findChildren(target):
            obj.setEnabled(True)

    def deactivate_target_object_in_widget(self, widget=None, target=None):
        for obj in widget.findChildren(target):
            obj.setEnabled(False)

    def deactivate_selection(self):
        self.deactivate_objects_in_widget(widget=self.CONTROL_GROUP)
        self.activate_btn(self.BTN_STOP)
        self.activate_btn(self.BTN_EXIT)
        self.deactivate_objects_in_widget(widget=self.CAN_CONNECTION_GROUP)
        self.deactivate_objects_in_widget(widget=self.GROUP_APPMODE)
        self.deactivate_target_object_in_widget(widget=self.FIXED_FRAME_TAB_BACKGROUND_CFG, target=QRadioButton)
        if self.main.app_mode == APP_CPD:
            self.CMBB_IA_PLOT_SELECT.setEnabled(False)
            self.CMBB_DATC_PLOT_SELECT.setEnabled(False)
        elif self.main.app_mode == APP_IA:
            self.CMBB_CPD_PLOT_SELECT.setEnabled(False)
            self.CMBB_DATC_PLOT_SELECT.setEnabled(False)
        elif self.main.app_mode == APP_DATC:
            self.CMBB_CPD_PLOT_SELECT.setEnabled(False)
            self.CMBB_IA_PLOT_SELECT.setEnabled(False)
        else:
            pass

    def activate_selection(self):
        self.activate_objects_in_widget(widget=self.CONTROL_GROUP)
        self.activate_objects_in_widget(widget=self.CAN_CONNECTION_GROUP)
        self.activate_objects_in_widget(widget=self.GROUP_APPMODE)
        self.activate_target_object_in_widget(widget=self.FIXED_FRAME_TAB_BACKGROUND_CFG, target=QRadioButton)
        self.CMBB_CPD_PLOT_SELECT.setEnabled(True)
        self.CMBB_IA_PLOT_SELECT.setEnabled(True)
        self.CMBB_DATC_PLOT_SELECT.setEnabled(True)

    def func_start(self):
        print('\n--- START Clicked ---')

        ''' Start Time Display @ GUI '''
        self.start_time = datetime.datetime.now()               # current time
        self.LBL_START_TIME.setText(str(self.start_time)[:19])  # current time transfer to widget

        ''' Operation Status Update @ GUI '''
        self.LBL_STATUS.setText('STATUS : START')               # current status transfer to widget
        self.main.run()

        self.graph_update_thread = queue_recv(recv_queue=q_dict['graph_update'])
        self.graph_update_thread.emit_signal.connect(self.graph_update)
        self.graph_update_thread.start()

        ''' Button & Tab Act-Deactivate '''
        self.deactivate_selection()

    def func_stop(self):
        print('--- STOP Clicked ---')
        ''' Time Display Clearing @ GUI '''
        self.LBL_START_TIME.setText('')
        self.LBL_DURATION.setText('')

        ''' Operation Status Update @ GUI '''
        self.LBL_STATUS.setText('STATUS : STOP')

        ''' Stop Process '''
        self.main.stop()
        self.activate_selection()

        if self.dialog:
            self.dialog.play_flag = False
            self.dialog.close()

        if self.TOGGLE_SAVE.isChecked():
            self.TOGGLE_SAVE.toggle()
        self.func_save()
        self.plot_select()

        self.LBL_CPDINFO.setText('')
        self.LBL_CPDSTAT.setText('')
        palette = self.LBL_CPDRESULT.palette()
        palette.setColor(self.LBL_CPDRESULT.backgroundRole(), QColor(169, 169, 169))  # 배경 색상 지정
        self.LBL_CPDRESULT.setPalette(palette)
        self.LBL_CPDRESULT.setText('STOP')

    def func_exit(self):
        self.func_stop()
        q_dict['graph_update'].put(False)
        qApp.quit()

    def func_save(self):
        if self.TOGGLE_SAVE.isChecked():
            self.main.update_save_cfg(enable=True, name=self.LINE_SAVE_CASE.text(), save_cnt=self.SPINBOX_FRAME.value())
            self.LBL_SAVE_CASE_CHECK.setText(self.LINE_SAVE_CASE.text())
            self.LBL_FRAME_CHECK.setText(str(self.SPINBOX_FRAME.value()))
        else:
            self.main.update_save_cfg(enable=False, name='', save_cnt=self.SPINBOX_FRAME.value())
            self.LBL_SAVE_CASE_CHECK.setText('')
            self.LBL_FRAME_CHECK.setText(str(self.SPINBOX_FRAME.value()))

    def return_wig_type(self, wt, y_min=None, y_max=None):
        if wt == 'htm':
            plot = pg.PlotItem()  # axis label 추가
            plot.setLabel(axis='left', text='Y-axis')
            plot.setLabel(axis='bottom', text='X-axis')

            wig = pg.ImageView(view=plot)
            wig.view.setAspectLocked(False)  # 종횡비 유지 해제

            positions = [0.0, 0.25, 0.5, 0.75, 1.0]  # Color stops
            colors = [(68, 1, 84), (3, 136, 140), (127, 205, 187), (255, 255, 0),
                      (249, 251, 14)]  # Modified yellow color
            colormap = pg.ColorMap(pos=positions, color=colors)
            wig.setColorMap(colormap)
            return wig, wig

        elif wt == 'htm_inv':
            plot = pg.PlotItem()  # axis label 추가
            plot.setLabel(axis='left', text='Y-axis')
            plot.setLabel(axis='bottom', text='X-axis')

            wig = pg.ImageView(view=plot)
            wig.view.invertY(False)
            wig.view.setAspectLocked(False)  # 종횡비 유지 해제

            positions = [0.0, 0.25, 0.5, 0.75, 1.0]  # Color stops
            colors = [(68, 1, 84), (3, 136, 140), (127, 205, 187), (255, 255, 0),
                      (249, 251, 14)]  # Modified yellow color
            colormap = pg.ColorMap(pos=positions, color=colors)
            wig.setColorMap(colormap)

            return wig, wig

        elif wt == 'grp1':
            wig = pg.PlotWidget()
            wig.showGrid(x=True, y=True)
            plot = wig.plot(pen='g')
            if y_min is not None:
                wig.setYRange(min=y_min, max=y_max)  # 최소값 0, 최대값 10으로 설정
            return wig, plot

        elif wt == 'grp2':
            wig = pg.PlotWidget()
            wig.showGrid(x=True, y=True)
            plot1 = wig.plot(pen='r')
            plot2 = wig.plot(pen='g')
            return wig, [plot1, plot2]

        elif wt == 'gc1':
            wig = pg.PlotWidget()
            wig.showGrid(x=True, y=True)
            plot1 = wig.plot(pen='r')
            plot2 = wig.plot(pen='g')
            return wig, [plot1, plot2]

        elif wt == 'gc2':
            wig = pg.PlotWidget()
            wig.showGrid(x=True, y=True)
            plot = pg.PlotCurveItem()
            wig.addItem(plot)
            return wig, plot

    def plot_select(self):
        if self.main.app_mode == APP_CPD:
            current_txt = self.CMBB_CPD_PLOT_SELECT.currentText()
        elif self.main.app_mode == APP_IA:
            current_txt = self.CMBB_IA_PLOT_SELECT.currentText()
        elif self.main.app_mode == APP_DATC:
            current_txt = self.CMBB_DATC_PLOT_SELECT.currentText()
        else:
            raise ValueError('Not allowed app_mode')
        self.plot_option = current_txt
        self.clear_wig()

        if current_txt == 'CPD_RichUI':
            n_plot = 1
            n_col = 1
            n_row = n_plot // n_col

        elif current_txt == 'IA_RichUI':
            n_plot = 1
            n_col = 1
            n_row = n_plot // n_col

        elif current_txt in ['Range-Azimuth(Fast)', 'Range-Elevation(Fast)', 'Range-Azimuth(Slow)', 'Range-Elevation(Slow)']:
            n_plot = 2
            n_col = 2
            n_row = n_plot // n_col

        elif current_txt in ['Range-Doppler(Fast)', 'Range-EachRX(Fast)', 'Chirp-EachRX(Fast)', 'Range-Doppler(Slow)',
                             'Range-EachRX(Slow)', 'Chirp-EachRX(Slow)', 'Doppler-EachRX(Slow)',
                             'Chirp_Repres(1D)', 'Chirp_Repres(2D)', 'Doppler_Repres', 'Trajectory', 'Trajectory(DPL)',
                             'STFT_Heatmap', 'STFT_Track', 'STFT_Track_FFT',
                             'Range-Doppler', 'Range-EachRX', 'Azimuth-Elevation(Static)', 'Azimuth-Elevation(Dynamic)',
                             'Azimuth-Elevation(Fast)', 'Azimuth-Elevation(Slow)', 'RD_NCI']:
            n_plot = 6
            n_col = 3
            n_row = n_plot // n_col

        elif current_txt == 'G-Sensor':
            n_plot = 6
            n_col = 3
            n_row = n_plot // n_col

        elif current_txt == 'ETC':
            n_plot = 3
            n_col = 3
            n_row = n_plot // n_col

        else:
            n_plot = 1
            n_col = 1
            n_row = n_plot // n_col

        if self.plot_option == 'CPD_RichUI':
            self.VISUALIZER_QGRID.setRowStretch(0, 1)
            self.VISUALIZER_QGRID.setRowStretch(1, 1)
        elif self.plot_option == 'IA_RichUI':
            self.VISUALIZER_QGRID.setRowStretch(0, 1)
            self.VISUALIZER_QGRID.setRowStretch(1, 1)
        else:
            for row in range(n_row):
                self.VISUALIZER_QGRID.setRowStretch(row, n_plot//n_row)
            for col in range(n_col):
                self.VISUALIZER_QGRID.setColumnStretch(col, n_plot//n_col)

        if self.plot_option in ['Range-Azimuth(Fast)', 'Range-Elevation(Fast)',
                                'Range-Azimuth(Slow)', 'Range-Elevation(Slow)']:
            self.type_list = ['htm', 'htm']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['Range-Doppler(Fast)', 'Range-Doppler(Slow)', 'STFT_Heatmap', 'RD_NCI']:
            self.type_list = ['htm', 'htm', 'htm', 'htm', 'htm', 'htm']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['Azimuth-Elevation(Static)', 'Azimuth-Elevation(Dynamic)',
                                  'Azimuth-Elevation(Fast)', 'Azimuth-Elevation(Slow)']:
            self.type_list = ['htm_inv', 'htm_inv', 'htm_inv', 'htm_inv', 'htm_inv', 'htm_inv']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['Range-EachRX(Fast)', 'Doppler_Repres', 'STFT_Track',
                                  'STFT_Track_FFT', 'Doppler-EachRX(Slow)', 'Range-EachRX(Slow)', 'Trajectory', 'Trajectory(DPL)']:

            self.type_list = ['grp1', 'grp1', 'grp1', 'grp1', 'grp1', 'grp1']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['Chirp_Repres(1D)', 'Chirp-EachRX(Slow)','Chirp-EachRX(Fast)']:
            self.type_list = ['gc1', 'gc1', 'gc1', 'gc1', 'gc1', 'gc1']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['Chirp_Repres(2D)']:
            self.type_list = ['gc2', 'gc2', 'gc2', 'gc2', 'gc2', 'gc2']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        elif self.plot_option in ['G-Sensor']:
            self.type_list = ['grp1', 'grp1', 'grp1', 'grp1', 'grp1', 'grp1']
            for i in range(n_plot):
                wig, plot = self.return_wig_type(self.type_list[i])
                text_item = pg.TextItem(text='0',
                                        anchor=(0, 0),
                                        color=(255, 255, 255),
                                        fill=pg.mkBrush(0, 0, 0, 200),
                                        border=pg.mkPen((150, 150, 150),
                                                        width=0.5))
                text_item.setFont(pg.QtGui.QFont("Consolas", 12))
                text_item.setFlag(text_item.GraphicsItemFlag.ItemIgnoresTransformations)
                text_item.setParentItem(wig.plotItem)
                text_item.setPos(50, 10)
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append([plot, text_item])

        elif self.plot_option == 'CPD_RichUI':
            '''
                       --------------------------------
                       |                   |          |
                       |     Car Image     |  Percen  |
                       |                   |   tage   |
                       |------------------------------|
                       |        | chp1 | chp2 | chp3  |
                       |Progress|---------------------|
                       |   bar  | dpl1 | dpl2 | dpl3  |
                       --------------------------------

                       - Total Grid: self.CPD_QGRID
                       - Car Image + Percentage = QHBox
                       - Progress bar + chp + dpl = GraphicsLayoutWidget

                       '''

            hbox_top_left = QHBoxLayout()
            hbox_top_right = QHBoxLayout()
            hbox_bot_left = QHBoxLayout()
            grid_bot_right = QGridLayout()
            self.VISUALIZER_QGRID.addLayout(hbox_top_left, 0, 0)
            self.VISUALIZER_QGRID.addLayout(hbox_top_right, 0, 1)
            self.VISUALIZER_QGRID.addLayout(hbox_bot_left, 1, 0)
            self.VISUALIZER_QGRID.addLayout(grid_bot_right, 1, 1)
            self.VISUALIZER_QGRID.setColumnStretch(0, 3)
            self.VISUALIZER_QGRID.setColumnStretch(1, 1)

            grp_widget = pg.GraphicsLayoutWidget()
            hbox_bot_left.addWidget(grp_widget)
            self.qlabel_list = [QLabel(), QLabel(), QLabel(), QLabel()]  # [AppMode, Timer, ResultBox, Frames]
            for idx, qlabel in enumerate(self.qlabel_list):
                if idx < len(self.qlabel_list) -1:
                    qlabel.setFont(QFont("Consolas", 16))
                else:
                    qlabel.setFont(QFont("Consolas", 10))
                qlabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
                qlabel.setStyleSheet("border: 1px solid black;")
                qlabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)  # 크기 변화 방지

            grid_bot_right.addWidget(self.qlabel_list[0], 0, 0)
            grid_bot_right.addWidget(self.qlabel_list[1], 0, 1)
            grid_bot_right.addWidget(self.qlabel_list[2], 1, 0)
            grid_bot_right.addWidget(self.qlabel_list[3], 1, 1)

            ########################################
            car_img_wig = pg.PlotWidget()
            car_img_wig.setXRange(variables['CPD_TOP_VIEW'][0], variables['CPD_TOP_VIEW'][1])
            car_img_wig.setYRange(variables['CPD_TOP_VIEW'][2], variables['CPD_TOP_VIEW'][3])
            car_img_wig.showGrid(x=True, y=True)
            car_img_wig.invertY(True)

            pixmap = QPixmap('./SRC_Qt5/CAR_IMG/car_top_view.png')  # Car image loading
            pixmap_item = QGraphicsPixmapItem(pixmap)

            (w, h) = (pixmap.width(), pixmap.height())
            (scale_w, scale_h) = (variables['TOP_VIEW_SCALE'][0], variables['TOP_VIEW_SCALE'][1])

            transform = QTransform()                                # Car image sacle/position setting
            transform.scale(scale_w, scale_h)
            pixmap_item.setTransform(transform)
            pixmap_item.setPos(-(scale_w * w / 2 + variables['TOP_VIEW_OFFSET'][0]), -(scale_h * h / 2 + variables['TOP_VIEW_OFFSET'][1]))
            pixmap_item.setOpacity(variables['CAR_TRANSPARENCY'])
            car_img_wig.addItem(pixmap_item)                        # Car image applying

            radar_box = pg.ScatterPlotItem(x=[0], y=[0], size=20, symbol='s', brush='r')    # radar position visualizing
            car_img_wig.addItem(radar_box)

            scatter_item = pg.ScatterPlotItem(symbol='star')
            car_img_wig.addItem(scatter_item)

            hbox_top_left.addWidget(car_img_wig)
            self.plot_obj_list.append([scatter_item])

            ############################################
            labels = ['C', 'A', 'B', 'E', 'U', 'R']
            ticks = [(i + 1, labels[i]) for i in range(len(labels))]

            # 커스텀 x축 생성
            x_axis = pg.AxisItem(orientation='bottom')
            x_axis.setTicks([ticks])

            # PlotWidget 생성 (커스텀 x축 사용)
            percent_wig = pg.PlotWidget(axisItems={'bottom': x_axis})
            percent_wig.setTitle('Percentage', color="w", size="12pt")
            percent_wig.showGrid(x=False, y=True)
            percent_wig.setYRange(0, 100)

            transparent_brushes = [
                QColor(255, 255, 255, 180),
                QColor(0, 0, 255, 180),
                QColor(0, 255, 0, 100),
                QColor(128, 128, 128, 180),
                QColor(128, 128, 128, 180),
                QColor(255, 165, 0, 180)]
            bar_item_transparent = pg.BarGraphItem(x=[1, 2, 3, 4, 5, 6], height=[0, 0, 0, 0, 0, 0], width=0.2, brushes=transparent_brushes)
            percent_wig.addItem(bar_item_transparent)
            bar_item_bold = pg.BarGraphItem(x=[1.4, 2.4, 3.4, 4.4, 5.4, 6.4], height=[0, 0, 0, 0, 0, 0], width=0.4, brushes=['w', 'b', 'g', 'gray', 'gray', 'orange'])
            percent_wig.addItem(bar_item_bold)

            hbox_top_right.addWidget(percent_wig)
            self.plot_obj_list.append([bar_item_transparent, bar_item_bold])

            plot_list = []
            for i in range(6):
                plot = grp_widget.addPlot(row=i // 3, col=(i % 3) + 2)
                plot.showGrid(x=True, y=True)
                if i < 3:
                    plot.setTitle(f'Time Signal {i % 3}', color="w", size="12pt")
                else:
                    plot.setTitle(f'Frequency Signal {i % 3}', color="w", size="12pt")
                plot1 = plot.plot(pen=pg.mkPen(color='g', width=2))
                plot2 = plot.plot(pen=pg.mkPen(color='r', width=2))
                plot_list.append([plot1, plot2])
            self.plot_obj_list.append(plot_list)

        elif self.plot_option == 'IA_RichUI':
            '''
            ----------------------
            |                    |
            |     Car Image      |
            |     Top View       |
            ----------------------
            |                    |
            |    History Graph   |
            |                    |
            ----------------------
            '''
            hbox_top_left = QHBoxLayout()
            hbox_top_right = QHBoxLayout()
            hbox_bot_left = QHBoxLayout()
            grid_bot_right = QGridLayout()
            self.VISUALIZER_QGRID.addLayout(hbox_top_left, 0, 0)
            self.VISUALIZER_QGRID.addLayout(hbox_top_right, 0, 1)
            self.VISUALIZER_QGRID.addLayout(hbox_bot_left, 1, 0)
            self.VISUALIZER_QGRID.addLayout(grid_bot_right, 1, 1)
            self.VISUALIZER_QGRID.setColumnStretch(0, 3)
            self.VISUALIZER_QGRID.setColumnStretch(1, 1)

            self.qlabel_list = [QLabel(), QLabel(), QLabel(), QLabel()]  # [AppMode, Timer, ResultBox, Frames]
            for idx, qlabel in enumerate(self.qlabel_list):
                if idx < len(self.qlabel_list)-1:
                    qlabel.setFont(QFont("Consolas", 16))
                else:
                    qlabel.setFont(QFont("Consolas", 10))
                qlabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
                qlabel.setStyleSheet("border: 1px solid black;")
                qlabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)  # 크기 변화 방지

            grid_bot_right.addWidget(self.qlabel_list[0], 0, 0)
            grid_bot_right.addWidget(self.qlabel_list[1], 0, 1)
            grid_bot_right.addWidget(self.qlabel_list[2], 1, 0)
            grid_bot_right.addWidget(self.qlabel_list[3], 1, 1)

            ################################################################################

            car_img_wig = pg.PlotWidget()
            car_img_wig.setXRange(variables['CPD_TOP_VIEW_IA'][0], variables['CPD_TOP_VIEW_IA'][1])
            car_img_wig.setYRange(variables['CPD_TOP_VIEW_IA'][2], variables['CPD_TOP_VIEW_IA'][3])
            car_img_wig.showGrid(x=True, y=True)
            car_img_wig.invertY(True)
            
            # y-axis
            top_limit = variables['IA_VALID_AREA']['Y'][0]
            bottom_limit = variables['IA_VALID_AREA']['Y'][1]
            # x-axis
            left_limit = variables['IA_VALID_AREA']['Z'][0]
            right_limit = variables['IA_VALID_AREA']['Z'][1]

            rect_x = [left_limit, right_limit, right_limit, left_limit, left_limit]
            rect_y = [top_limit, top_limit, bottom_limit, bottom_limit, top_limit]
            car_img_wig.plot(rect_x, rect_y, pen=pg.mkPen('r', width=2))

            pixmap_top = QPixmap('./SRC_Qt5/CAR_IMG/car_top_view.png')  # Car image loading
            pixmap_item = QGraphicsPixmapItem(pixmap_top)

            (w, h) = (pixmap_top.width(), pixmap_top.height())
            (scale_w, scale_h) = (variables['TOP_VIEW_SCALE_IA'][0], variables['TOP_VIEW_SCALE_IA'][1])

            transform = QTransform()  # Car image sacle/position setting
            transform.scale(scale_w, scale_h)
            pixmap_item.setTransform(transform)
            pixmap_item.setPos(-(scale_w * w / 2 + variables['TOP_VIEW_OFFSET_IA'][0]), -(scale_h * h / 2 + variables['TOP_VIEW_OFFSET_IA'][1]))
            pixmap_item.setOpacity(variables['CAR_TRANSPARENCY'])
            car_img_wig.addItem(pixmap_item)  # Car image applying

            radar_box = pg.ScatterPlotItem(x=[0], y=[0], size=20, symbol='s', brush='r')  # radar position visualizing
            car_img_wig.addItem(radar_box)

            scatter_item = pg.ScatterPlotItem(symbol='o')
            car_img_wig.addItem(scatter_item)

            cluster_scatter_item = pg.ScatterPlotItem(symbol='o')
            car_img_wig.addItem(cluster_scatter_item)

            hbox_top_left.addWidget(car_img_wig)
            self.plot_obj_list.append([scatter_item, cluster_scatter_item])

            #########################################################################
            # Car Side View
            car_img_wig = pg.PlotWidget()
            car_img_wig.setXRange(variables['CPD_SIDE_VIEW_IA'][0], variables['CPD_SIDE_VIEW_IA'][1])
            car_img_wig.setYRange(variables['CPD_SIDE_VIEW_IA'][2], variables['CPD_SIDE_VIEW_IA'][3])
            car_img_wig.showGrid(x=True, y=True)
            car_img_wig.invertY(True)

            pixmap_top = QPixmap('./SRC_Qt5/CAR_IMG/car_side_view.png')  # Car image loading
            pixmap_item = QGraphicsPixmapItem(pixmap_top)

            (w, h) = (pixmap_top.width(), pixmap_top.height())
            (scale_w, scale_h) = (variables['SIDE_VIEW_SCALE_IA'][0], variables['SIDE_VIEW_SCALE_IA'][1])

            transform = QTransform()  # Car image sacle/position setting
            transform.scale(scale_w, scale_h)
            pixmap_item.setTransform(transform)
            pixmap_item.setPos(-(scale_w * w / 2 + variables['SIDE_VIEW_OFFSET_IA'][0]), -(scale_h * h / 2 + variables['SIDE_VIEW_OFFSET_IA'][1]))
            pixmap_item.setOpacity(variables['CAR_TRANSPARENCY'])
            car_img_wig.addItem(pixmap_item)  # Car image applying

            radar_box = pg.ScatterPlotItem(x=[0], y=[0], size=20, symbol='s', brush='r')  # radar position visualizing
            car_img_wig.addItem(radar_box)

            scatter_item = pg.ScatterPlotItem(symbol='o')
            car_img_wig.addItem(scatter_item)

            cluster_scatter_item = pg.ScatterPlotItem(symbol='o')
            car_img_wig.addItem(cluster_scatter_item)

            hbox_bot_left.addWidget(car_img_wig)
            self.plot_obj_list.append([scatter_item, cluster_scatter_item])

            ################################################################################
            # Result History - Graph
            result_history = pg.PlotWidget()
            result_history.showGrid(x=True, y=True)
            result_history.setTitle('Result History', color="w", size="12pt")
            plot = result_history.plot(pen=pg.mkPen(color='r', width=5))
            result_history.invertX(True)
            result_history.setXRange(1, 160)
            result_history.setYRange(0, 2)
            self.VISUALIZER_QGRID.addWidget(result_history, 0, 1)
            self.plot_obj_list.append(plot)
            ################################################################################

        elif self.plot_option in ['ETC']:
            self.type_list = ['grp1', 'grp1', 'grp1']
            for i in range(n_plot):
                if i == n_plot -1:
                    wig, plot = self.return_wig_type(self.type_list[i], y_min=0, y_max=200)
                else:
                    wig, plot = self.return_wig_type(self.type_list[i])
                self.VISUALIZER_QGRID.addWidget(wig, i // n_col, i % n_col)
                self.plot_obj_list.append(plot)

        else:
            print('Not allowed widget type')

        self.graph_update()

    def clear_wig(self):
        self.plot_obj_list.clear()
        self.text_list.clear()
        self.type_list.clear()

        while self.VISUALIZER_QGRID.count():
            item = self.VISUALIZER_QGRID.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()    # 이번 이벤트 루프 후 위젯 삭제
            else:
                self.clearLayoutRecursively(item.layout())

        # 스트레치 초기화
        for row in range(self.VISUALIZER_QGRID.rowCount()):
            self.VISUALIZER_QGRID.setRowStretch(row, 0)
        for col in range(self.VISUALIZER_QGRID.columnCount()):
            self.VISUALIZER_QGRID.setColumnStretch(col, 0)

    def clearLayoutRecursively(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self.clearLayoutRecursively(item.layout())

    def graph_update(self):
        if self.main.start_flag:
            graph_data, pen_color, text, pos_conf, position = self.main.get_graph_data(self.plot_option)
            if self.main.app_mode in [APP_CPD, APP_DATC]:
                info, rock_th, feat, stat, mara, init_warn = self.main.get_info()
                self.update_cpd_info(info, feat, rock_th, mara)
                self.update_cpd_datc_result(stat, init_warn)

            if self.plot_option == 'CPD_RichUI':
                if (self.CHK_INIT_WARN.isChecked() and init_warn[0] == CLS_COLLECT) or not self.CHK_INIT_WARN.isChecked():
                    self.plot_obj_list[0][0].setData(x=graph_data[0][0], y=graph_data[0][1], size=graph_data[0][2])
                    self.plot_obj_list[0][0].setBrush(QBrush(QColor(*graph_data[0][3])))

                    self.plot_obj_list[1][0].setOpts(height=graph_data[1][0])  # 각 클래스 별 result history
                    self.plot_obj_list[1][1].setOpts(height=graph_data[1][1])  # 각 클래스 별 count

                    for i in range(6):
                        self.plot_obj_list[2][i][0].setData(graph_data[2][i].real)
                        if i >= 3:
                            color = (0, 255, 0)
                            self.plot_obj_list[2][i][0].setPen(color=color, width=2)
                            self.plot_obj_list[2][i][1].setPen(color=(0, 0, 0, 0), width=2)
                        else:
                            self.plot_obj_list[2][i][1].setPen(color=(255, 0, 0, 255), width=2)
                        self.plot_obj_list[2][i][1].setData(graph_data[2][i].imag)

                    if self.main.app_mode == APP_CPD:
                        self.qlabel_list[0].setText('[App_Mode]\n\n\nCPD')
                    elif self.main.app_mode == APP_IA:
                        self.qlabel_list[0].setText('[App_Mode]\n\n\nIA')
                    elif self.main.app_mode == APP_DATC:
                        self.qlabel_list[0].setText('[App_Mode]\n\n\nDATC')
                    else:
                        self.qlabel_list[0].setText('')

                    current_time = datetime.datetime.now()
                    duration_seconds = int((current_time - self.start_time).total_seconds())
                    self.qlabel_list[1].setText(f'┌  TEST  ┐\n└Duration┘\n\n{duration_seconds} sec.')

                else:
                    pass

            elif self.plot_option == 'IA_RichUI':
                stat = self.main.get_ia_info()
                self.update_ia_result(stat)
                # Top View - XYZ
                self.plot_obj_list[0][0].setData(x=graph_data[0][0], y=graph_data[0][1], size=10)
                self.plot_obj_list[0][0].setBrush(QBrush(QColor(*graph_data[0][2])))
                # Top View - Cluster
                self.plot_obj_list[0][1].setData(x=graph_data[0][3], y=graph_data[0][4], size=10)
                self.plot_obj_list[0][1].setBrush(QBrush(QColor(*graph_data[0][5])))
                # Side View - XYZ
                self.plot_obj_list[1][0].setData(x=graph_data[1][0], y=graph_data[1][1], size=10)
                self.plot_obj_list[1][0].setBrush(QBrush(QColor(*graph_data[1][2])))
                # Side View - Cluster
                self.plot_obj_list[1][1].setData(x=graph_data[1][3], y=graph_data[1][4], size=10)
                self.plot_obj_list[1][1].setBrush(QBrush(QColor(*graph_data[1][5])))
                # Graph
                self.plot_obj_list[2].setData(graph_data[2], pen=pg.mkPen(color='r', width=5))

                if self.main.app_mode == APP_CPD:
                    self.qlabel_list[0].setText('[App_Mode]\n\n\nCPD')
                elif self.main.app_mode == APP_IA:
                    self.qlabel_list[0].setText('[App_Mode]\n\n\nIA')
                elif self.main.app_mode == APP_DATC:
                    self.qlabel_list[0].setText('[App_Mode]\n\n\nDATC')
                else:
                    self.qlabel_list[0].setText('')

                current_time = datetime.datetime.now()
                duration_seconds = int((current_time - self.start_time).total_seconds())
                self.qlabel_list[1].setText(f'┌  TEST  ┐\n└Duration┘\n\n{duration_seconds} sec.')

            else:
                for i in range(len(self.type_list)):  # [grp, gc1, gc2, htm]
                    if self.type_list[i] == 'grp1':
                        if self.plot_option == 'G-Sensor':
                            self.plot_obj_list[i][0].setData(graph_data[i][0], pen='g')
                            self.plot_obj_list[i][1].setText(str(graph_data[i][1]))
                        else:
                            self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp1_feat1':
                        self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp1_feat3':
                        self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp1_az':
                        self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp1_shk':
                        self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp1_xlen':
                        self.plot_obj_list[i].setData(graph_data[i], pen='g')
                    elif self.type_list[i] == 'grp2':
                        self.plot_obj_list[i][0].setData(graph_data[i][0], pen='g')
                        self.plot_obj_list[i][1].setData(graph_data[i][1], pen='r')
                    elif self.type_list[i] == 'gc1':
                        self.plot_obj_list[i][0].setData(graph_data[i].real, pen='g')
                        self.plot_obj_list[i][1].setData(graph_data[i].imag, pen='r')
                    elif self.type_list[i] == 'gc2':
                        self.plot_obj_list[i].setData(x=graph_data[i].real, y=graph_data[i].imag, pen='g')
                    elif self.type_list[i] == 'htm':
                        self.plot_obj_list[i].setImage(graph_data[i])

            current_time = datetime.datetime.now()
            duration_seconds = int((current_time - self.start_time).total_seconds())
            self.LBL_DURATION.setText(str(duration_seconds))

    def update_cpd_info(self, info, feat, rock_th, mara):
        info_text = f"&nbsp;&nbsp;&nbsp;&nbsp;RG AZ EL &nbsp;&nbsp;X &nbsp;&nbsp;Y &nbsp;&nbsp;Z"
        except_list = ['POW', 'SINR', 'CLASS', 'CLASS2']

        if self.CHK_FEAT.isChecked():
            info_text += f"&nbsp;C3 ROCK &nbsp;&nbsp;MAG &nbsp;&nbsp;RAD &nbsp;&nbsp;RATIO <br>"
        else:
            info_text += f"&nbsp;C3 ROCK F1 F2L F2R &nbsp;F3 &nbsp;F4 F5<br>"
        info_field_names = info.dtype.names
        feat_field_names = feat.dtype.names
        mara_field_names = mara.dtype.names

        for i in range(len(info)):
            if feat[i][STR_ROCKING] >= rock_th:
                info_text += f"<span style='color: red;'>"
            else:
                info_text += f"<span style='color: black;'>"

            if i < 10:
                info_text += f"&nbsp;"

            info_text += f"{i}|"

            for field_name in info_field_names:
                if field_name in except_list:
                    continue

                num_digits = len(str(info[i][field_name]))
                if field_name in ['POW', 'X', 'Y', 'Z']:
                    bsp = 4 - num_digits
                else:
                    bsp = 3 - num_digits

                for _ in range(bsp):
                    info_text += f"&nbsp;"
                info_text += f"{info[i][field_name]}"

            if self.CHK_FEAT.isChecked():
                num_digits = len(str(feat[i][STR_ROCKING]))
                bsp = 4 - num_digits
                for _ in range(bsp):
                    info_text += f"&nbsp;"
                info_text += f"{feat[i][STR_ROCKING]}"

                for field_name in mara_field_names:
                    num_digits = len(f"{mara[i][field_name]:.1f}")
                    bsp = 7 - num_digits
                    for _ in range(bsp):
                        info_text += f"&nbsp;"
                    info_text += f"{mara[i][field_name]:.1f}"
            else:
                for field_name in feat_field_names:
                    num_digits = len(str(feat[i][field_name]))
                    bsp = 4 - num_digits
                    for _ in range(bsp):
                        info_text += f"&nbsp;"
                    info_text += f"{feat[i][field_name]}"

            info_text += f"</span><br>"

        self.LBL_CPDINFO.setText(info_text)

    def update_cpd_datc_result(self, stat, init_warn):
        stat_text = f"<Statistics>\n"
        stat_field_names = stat.dtype.names

        for field in stat_field_names:
            if field in ['Frame', 'Result', STR_COLLECT, 'Location']:
                continue
            stat_text += f"{field:<8}:{stat[field]:>4}/{stat['Frame']:<5}\n"
        stat_text += "\nFrame Rate: 16 fps\n(1frame = 64 ms)"
        self.LBL_CPDSTAT.setText(stat_text)
        self.qlabel_list[3].setText(stat_text)

        if self.CHK_INIT_WARN.isChecked():
            cpd_result = init_warn[0]
        else:
            cpd_result = stat['Result']

        if self.main.app_mode == APP_CPD:
            if cpd_result == CLS_NONE:
                color_style = 'gray'
                text = STR_NONE
            elif cpd_result == CLS_MOTION:
                color_style = 'lightblue'
                text = STR_MOTION
            elif cpd_result == CLS_VITAL:
                color_style = 'lightgreen'
                text = STR_VITAL
            elif cpd_result == CLS_COLLECT:
                color_style = 'gray'
                text = 'Data\nCollecting'
            else:
                color_style = 'gray'
                text = STR_UNKNOWN
        else:   # APP_DATC
            if cpd_result == CLS_MOTION:
                color_style = 'lightblue'
                text = 'A/C Remain'
            elif cpd_result == CLS_COLLECT:
                color_style = 'gray'
                text = 'Data\nCollecting'
            else:
                color_style = 'lightcoral'
                text = 'A/C OFF'

        if self.CHK_INIT_WARN.isChecked() and self.main.app_mode == APP_CPD:
            if init_warn[1] == 0:
                pass
            elif init_warn[1] == 1:
                text += '\non 2nd row'
            elif init_warn[1] == 2:
                text += '\non 3rd row'
            else:
                pass
            text += '\n(INIT_WARN)'

        self.LBL_CPDRESULT.setStyleSheet(f"background-color: {color_style};")
        self.LBL_CPDRESULT.setText(text)

        self.qlabel_list[2].setStyleSheet(f"border: 1px solid black; background-color: {color_style};")
        self.qlabel_list[2].setText(f'[Result]\n\n{text}')

    def update_ia_result(self, stat):
        stat_text = f"<Statistics>\n"
        stat_field_names = stat.dtype.names
        
        for field in stat_field_names:
            if field in ['Frame', 'Result']:
                continue
            stat_text += f"{field:<8}:{stat[field]:>4} / {stat['Frame']+1:<4}\n"
        stat_text += "\nFrame Rate: 16 fps\n(1frame = 64 ms)"
        self.LBL_CPDSTAT.setText(stat_text)
        self.qlabel_list[3].setText(stat_text)

        ia_result = stat['Result']
        if ia_result == CLS_INTRUDER:
            color_style = 'lightcoral'
            text = 'Intruder'
        elif ia_result == CLS_NONE:
            color_style = 'gray'
            text = 'None'
        else:
            color_style = 'gray'
            text = 'None'

        self.LBL_CPDRESULT.setStyleSheet(f"border: 1px solid black; background-color: {color_style};")
        self.LBL_CPDRESULT.setText(text)

        self.qlabel_list[2].setStyleSheet(f"border: 1px solid black; background-color: {color_style};")
        self.qlabel_list[2].setText(f'[Result]\n\n{text}')

    def cfg_value_to_main(self, push_button=None):
        group = push_button.parent()
        ret_dict = {}
        ret_dict['command'] = group.title()
        for obj in group.findChildren((QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QCheckBox)):
            obj_type = type(obj)
            param = obj.objectName().split('_')[1]

            if obj_type in [QSpinBox, QDoubleSpinBox]:
                ret_dict['{}'.format(param)] = obj.value()

            elif obj_type == QComboBox:
                if param[:-1] == 'DigOutputSampRate':
                    if obj.currentText() == '12.5':
                        ret_dict['{}'.format(param)] = 8
                    elif obj.currentText() == '11.11':
                        ret_dict['{}'.format(param)] = 9
                    elif obj.currentText() == '10':
                        ret_dict['{}'.format(param)] = 10
                    elif obj.currentText() == '8.33':
                        ret_dict['{}'.format(param)] = 12
                    elif obj.currentText() == '6.25':
                        ret_dict['{}'.format(param)] = 16
                    elif obj.currentText() == '5':
                        ret_dict['{}'.format(param)] = 20
                    elif obj.currentText() == '4':
                        ret_dict['{}'.format(param)] = 25
                    elif obj.currentText() == '3.125':
                        ret_dict['{}'.format(param)] = 32
                    elif obj.currentText() == '2.5':
                        ret_dict['{}'.format(param)] = 40
                    elif obj.currentText() == '2':
                        ret_dict['{}'.format(param)] = 50
                    elif obj.currentText() == '1.5625':
                        ret_dict['{}'.format(param)] = 64
                    elif obj.currentText() == '1.25':
                        ret_dict['{}'.format(param)] = 80
                    elif obj.currentText() == '1':
                        ret_dict['{}'.format(param)] = 100

                elif param[:-1] == 'ChirpTxMimoPatSel':
                    if obj.currentIndex() == 0:
                        ret_dict['{}'.format(param)] = 0
                    elif obj.currentIndex() == 1:
                        ret_dict['{}'.format(param)] = 1
                    elif obj.currentIndex() == 2:
                        ret_dict['{}'.format(param)] = 4
                else:
                    ret_dict['{}'.format(param)] = obj.currentIndex()

            elif obj_type in [QRadioButton, QCheckBox]:
                if obj.isChecked():
                    ret_dict['{}'.format(param)] = True
                else:
                    ret_dict['{}'.format(param)] = False

            else:
                print('Not allowed QObject type')

        self.main.apply_cfg_via_pcan(ret_dict)

    def load_cfg_file(self):
        fname = QFileDialog.getOpenFileNames(self)
        with open(fname[0][0]) as file:
            unified_cfg_dict = json.load(file)

        for group in self.FIXED_FRAME_TAB_BACKGROUND_CFG.findChildren(QGroupBox):
            command = group.title()
            for obj in group.findChildren((QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QCheckBox)):
                obj_type = type(obj)
                param = obj.objectName().split('_')[1][:-1]
                if obj_type in [QSpinBox, QDoubleSpinBox]:
                    obj.setValue(unified_cfg_dict[command][param])

                elif obj_type == QComboBox:
                    obj.setCurrentIndex(unified_cfg_dict[command][param])

                elif obj_type in [QRadioButton, QCheckBox]:
                    obj.setChecked(unified_cfg_dict[command][param])

    def save_cfg_file(self):
        unified_cfg_dict = {}
        for group in self.FIXED_FRAME_TAB_BACKGROUND_CFG.findChildren(QGroupBox):
            unit_cfg_dict = {}
            for obj in group.findChildren((QSpinBox, QDoubleSpinBox, QComboBox, QRadioButton, QCheckBox)):
                obj_type = type(obj)
                param = obj.objectName().split('_')[1][:-1]
                if obj_type in [QSpinBox, QDoubleSpinBox]:
                    unit_cfg_dict['{}'.format(param)] = obj.value()

                elif obj_type == QComboBox:
                    unit_cfg_dict['{}'.format(param)] = obj.currentIndex()

                elif obj_type in [QRadioButton, QCheckBox]:
                    if obj.isChecked():
                        unit_cfg_dict['{}'.format(param)] = True
                    else:
                        unit_cfg_dict['{}'.format(param)] = False

            unified_cfg_dict[group.title()] = unit_cfg_dict

        fpath = QFileDialog.getSaveFileName(self)
        fpath_json = fpath[0] + '.json'

        with open(fpath_json, 'w') as outfile:
            json.dump(unified_cfg_dict, outfile, indent=4)
        print('Current Radar Config is saved at {}'.format(fpath_json))

    def update_sel_dict(self, dict_in:dict):
        if self.main.start_flag:
            for key, val in dict_in.items():
                self.main.sel_dict[key] = val
            q_dict['graph_update'].put(True)
        else:
            pass

    def open_dialog(self, btn):
        if self.main.start_flag:
            if not self.dialog:
                if btn.objectName() == 'BTN_PLOTSETTING':
                    self.dialog = Dialog()
                    self.dialog.update_diag(dict_in=self.main.get_min_max_sel_dict())
                self.dialog.closed.connect(self.set_dialog_none)
                self.dialog.show()
            else:
                visible = self.dialog.isVisible()
                if visible:
                    print('[Message] Dialog is already opened')
                else:
                    self.dialog.close()
                    self.dialog = None
        else:
            pass

    def set_dialog_none(self):
        self.dialog = None

    def get_path_for_data_load(self):
        file = str(QFileDialog.getExistingDirectory(self))
        data_name = file.split('/')[-1]
        print('loade data name:', data_name)
        self.main.path_data_load = file
        self.LBL_LOAD_PATH.setToolTip(data_name)
        self.LBL_LOAD_PATH.setText('{}'.format(data_name))

    def closeEvent(self, event):
        if self.dialog is not None and self.dialog.isVisible():
            self.dialog.close()
        event.accept()


class Dialog(QDialog, DialogClass):
    closed = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.init_slider()

        self.play_flag = False
        self.BTN_FRMRUN.clicked.connect(self.auto_play)
        self.BTN_FRMSTOP.clicked.connect(self.stop_play)

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()

    def init_slider(self):
        for slider in self.findChildren(QSlider):
            slider.valueChanged.connect(partial(self.value_to_mainwindow))

    def update_diag(self, dict_in:dict):
        for slider in self.findChildren(QSlider):
            objname = slider.objectName().split('_')[-1]
            item = objname.split('IDX')[0]

            min_val = dict_in[item + 'MIN']
            max_val = dict_in[item + 'MAX'] - 1

            slider.setMinimum(min_val)
            slider.setMaximum(max_val)

            lbl_min = 'LBL_' + item + 'MIN'
            lbl_max = 'LBL_' + item + 'MAX'
            lbl_min_obj = self.findChild(QLabel, lbl_min)
            lbl_max_obj = self.findChild(QLabel, lbl_max)
            lbl_min_obj.setText('{}'.format(min_val))
            lbl_max_obj.setText('{}'.format(max_val))

        for cmbb in self.findChildren(QComboBox):
            item = cmbb.objectName().split('_')[-1]

            add_list = dict_in[item + 'LIST']
            for val in add_list:
                cmbb.addItem('{}'.format(val))
            cmbb.setCurrentIndex(0)

    def value_to_mainwindow(self):
        dial_dict = {}
        for slider in self.findChildren(QSlider):
            key = slider.objectName().split('_')[-1]
            val = slider.value()
            dial_dict[key] = val

        mainwindow.update_sel_dict(dict_in=dial_dict)

    def auto_play(self):
        self.play_flag = True
        current_idx = self.QSLIDE_FRMIDX.value()
        max_idx = self.QSLIDE_FRMIDX.maximum()

        for idx in range(current_idx, max_idx + 1):
            if self.play_flag:
                self.QSLIDE_FRMIDX.setValue(idx)
                self.value_to_mainwindow()
                QTest.qWait(100)
            else:
                break
        print('[Message] auto playing is finished')

    def stop_play(self):
        self.play_flag = False


class queue_recv(QThread):
    emit_signal = pyqtSignal(object)

    def __init__(self, recv_queue):
        super().__init__()
        self.recv_queue = recv_queue

    def run(self):
        print('[Message] queue_recv started')
        while True:
            data = self.recv_queue.get()
            if data:
                self.emit_signal.emit(data)
            else:
                break
        print('[Message] queue_recv terminated')


if __name__ == '__main__':
    if platform.system() == 'Windows' and int(platform.release()) >= 8:
        ctypes.windll.shcore.SetProcessDpiAwareness(True)

    ''' GUI Execution '''
    app = QApplication(sys.argv)                        # QApplication 객체 생성
    mainwindow = GuiMain()                             # 각종 위젯 생성 및 초기화
    mainwindow.show()                                  # GUI를 화면에 출력
    sys.exit(app.exec_())                               # 이벤트 루프 실행

