import sys
import serial
import serial.tools.list_ports
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QTextEdit, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal

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
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)

        # 布局
        h0 = QHBoxLayout()
        h0.addWidget(self.channel_label)
        h0.addWidget(self.channel_combo)

        h1 = QHBoxLayout()
        h1.addWidget(self.port_label)
        h1.addWidget(self.port_combo)
        h1.addWidget(self.refresh_btn)
        h1.addWidget(self.open_btn)
        h1.addWidget(self.close_btn)

        h2 = QHBoxLayout()
        h2.addWidget(self.start_btn)
        h2.addWidget(self.stop_btn)

        v = QVBoxLayout()
        v.addLayout(h0)
        v.addLayout(h1)
        v.addLayout(h2)
        v.addWidget(self.temp_label)
        v.addWidget(self.humi_label)
        v.addWidget(self.freq_label)
        v.addWidget(self.text_area)

        self.setLayout(v)
        self.update_channel_ui()

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

    def stop_collect(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'E')
            self.text_area.append("已发送停止命令")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.channel_combo.setEnabled(True) # 解锁通道选择

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
        else:
            self.temp_label.setVisible(False)
            self.humi_label.setVisible(False)
            self.freq_label.setVisible(True)

    def on_data_received(self, line):
        self.text_area.append(line)
        print(f"原始数据: {line}")
        if self.current_channel == 0:
            # 解析温湿度
            match = re.search(r"T:(\d+)\s+H:(\d+)", line)
            if match:
                t = match.group(1)
                h = match.group(2)
                self.temp_label.setText(f"温度: {t} ℃")
                self.humi_label.setText(f"湿度: {h} %")
        else:
            # 解析频率
            match = re.search(r"FREQ:(\d+)", line)
            if match:
                f = match.group(1)
                self.freq_label.setText(f"频率: {f} Hz")

    def closeEvent(self, event):
        self.close_serial()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())