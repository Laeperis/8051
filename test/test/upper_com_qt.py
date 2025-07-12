import sys
import serial
import serial.tools.list_ports
import re
import requests
import json
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QTextEdit, QMessageBox, QLineEdit, QFormLayout, QSlider
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QBrush, QPixmap, QPainter, QColor, QImage
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu
import PyQt5.QtCore as QtCore
import pyqtgraph as pg  
from PyQt5.QtWidgets import QDial



class SerialThread(QThread):
    data_received = pyqtSignal(str)

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self.running = True

    def run(self):
        while self.running:
            if self.ser.is_open:
                try:
                    line = self.ser.readline().decode(errors='ignore').strip()
                    if line:
                        self.data_received.emit(line)
                except Exception:
                    pass

    def stop(self):
        self.running = False
        self.quit()
        self.wait()
class NetworkThread(QThread):
    """
    网络线程，负责发送网络数据
    """
    send_log = pyqtSignal(str)#用于向UI发送日志
    def __init__(self,url):
        super().__init__()
        self.url = url
        self.running = True
        self.data_to_send = None #存储待发送的数据
        
    def run(self):
        while self.running:
            if self.data_to_send:
                try:
                    # 使用HTTP POST请求发送数据
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(self.url, data=self.data_to_send, headers=headers, timeout=5)
                    
                    if response.status_code == 200:
                        self.send_log.emit(f"✅ 已发送到服务器: {self.data_to_send}")
                    else:
                        self.send_log.emit(f"⚠️ 服务器响应异常: {response.status_code}")
                    
                    self.data_to_send = None # 发送成功后清空
                except requests.exceptions.ConnectionError:
                    self.send_log.emit(f"❌ 连接服务器失败: {self.url}")
                except requests.exceptions.Timeout:
                    self.send_log.emit(f"❌ 请求超时: {self.url}")
                except Exception as e:
                    self.send_log.emit(f"❌ 发送到服务器失败: {e}")
            self.msleep(1000) # 每秒尝试发送一次，避免频繁连接

    def send_data(self, data):
        """
        设置要发送的数据。
        """
        self.data_to_send = data

    def stop(self):
        self.running = False
        self.quit()
        self.wait()
            

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 先定义 set_label_shadow，确保后续所有 label 创建前可用
        def set_label_shadow(label):
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(0)
            effect.setColor(QColor(0,0,0))
            effect.setOffset(1, 1)
            label.setGraphicsEffect(effect)
            label.setStyleSheet("color: white; font-weight: bold; font-size: 20px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;")
        self.setWindowTitle("温湿度/频率监控上位机")
        self.ser = None
        self.serial_thread = None
        self.network_thread = None #新增网络线程
        self.current_channel = 1 # 0=温湿度, 1=频率

        # 网络配置 - 固定服务器地址
        self.server_url = "http://data.cancanjiao.xyz/data"  # 固定服务器URL
        # 报警状态标志
        self.temp_alarm_on = False
        self.humi_alarm_on = False
        self.freq_alarm_on = False

        # 固定窗口初始大小和比例
        self.setFixedSize(960, 540)

        # 通道选择
        self.channel_label = QLabel("采集通道:")
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["温湿度", "频率"])
        self.channel_combo.setCurrentIndex(0)  # 默认选择温湿度
        self.channel_combo.currentIndexChanged.connect(self.change_channel)

        # 串口选择
        self.port_label = QLabel("串口号:")
        self.port_combo = QComboBox()
        self.refresh_ports()
        # 默认选择COM2（如果存在）
        idx = self.port_combo.findText("COM2")
        if idx != -1:
            self.port_combo.setCurrentIndex(idx)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_ports)

        # 打开/关闭串口
        self.open_btn = QPushButton("打开串口")
        self.open_btn.clicked.connect(self.open_serial)
        self.close_btn = QPushButton("关闭串口")
        self.close_btn.clicked.connect(self.close_serial)
        self.close_btn.setEnabled(False)
        self.channel_combo.setEnabled(True) # 解锁通道选择

        # 启动/停止采集
        self.start_btn = QPushButton("启动采集")
        self.start_btn.clicked.connect(self.start_collect)
        self.start_btn.setEnabled(False)
        self.stop_btn = QPushButton("停止采集")
        self.stop_btn.clicked.connect(self.stop_collect)
        self.stop_btn.setEnabled(False)
        
        # 网络发送控制按钮
        self.network_send_btn = QPushButton("发送数据")
        self.network_send_btn.clicked.connect(self.toggle_network_send)
        self.network_send_btn.setEnabled(False)
        self.network_sending = False
        
        # 数据显示
        self.temp_label = QLabel("温度: -- ℃")
        self.humi_label = QLabel("湿度: -- %")
        self.freq_label = QLabel("频率: -- Hz")
        self.half_temp_label = QLabel("减半温度: -- ℃")
        self.half_humi_label = QLabel("减半湿度: -- %")
        self.half_freq_label = QLabel("减半频率: -- Hz")
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)

        # 折线图相关
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(QColor(255, 255, 255, 220))  # 半透明白色背景
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLabel('left', '数值')
        self.plot_widget.setLabel('bottom', '采样点')
        plot_item = self.plot_widget.getPlotItem()
        if plot_item is not None:
            plot_item.getAxis('bottom').setTicks([[(i, str(i+1)) for i in range(10)]])
        self.temp_curve = self.plot_widget.plot(pen=pg.mkPen('r', width=2), name='温度')
        self.humi_curve = self.plot_widget.plot(pen=pg.mkPen('b', width=2), name='湿度')
        self.freq_curve = self.plot_widget.plot(pen=pg.mkPen('g', width=2), name='频率')
        self.data_len = 100
        self.temp_data = []
        self.humi_data = []
        self.freq_data = []

        # 阈值标题标签和单位/分隔符，必须在布局前定义
        self.temp_thresh_title = QLabel("温度范围:")
        self.humi_thresh_title = QLabel("湿度范围:")
        self.freq_thresh_title = QLabel("频率范围:")
        def set_small_label_shadow(label):
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(0)
            effect.setColor(QColor(0,0,0))
            effect.setOffset(1, 1)
            label.setGraphicsEffect(effect)
            label.setStyleSheet("color: white; font-weight: bold; font-size: 16px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;")
        set_small_label_shadow(self.temp_thresh_title)
        set_small_label_shadow(self.humi_thresh_title)
        set_small_label_shadow(self.freq_thresh_title)
        # 美化中间符号和单位
        self.temp_range_sep = QLabel("~")
        self.temp_range_unit = QLabel("℃")
        set_small_label_shadow(self.temp_range_sep)
        set_small_label_shadow(self.temp_range_unit)
        self.humi_range_sep = QLabel("~")
        self.humi_range_unit = QLabel("%")
        set_small_label_shadow(self.humi_range_sep)
        set_small_label_shadow(self.humi_range_unit)
        self.freq_range_sep = QLabel("~")
        self.freq_range_unit = QLabel("Hz")
        set_small_label_shadow(self.freq_range_sep)
        set_small_label_shadow(self.freq_range_unit)

        # 阈值输入框（QLineEdit）
        self.temp_min_edit = QLineEdit("0")
        self.temp_max_edit = QLineEdit("40")
        self.humi_min_edit = QLineEdit("0")
        self.humi_max_edit = QLineEdit("90")
        self.freq_min_edit = QLineEdit("0")
        self.freq_max_edit = QLineEdit("6000")
        for edit in [self.temp_min_edit, self.temp_max_edit, self.humi_min_edit, self.humi_max_edit, self.freq_min_edit, self.freq_max_edit]:
            edit.setFixedWidth(60)
            edit.setStyleSheet("background: rgba(255,255,255,180); color: #222; border-radius: 6px; border: 1px solid #bbb; font-size: 15px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; padding: 2px 6px;")

        # 阈值布局（输入框+单位）
        self.temp_thresh_layout = QHBoxLayout()
        self.temp_thresh_layout.addWidget(self.temp_thresh_title)
        self.temp_thresh_layout.addWidget(self.temp_min_edit)
        self.temp_thresh_layout.addWidget(self.temp_range_sep)
        self.temp_thresh_layout.addWidget(self.temp_max_edit)
        self.temp_thresh_layout.addWidget(self.temp_range_unit)
        self.temp_thresh_layout.addStretch(1)

        self.humi_thresh_layout = QHBoxLayout()
        self.humi_thresh_layout.addWidget(self.humi_thresh_title)
        self.humi_thresh_layout.addWidget(self.humi_min_edit)
        self.humi_thresh_layout.addWidget(self.humi_range_sep)
        self.humi_thresh_layout.addWidget(self.humi_max_edit)
        self.humi_thresh_layout.addWidget(self.humi_range_unit)
        self.humi_thresh_layout.addStretch(1)

        self.freq_thresh_layout = QHBoxLayout()
        self.freq_thresh_layout.addWidget(self.freq_thresh_title)
        self.freq_thresh_layout.addWidget(self.freq_min_edit)
        self.freq_thresh_layout.addWidget(self.freq_range_sep)
        self.freq_thresh_layout.addWidget(self.freq_max_edit)
        self.freq_thresh_layout.addWidget(self.freq_range_unit)
        self.freq_thresh_layout.addStretch(1)

        # 优化按钮大小和样式（白底半透明，禁用更灰）
        button_width = 120
        button_height = 36
        button_style = """
        QPushButton {
            background: rgba(255,255,255,180);
            color: #222;
            border-radius: 6px;
            border: 1px solid #bbb;
            font-size: 16px;
            font-weight: bold;
            padding: 6px 16px;
            font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
        }
        QPushButton:hover {
            background: rgba(255,255,255,220);
            border: 1.5px solid #4A90E2;
        }
        QPushButton:pressed {
            background: rgba(230,230,230,200);
        }
        QPushButton:disabled {
            background: rgba(220,220,220,180);
            color: #aaa;
            border: 1px solid #ccc;
        }
        """
        combo_style = """
        QComboBox {
            background: rgba(255,255,255,180);
            color: #222;
            border-radius: 6px;
            border: 1px solid #bbb;
            font-size: 15px;
            font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
            padding: 4px 12px;
        }
        QComboBox:disabled {
            background: rgba(220,220,220,180);
            color: #aaa;
            border: 1px solid #ccc;
        }
        """
        for btn in [self.open_btn, self.close_btn, self.refresh_btn, self.start_btn, self.stop_btn, self.network_send_btn]:
            btn.setMinimumWidth(button_width)
            btn.setMinimumHeight(button_height)
            btn.setStyleSheet(button_style)
        self.channel_combo.setStyleSheet(combo_style)
        self.port_combo.setStyleSheet(combo_style)

        # 合并调试按钮为一个下拉菜单弹窗选择信号发送
        self.debug_btn = QPushButton("调试信号发送")
        self.debug_btn.setMinimumWidth(120)
        self.debug_btn.setMinimumHeight(36)
        self.debug_btn.setStyleSheet(button_style)
        self.debug_menu = QMenu()
        debug_signals = [
            ("发送X", b'X'),
            ("发送Y", b'Y'),
            ("发送Z", b'Z'),
            ("发送x", b'x'),
            ("发送y", b'y'),
            ("发送z", b'z'),
        ]
        for label, sig in debug_signals:
            self.debug_menu.addAction(label, lambda checked=False, s=sig: self.send_debug_signal(s))
        self.debug_btn.setMenu(self.debug_menu)
        # 调试按钮布局
        self.debug_btn_layout = QHBoxLayout()
        self.debug_btn_layout.addWidget(self.debug_btn)
        self.debug_btn_layout.addStretch(1)
        


        # 分散对齐布局
        h0 = QHBoxLayout()
        h0.addWidget(self.channel_label)
        h0.addWidget(self.channel_combo)
        h0.addStretch(1)
        for btn in [self.debug_btn]:
            h0.addWidget(btn)

        h1 = QHBoxLayout()
        h1.addWidget(self.port_label)
        h1.addWidget(self.port_combo)
        h1.addStretch(1)
        h1.addWidget(self.refresh_btn)

        # 控制按钮水平布局（右下角）
        control_btn_hlayout = QHBoxLayout()
        control_btn_hlayout.addWidget(self.open_btn)
        control_btn_hlayout.addWidget(self.close_btn)
        control_btn_hlayout.addWidget(self.start_btn)
        control_btn_hlayout.addWidget(self.stop_btn)
        control_btn_hlayout.setSpacing(16)

        # 底部按钮区：控制按钮在右侧，网络发送按钮在左侧
        bottom_hlayout = QHBoxLayout()
        bottom_hlayout.addWidget(self.network_send_btn)  # 网络发送按钮在左侧
        bottom_hlayout.addStretch(1)
        bottom_hlayout.addWidget(self.open_btn)
        bottom_hlayout.addWidget(self.close_btn)
        bottom_hlayout.addWidget(self.start_btn)
        bottom_hlayout.addWidget(self.stop_btn)
        bottom_hlayout.setContentsMargins(10, 10, 10, 10)
        bottom_hlayout.setSpacing(32)

        # 温度范围和湿度范围水平两端对齐放置
        self.temp_humi_row_layout = QHBoxLayout()
        self.temp_humi_row_layout.addLayout(self.temp_thresh_layout)
        self.temp_humi_row_layout.addStretch(1)
        self.temp_humi_row_layout.addLayout(self.humi_thresh_layout)

        # 主界面左右布局
        left_v = QVBoxLayout()
        left_v.addLayout(h0)
        left_v.addLayout(h1)
        left_v.addSpacing(16)
        left_v.addLayout(self.temp_humi_row_layout)
        left_v.addLayout(self.freq_thresh_layout)
        left_v.addSpacing(8)
        # 温湿度并排左，减半温湿度并排右
        temp_humi_full_row = QHBoxLayout()
        temp_humi_left = QHBoxLayout()
        temp_humi_left.addWidget(self.temp_label)
        temp_humi_left.addWidget(self.humi_label)
        temp_humi_right = QHBoxLayout()
        temp_humi_right.addWidget(self.half_temp_label)
        temp_humi_right.addWidget(self.half_humi_label)
        temp_humi_full_row.addLayout(temp_humi_left)
        temp_humi_full_row.addStretch(1)
        temp_humi_full_row.addLayout(temp_humi_right)
        left_v.addLayout(temp_humi_full_row)
        # 频率两端对齐
        freq_row = QHBoxLayout()
        freq_row.addWidget(self.freq_label)
        freq_row.addWidget(self.half_freq_label)
        left_v.addLayout(freq_row)
        left_v.addWidget(self.plot_widget)  # 恢复为最初的折线图布局
        left_v.addStretch(1)
        left_v.addLayout(self.debug_btn_layout)
        


        # 右侧区域（串口信息区）
        right_v = QVBoxLayout()
        self.text_area.setMaximumWidth(int(self.width() * 0.4))
        self.text_area.setStyleSheet("background: rgba(0,0,0,128); color: white; border: 2px solid #fff; border-radius: 8px;")
        right_v.addWidget(self.text_area)

        # 主体水平布局
        main_h = QHBoxLayout()
        main_h.addLayout(left_v, 2)
        main_h.addLayout(right_v, 3)

        # 最外层VBoxLayout，底部一行按钮
        main_v = QVBoxLayout()
        main_v.addLayout(main_h)
        main_v.addLayout(bottom_hlayout)
        self.setLayout(main_v)
        self.change_channel(0)

        # 设置text_area为半透明
        self.text_area.setStyleSheet("background: rgba(0,0,0,128); color: white;")

        # 统一所有label样式为频率样式
        for label in [self.channel_label, self.port_label, self.temp_label, self.humi_label, self.freq_label, self.half_temp_label, self.half_humi_label, self.half_freq_label]:
            set_label_shadow(label)

        # 设置温度、湿度、减半温度、减半湿度、频率、减半频率字号调小，两端对齐
        def set_small_label_shadow_align(label, align):
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(0)
            effect.setColor(QColor(0,0,0))
            effect.setOffset(1, 1)
            label.setGraphicsEffect(effect)
            label.setStyleSheet("color: white; font-weight: bold; font-size: 16px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;")
            label.setAlignment(align)
        set_small_label_shadow_align(self.temp_label, Qt.AlignLeft) # type: ignore
        set_small_label_shadow_align(self.humi_label, Qt.AlignRight) # type: ignore
        set_small_label_shadow_align(self.half_temp_label, Qt.AlignLeft) # type: ignore
        set_small_label_shadow_align(self.half_humi_label, Qt.AlignRight) # type: ignore
        set_small_label_shadow_align(self.freq_label, Qt.AlignLeft) # type: ignore
        set_small_label_shadow_align(self.half_freq_label, Qt.AlignRight) # type: ignore

        # 设置背景图片（自适应窗口大小+淡灰色蒙版）
        import os
        self.bg_path = os.path.join(os.path.dirname(__file__), "bg.jpg")
        self.bg_pixmap = QPixmap(self.bg_path) if os.path.exists(self.bg_path) else None
        self.setAutoFillBackground(True)
        self.update_background()

    def update_background(self):
        if self.bg_pixmap:
            palette = QPalette()
            # 兼容不同PyQt5版本，动态获取枚举值
            aspect = getattr(Qt, 'KeepAspectRatioByExpanding', 1)
            trans = getattr(Qt, 'SmoothTransformation', 2)
            img = self.bg_pixmap.toImage().scaled(
                self.size(),
                aspect,
                trans   # type: ignore
            )  # type: ignore
            # 创建淡灰色蒙版
            overlay = QImage(img.size(), QImage.Format_ARGB32)
            overlay.fill(QColor(200, 200, 200, 80))  # 80为透明度
            painter = QPainter(img)
            painter.drawImage(0, 0, overlay)
            painter.end()
            scaled = QPixmap.fromImage(img)
            palette.setBrush(QPalette.Window, QBrush(scaled))
            self.setPalette(palette)

    def resizeEvent(self, event):
        # 固定宽高比为1920:1080
        w = self.width()
        h = int(w * 1080 / 1920)
        if h != self.height():
            self.setFixedSize(w, h)
        self.update_background()
        super().resizeEvent(event)

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def open_serial(self):
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, "错误", "请选择串口号")
            return
        try:
            self.ser = serial.Serial(port, 9600, timeout=1)
            self.serial_thread = SerialThread(self.ser)
            self.serial_thread.data_received.connect(self.on_data_received)
            self.serial_thread.start()
            self.open_btn.setEnabled(False)
            self.close_btn.setEnabled(True)
            self.start_btn.setEnabled(True)
            self.network_send_btn.setEnabled(True)  # 启用网络发送按钮
            self.text_area.append("串口已打开")
            # 打开串口后立即同步通道
            self.send_channel_cmd()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开串口失败: {e}")

    def close_serial(self):
        if self.serial_thread:
            self.serial_thread.stop()
        if self.ser and self.ser.is_open:
            self.ser.close()
        # 停止网络发送
        if self.network_sending:
            self.stop_network_send()
        self.open_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.network_send_btn.setEnabled(False)  # 禁用网络发送按钮
        self.channel_combo.setEnabled(True) # 解锁通道选择
        self.text_area.append("串口已关闭")

    def start_collect(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'CMD:S\r\n')
            self.text_area.append("已发送启动命令")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.channel_combo.setEnabled(False) # 锁定通道选择
            self.close_btn.setEnabled(False) # 采集时不能关闭串口

    def stop_collect(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'CMD:E\r\n')
            self.text_area.append("已发送停止命令")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.channel_combo.setEnabled(True) # 解锁通道选择
            self.close_btn.setEnabled(True) # 停止采集后可关闭串口

    def change_channel(self, idx):
        self.current_channel = idx
        self.update_channel_ui()
        self.send_channel_cmd()

    def send_channel_cmd(self):
        if self.ser and self.ser.is_open:
            if self.current_channel == 0:
                self.ser.write(b'CMD:A\r\n')  # 温湿度
                self.text_area.append("切换到温湿度通道")
            else:
                self.ser.write(b'CMD:B\r\n')  # 频率
                self.text_area.append("切换到频率通道")

    def update_channel_ui(self):
        if self.current_channel == 0:
            self.temp_label.setVisible(True)
            self.humi_label.setVisible(True)
            self.freq_label.setVisible(False)
            self.half_temp_label.setVisible(True)
            self.half_humi_label.setVisible(True)
            self.half_freq_label.setVisible(False)
            # 显示温湿度阈值，隐藏频率阈值
            for l in [self.temp_thresh_layout, self.humi_thresh_layout]:
                for i in range(l.count()):
                    item = l.itemAt(i)
                    w = item.widget() # type: ignore
                    if w is not None:
                        w.setVisible(True)
            for i in range(self.freq_thresh_layout.count()):
                item = self.freq_thresh_layout.itemAt(i)
                w = item.widget() # type: ignore
                if w is not None:
                    w.setVisible(False)
        else:
            self.temp_label.setVisible(False)
            self.humi_label.setVisible(False)
            self.freq_label.setVisible(True)
            self.half_temp_label.setVisible(False)
            self.half_humi_label.setVisible(False)
            self.half_freq_label.setVisible(True)
            # 显示频率阈值，隐藏温湿度阈值
            for l in [self.temp_thresh_layout, self.humi_thresh_layout]:
                for i in range(l.count()):
                    item = l.itemAt(i)
                    w = item.widget() # type: ignore
                    if w is not None:
                        w.setVisible(False)
            for i in range(self.freq_thresh_layout.count()):
                item = self.freq_thresh_layout.itemAt(i)
                w = item.widget() # type: ignore
                if w is not None:
                    w.setVisible(True)

    def calculate_checksum(self, data_str):
        """计算字符串的校验和"""
        checksum = 0
        for char in data_str:
            checksum += ord(char)
        return checksum  

    def validate_checksum(self, line):
        """校验和验证"""
        if "CHECKSUM:" not in line:
            return False, "缺少校验和"
        
        # 分离数据和校验和
        parts = line.split(" CHECKSUM:")
        if len(parts) != 2:
            return False, "校验和格式错误"
        
        data_part = parts[0]
        try:
            received_checksum = int(parts[1])
        except ValueError:
            return False, "校验和数值格式错误"
        
        # 计算校验和
        calculated_checksum = self.calculate_checksum(data_part)
        
        if received_checksum != calculated_checksum:
            return False, f"校验和不匹配: 接收={received_checksum}, 计算={calculated_checksum}"
        
        return True, f"校验和正确: {calculated_checksum}"

    def validate_data_format(self, data_part):
        """数据格式和范围校验（不包含校验和）"""
        try:
            if self.current_channel == 0:
                # 温湿度通道校验
                if not re.match(r"T:\d+\s+H:\d+", data_part):
                    return False, "温湿度数据格式错误"
                t, h = map(int, re.findall(r"\d+", data_part))
                if not (0 <= t <= 100):
                    return False, f"温度数值超出范围: {t}℃"
                if not (0 <= h <= 100):
                    return False, f"湿度数值超出范围: {h}%"
                return True, f"温湿度数据有效: T={t}℃, H={h}%"
            else:
                # 频率通道校验
                if not re.match(r"FREQ:\d+", data_part):
                    return False, "频率数据格式错误"
                match = re.search(r"\d+", data_part)
                if not match:
                    return False, "频率数值提取失败"
                f = int(match.group())
                if not (0 <= f <= 10000):
                    return False, f"频率数值超出范围: {f}Hz"
                return True, f"频率数据有效: {f}Hz"
        except Exception as e:
            return False, f"数据解析异常: {str(e)}"

    def validate_data_with_checksum(self, line):
        """带校验和的完整数据校验"""
        # 1. 校验和验证
        checksum_valid, checksum_msg = self.validate_checksum(line)
        if not checksum_valid:
            return False, checksum_msg
        
        # 2. 数据格式和范围校验
        data_part = line.split(" CHECKSUM:")[0]
        format_valid, format_msg = self.validate_data_format(data_part)
        if not format_valid:
            return False, format_msg
        
        return True, f"{format_msg} | {checksum_msg}"

    def on_data_received(self, line):
        self.text_area.append(line)
        
        # 只处理包含校验和的数据，忽略调试信息
        if "CHECKSUM:" not in line:
            return
        
        # 数据校验（包含校验和）
        is_valid, message = self.validate_data_with_checksum(line)
        if not is_valid:
            self.text_area.append(f"❌ 数据校验失败: {message}")
            return
        else:
            self.text_area.append(f"✅ {message}")
        
        # 提取数据部分（不含校验和）
        data_part = line.split(" CHECKSUM:")[0]
        
        if self.current_channel == 0:
            # 解析温湿度
            match = re.search(r"T:(\d+)\s+H:(\d+)", data_part)
            if match:
                t = int(match.group(1))
                h = int(match.group(2))
                self.temp_label.setText(f"温度: {t} ℃")
                self.humi_label.setText(f"湿度: {h} %")
                half_t = t // 2
                half_h = h // 2
                self.half_temp_label.setText(f"减半温度: {half_t} ℃")
                self.half_humi_label.setText(f"减半湿度: {half_h} %")
                # 折线图数据更新
                self.temp_data.append(t)
                self.humi_data.append(h)
                if len(self.temp_data) > self.data_len:
                    self.temp_data = self.temp_data[-self.data_len:]
                if len(self.humi_data) > self.data_len:
                    self.humi_data = self.humi_data[-self.data_len:]
                temp_y = self.temp_data[-10:]
                humi_y = self.humi_data[-10:]
                x = list(range(1, len(temp_y) + 1))
                self.temp_curve.setData(x, temp_y)
                self.humi_curve.setData(x, humi_y)
                self.freq_curve.setData([], [])  # 清空频率曲线
                
                # 向服务器发送数据
                if self.network_sending:
                    server_data = {
                        "type": "temperature_humidity",
                        "temperature": t,
                        "humidity": h,
                        "half_temperature": half_t,
                        "half_humidity": half_h,
                        "timestamp": int(time.time() * 1000)
                    }
                    self.send_data_to_server(json.dumps(server_data))
                
                # 阈值判断
                try:
                    tmin = float(self.temp_min_edit.text())
                    tmax = float(self.temp_max_edit.text())
                    hmin = float(self.humi_min_edit.text())
                    hmax = float(self.humi_max_edit.text())
                except Exception:
                    tmin, tmax, hmin, hmax = 0, 100, 0, 100
                
                # 检查是否需要发送报警信号
                temp_alarm_needed = (t < tmin or t > tmax) != self.temp_alarm_on
                humi_alarm_needed = (h < hmin or h > hmax) != self.humi_alarm_on
                
                if self.ser and self.ser.is_open:
                    # 如果需要发送报警信号，则不回发减半数据
                    if temp_alarm_needed or humi_alarm_needed:
                        # 温度报警逻辑
                        if t < tmin or t > tmax:
                            if not self.temp_alarm_on:
                                self.send_debug_signal(b'X')
                                self.text_area.append("温度超出阈值，已发送'X'")
                                self.temp_alarm_on = True
                        else:
                            if self.temp_alarm_on:
                                self.send_debug_signal(b'x')
                                self.text_area.append("温度恢复正常，已发送'x'")
                                self.temp_alarm_on = False
                        # 湿度报警逻辑
                        if h < hmin or h > hmax:
                            if not self.humi_alarm_on:
                                self.send_debug_signal(b'Y')
                                self.text_area.append("湿度超出阈值，已发送'Y'")
                                self.humi_alarm_on = True
                        else:
                            if self.humi_alarm_on:
                                self.send_debug_signal(b'y')
                                self.text_area.append("湿度恢复正常，已发送'y'")
                                self.humi_alarm_on = False
                    else:
                        # 不需要报警时，回发减半数据（带校验和）
                        half_data = f"{half_t} {half_h}"
                        checksum = self.calculate_checksum(half_data)
                        self.ser.write(f"{half_data} CHECKSUM:{checksum}\r\n".encode())
        else:
            # 解析频率
            match = re.search(r"FREQ:(\d+)", data_part)
            if match:
                f = int(match.group(1))
                self.freq_label.setText(f"频率: {f} Hz")
                half_f = f // 2
                self.half_freq_label.setText(f"减半频率: {half_f} Hz")
                # 折线图数据更新
                self.freq_data.append(f)
                if len(self.freq_data) > self.data_len:
                    self.freq_data = self.freq_data[-self.data_len:]
                freq_y = self.freq_data[-10:]
                x = list(range(1, len(freq_y) + 1))
                self.freq_curve.setData(x, freq_y)
                self.temp_curve.setData([], [])  # 清空温度曲线
                self.humi_curve.setData([], [])  # 清空湿度曲线
                
                # 向服务器发送数据
                if self.network_sending:
                    server_data = {
                        "type": "frequency",
                        "frequency": f,
                        "half_frequency": half_f,
                        "timestamp": int(time.time() * 1000)
                    }
                    self.send_data_to_server(json.dumps(server_data))
                
                # 阈值判断
                try:
                    fmin = float(self.freq_min_edit.text())
                    fmax = float(self.freq_max_edit.text())
                except Exception:
                    fmin, fmax = 0, 10000
                
                # 检查是否需要发送报警信号
                freq_alarm_needed = (f < fmin or f > fmax) != self.freq_alarm_on
                
                if self.ser and self.ser.is_open:
                    # 如果需要发送报警信号，则不回发减半数据
                    if freq_alarm_needed:
                        # 频率报警逻辑
                        if f < fmin or f > fmax:
                            if not self.freq_alarm_on:
                                self.send_debug_signal(b'Z')
                                self.text_area.append("频率超出阈值，已发送'Z'")
                                self.freq_alarm_on = True
                        else:
                            if self.freq_alarm_on:
                                self.send_debug_signal(b'z')
                                self.text_area.append("频率恢复正常，已发送'z'")
                                self.freq_alarm_on = False
                    else:
                        # 不需要报警时，回发减半数据（带校验和）
                        half_data = f"{half_f}"
                        checksum = self.calculate_checksum(half_data)
                        self.ser.write(f"{half_data} CHECKSUM:{checksum}\r\n".encode())

    def toggle_network_send(self):
        """切换网络发送状态"""
        self.text_area.append(f"🔍 点击发送数据按钮，当前状态: network_sending={self.network_sending}")
        if not self.network_sending:
            # 开始发送
            self.text_area.append("🚀 开始网络发送...")
            self.start_network_send()
        else:
            # 停止发送
            self.text_area.append("⏹️ 停止网络发送...")
            self.stop_network_send()
    
    def start_network_send(self):
        """开始网络发送"""
        self.text_area.append(f"🔧 创建网络线程，服务器URL: {self.server_url}")
        if not self.network_thread:
            self.network_thread = NetworkThread(self.server_url)
            self.network_thread.send_log.connect(self.on_network_log)
            self.network_thread.start()
            self.text_area.append("✅ 网络线程已启动")
        
        self.network_sending = True
        self.network_send_btn.setText("停止发送")
        self.network_send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,100,100,180);
                color: white;
                border-radius: 6px;
                border: 1px solid #bbb;
                font-size: 16px;
                font-weight: bold;
                padding: 6px 16px;
                font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
            }
            QPushButton:hover {
                background: rgba(255,120,120,220);
                border: 1.5px solid #E74C3C;
            }
        """)
        self.text_area.append("✅ 开始向服务器发送数据")
    
    def stop_network_send(self):
        """停止网络发送"""
        if self.network_thread:
            self.network_thread.stop()
            self.network_thread = None
        
        self.network_sending = False
        self.network_send_btn.setText("发送数据")
        self.network_send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,180);
                color: #222;
                border-radius: 6px;
                border: 1px solid #bbb;
                font-size: 16px;
                font-weight: bold;
                padding: 6px 16px;
                font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
            }
            QPushButton:hover {
                background: rgba(255,255,255,220);
                border: 1.5px solid #4A90E2;
            }
        """)
        self.text_area.append("⏹️ 已停止向服务器发送数据")
    
    def on_network_log(self, message):
        """处理网络线程的日志消息"""
        self.text_area.append(message)
    
    def send_data_to_server(self, data):
        """向服务器发送数据"""
        if self.network_thread and self.network_sending:
            self.text_area.append(f"📤 准备发送数据: {data[:100]}...")
            self.network_thread.send_data(data)
        else:
            self.text_area.append(f"⚠️ 网络发送未启用: network_thread={self.network_thread is not None}, network_sending={self.network_sending}")

    def send_debug_signal(self, sig):
        if self.ser and self.ser.is_open:
            # 统一发送带 CMD: 前缀的命令
            if isinstance(sig, bytes):
                sig_str = sig.decode(errors='ignore').strip()
            else:
                sig_str = str(sig).strip()
            cmd = f"CMD:{sig_str}\r\n".encode()
            self.ser.write(cmd)
            self.text_area.append(f"已发送调试信号: CMD:{sig_str}")
        else:
            QMessageBox.warning(self, "错误", "串口未打开，无法发送调试信号")
    


    def closeEvent(self, event):
        # 停止网络发送
        if self.network_sending:
            self.stop_network_send()
        self.close_serial()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())