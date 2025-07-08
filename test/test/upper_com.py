import serial
import time

def main():
    # 修改COM口为实际端口
    ser = serial.Serial('COM2', 9600, timeout=1)
    print("串口已打开，发送启动命令...")
    ser.write(b'S')
    try:
        while True:
            line = ser.readline().decode(errors='ignore').strip()
            if line:
                print("收到数据：", line)
    except KeyboardInterrupt:
        print("停止采集，发送停止命令")
        ser.write(b'E')
        ser.close()

if __name__ == "__main__":
    main() 
    