import sys
import serial
import serial.tools.list_ports
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QTextEdit, QMessageBox, QLineEdit, QFormLayout
)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QPalette, QBrush, QPixmap, QPainter, QColor, QImage
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
import PyQt5.QtCore as QtCore
from PyQt5.QtCore import Qt

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

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("温湿度/频率监控上位机")
        self.ser = None
        self.serial_thread = None
        self.current_channel = 1 # 0=温湿度, 1=频率

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
        self.channel_combo.setCurrentIndex(1)
        self.channel_combo.currentIndexChanged.connect(self.change_channel)

        # 串口选择
        self.port_label = QLabel("串口号:")
        self.port_combo = QComboBox()
        self.refresh_ports()
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
        
        # 数据显示
        self.temp_label = QLabel("温度: -- ℃")
        self.humi_label = QLabel("湿度: -- %")
        self.freq_label = QLabel("频率: -- Hz")
        self.half_temp_label = QLabel("减半温度: -- ℃")
        self.half_humi_label = QLabel("减半湿度: -- %")
        self.half_freq_label = QLabel("减半频率: -- Hz")
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)

        # 阈值输入框
        self.temp_min_edit = QLineEdit("0")
        self.temp_max_edit = QLineEdit("100")
        self.humi_min_edit = QLineEdit("0")
        self.humi_max_edit = QLineEdit("100")
        self.freq_min_edit = QLineEdit("0")
        self.freq_max_edit = QLineEdit("10000")
        for edit in [self.temp_min_edit, self.temp_max_edit, self.humi_min_edit, self.humi_max_edit, self.freq_min_edit, self.freq_max_edit]:
            edit.setFixedWidth(60)
            edit.setStyleSheet("background: rgba(255,255,255,180); color: #222; border-radius: 6px; border: 1px solid #bbb; font-size: 15px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; padding: 2px 6px;")

        # 阈值确认按钮
        self.temp_thresh_btn = QPushButton("确认")
        self.humi_thresh_btn = QPushButton("确认")
        self.freq_thresh_btn = QPushButton("确认")
        for btn in [self.temp_thresh_btn, self.humi_thresh_btn, self.freq_thresh_btn]:
            btn.setFixedWidth(60)
            btn.setStyleSheet("background: rgba(255,255,255,180); color: #222; border-radius: 6px; border: 1px solid #bbb; font-size: 15px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; padding: 2px 6px;")

        self.temp_thresh_btn.clicked.connect(lambda: QMessageBox.information(self, "提示", "温度阈值已更新"))
        self.humi_thresh_btn.clicked.connect(lambda: QMessageBox.information(self, "提示", "湿度阈值已更新"))
        self.freq_thresh_btn.clicked.connect(lambda: QMessageBox.information(self, "提示", "频率阈值已更新"))

        # 阈值布局
        self.temp_thresh_layout = QHBoxLayout()
        self.temp_thresh_layout.addWidget(QLabel("温度阈值:"))
        self.temp_thresh_layout.addWidget(self.temp_min_edit)
        self.temp_thresh_layout.addWidget(QLabel("~"))
        self.temp_thresh_layout.addWidget(self.temp_max_edit)
        self.temp_thresh_layout.addWidget(QLabel("℃"))
        self.temp_thresh_layout.addWidget(self.temp_thresh_btn)
        self.temp_thresh_layout.addStretch(1)

        self.humi_thresh_layout = QHBoxLayout()
        self.humi_thresh_layout.addWidget(QLabel("湿度阈值:"))
        self.humi_thresh_layout.addWidget(self.humi_min_edit)
        self.humi_thresh_layout.addWidget(QLabel("~"))
        self.humi_thresh_layout.addWidget(self.humi_max_edit)
        self.humi_thresh_layout.addWidget(QLabel("%"))
        self.humi_thresh_layout.addWidget(self.humi_thresh_btn)
        self.humi_thresh_layout.addStretch(1)

        self.freq_thresh_layout = QHBoxLayout()
        self.freq_thresh_layout.addWidget(QLabel("频率阈值:"))
        self.freq_thresh_layout.addWidget(self.freq_min_edit)
        self.freq_thresh_layout.addWidget(QLabel("~"))
        self.freq_thresh_layout.addWidget(self.freq_max_edit)
        self.freq_thresh_layout.addWidget(QLabel("Hz"))
        self.freq_thresh_layout.addWidget(self.freq_thresh_btn)
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
        for btn in [self.open_btn, self.close_btn, self.refresh_btn, self.start_btn, self.stop_btn]:
            btn.setMinimumWidth(button_width)
            btn.setMinimumHeight(button_height)
            btn.setStyleSheet(button_style)
        self.channel_combo.setStyleSheet(combo_style)
        self.port_combo.setStyleSheet(combo_style)

        # 添加调试信号按钮
        self.debug_btns = []
        debug_signals = [
            ("发送X", b'X'),
            ("发送Y", b'Y'),
            ("发送Z", b'Z'),
            ("发送x", b'x'),
            ("发送y", b'y'),
            ("发送z", b'z'),
        ]
        for label, sig in debug_signals:
            btn = QPushButton(label)
            btn.setMinimumWidth(80)
            btn.setMinimumHeight(32)
            btn.setStyleSheet("background: rgba(255,255,255,180); color: #222; border-radius: 6px; border: 1px solid #bbb; font-size: 15px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif; padding: 2px 8px;")
            btn.clicked.connect(lambda _, s=sig: self.send_debug_signal(s))
            self.debug_btns.append(btn)
        # 调试按钮布局
        self.debug_btn_layout = QHBoxLayout()
        for btn in self.debug_btns:
            self.debug_btn_layout.addWidget(btn)
        self.debug_btn_layout.addStretch(1)

        # 分散对齐布局
        h0 = QHBoxLayout()
        h0.addWidget(self.channel_label)
        h0.addWidget(self.channel_combo)
        h0.addStretch(1)

        h1 = QHBoxLayout()
        h1.addWidget(self.port_label)
        h1.addWidget(self.port_combo)
        h1.addStretch(1)
        h1.addWidget(self.refresh_btn)
        h1.addWidget(self.open_btn)
        h1.addWidget(self.close_btn)

        h2 = QHBoxLayout()
        h2.addWidget(self.start_btn)
        h2.addStretch(1)
        h2.addWidget(self.stop_btn)

        v = QVBoxLayout()
        v.addLayout(h0)
        v.addLayout(h1)
        v.addLayout(h2)
        v.addLayout(self.debug_btn_layout)  # 添加调试按钮布局
        v.addLayout(self.temp_thresh_layout)
        v.addLayout(self.humi_thresh_layout)
        v.addLayout(self.freq_thresh_layout)
        v.addWidget(self.temp_label)
        v.addWidget(self.humi_label)
        v.addWidget(self.freq_label)
        v.addWidget(self.half_temp_label)
        v.addWidget(self.half_humi_label)
        v.addWidget(self.half_freq_label)
        v.addWidget(self.text_area)
        self.setLayout(v)
        self.update_channel_ui()

        # 设置text_area为半透明
        self.text_area.setStyleSheet("background: rgba(0,0,0,128); color: white;")

        # 设置所有label为白色加黑色描边，字体更大，微软雅黑
        def set_label_shadow(label):
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(0)
            effect.setColor(QColor(0,0,0))
            effect.setOffset(1, 1)
            label.setGraphicsEffect(effect)
            label.setStyleSheet("color: white; font-weight: bold; font-size: 20px; font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;")
        for label in [self.channel_label, self.port_label, self.temp_label, self.humi_label, self.freq_label, self.half_temp_label, self.half_humi_label, self.half_freq_label]:
            set_label_shadow(label)

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
        self.open_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.channel_combo.setEnabled(True) # 解锁通道选择
        self.text_area.append("串口已关闭")

    def start_collect(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'S')
            self.text_area.append("已发送启动命令")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.channel_combo.setEnabled(False) # 锁定通道选择
            self.close_btn.setEnabled(False) # 采集时不能关闭串口

    def stop_collect(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'E')
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
                self.ser.write(b'A')  # 温湿度
                self.text_area.append("切换到温湿度通道")
            else:
                self.ser.write(b'B')  # 频率
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
                    w = item.widget()
                    if w is not None:
                        w.setVisible(True)
            for i in range(self.freq_thresh_layout.count()):
                item = self.freq_thresh_layout.itemAt(i)
                w = item.widget()
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
                    w = item.widget()
                    if w is not None:
                        w.setVisible(False)
            for i in range(self.freq_thresh_layout.count()):
                item = self.freq_thresh_layout.itemAt(i)
                w = item.widget()
                if w is not None:
                    w.setVisible(True)

    def on_data_received(self, line):
        self.text_area.append(line)
        print(f"原始数据: {line}")
        if self.current_channel == 0:
            # 解析温湿度
            match = re.search(r"T:(\d+)\s+H:(\d+)", line)
            if match:
                t = int(match.group(1))
                h = int(match.group(2))
                self.temp_label.setText(f"温度: {t} ℃")
                self.humi_label.setText(f"湿度: {h} %")
                half_t = t // 2
                half_h = h // 2
                self.half_temp_label.setText(f"减半温度: {half_t} ℃")
                self.half_humi_label.setText(f"减半湿度: {half_h} %")
                # 回发减半后的数字，格式："{half_t} {half_h}\r\n"
                if self.ser and self.ser.is_open:
                    self.ser.write(f"{half_t} {half_h}\r\n".encode())
                # 阈值判断
                try:
                    tmin = float(self.temp_min_edit.text())
                    tmax = float(self.temp_max_edit.text())
                    hmin = float(self.humi_min_edit.text())
                    hmax = float(self.humi_max_edit.text())
                except Exception:
                    tmin, tmax, hmin, hmax = 0, 100, 0, 100
                if self.ser and self.ser.is_open:
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
            # 解析频率
            match = re.search(r"FREQ:(\d+)", line)
            if match:
                f = int(match.group(1))
                self.freq_label.setText(f"频率: {f} Hz")
                half_f = f // 2
                self.half_freq_label.setText(f"减半频率: {half_f} Hz")
                # 回发减半后的数字，格式："{half_f}\r\n"
                if self.ser and self.ser.is_open:
                    self.ser.write(f"{half_f}\r\n".encode())
                # 阈值判断
                try:
                    fmin = float(self.freq_min_edit.text())
                    fmax = float(self.freq_max_edit.text())
                except Exception:
                    fmin, fmax = 0, 10000
                if self.ser and self.ser.is_open:
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

    def send_debug_signal(self, sig):
        if self.ser and self.ser.is_open:
            self.ser.write(sig)
            self.text_area.append(f"已发送调试信号: {sig.decode(errors='ignore')}")
        else:
            QMessageBox.warning(self, "错误", "串口未打开，无法发送调试信号")

    def closeEvent(self, event):
        self.close_serial()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())