#include <reg51.h>
#include <stdio.h>
#include "lcd1602.h"
#include "dht11.h"
#include <string.h>
#include <stdlib.h>
#include <intrins.h> // 修正 _nop_ 错误
#define u8 unsigned char // 修正 u8 未定义

void UART_SendStr(char *str); // 添加函数原型声明，防止编译器警告

sbit KEY = P3^2; // 启动/停止按键

bit collect_flag = 0; // 采集标志
volatile char last_rx = 0;
volatile bit rx_flag = 0;
// char debug[17]; // 全局变量（删除，调试用局部变量）

// 优化：用于接收上位机回发的数字，增加缓冲区大小以容纳校验和
unsigned char xdata num_buf[24]; // 放到xdata区，增加大小以容纳校验和
unsigned char num_idx = 0;

volatile unsigned char current_channel = 0; // 0=DHT11, 1=555频率
volatile bit freq_sample_flag = 0;
volatile unsigned char t0_count = 0;

// -- 频率测量所需的状态变量 --
volatile unsigned int freq_count = 0; // 用于累加脉冲数量
unsigned int freq_value = 0;        // 用于存放最终计算出的频率值
static bit last_p32_state = 1;      // 用于检测P3.2引脚的下降沿

// I2C/PCF8591相关定义
sbit IIC_SDA = P1^1;
sbit IIC_SCL = P1^0;
#define PCF8591_WRITE_ADDR 0x90
#define PCF8591_READ_ADDR  0x91
//报警LED定义
sbit LED1 = P1^2;
sbit LED2 = P1^3;
sbit LED3 = P1^4;

void IIC_Delay() { _nop_(); _nop_(); _nop_(); }
void IIC_SendStart(void) {
    IIC_SDA=1; IIC_SCL=1; IIC_Delay();
    IIC_SDA=0; IIC_Delay();
    IIC_SCL=0;
}
void IIC_SendStop(void) {
    IIC_SCL=0; IIC_SDA=0; IIC_Delay();
    IIC_SCL=1; IIC_SDA=1; IIC_Delay();
}
u8 IIC_GetAck(void) {
    u8 i=0; IIC_SDA=1; IIC_SCL=1;
    while(IIC_SDA) { i++; if(i>250) { IIC_SCL=0; return 1; } }
    IIC_SCL=0; return 0;
}
void IIC_SendOneByte(u8 dat) {
    u8 j;
    for(j=0;j<8;j++) {
        IIC_SCL=0;
        IIC_SDA=(dat&0x80)?1:0;
        dat<<=1;
        IIC_SCL=1; IIC_Delay();
    }
    IIC_SCL=0;
}
void PCF8591_SetDAC_Data(u8 val) {
    IIC_SendStart();
    IIC_SendOneByte(PCF8591_WRITE_ADDR);
    IIC_GetAck();
    IIC_SendOneByte(0x40); // 控制字节：DAC使能
    IIC_GetAck();
    IIC_SendOneByte(val);
    IIC_GetAck();
    IIC_SendStop();
}
void Delay100ms() {
    unsigned char i, j;
    for(i=0;i<20;i++) {
        for(j=0;j<250;j++); // 1us*250*20=5ms*20=100ms
    }
}

// 解析并输出温湿度减半值到DAC
void handle_half_value(const char* str) {
    int t = 0, h = 0;
    UART_SendStr("[DEBUG] RAW BUF: ");
    UART_SendStr(str);
    UART_SendStr("\r\n");
    sscanf(str, "%d %d", &t, &h);
    // 先输出温度
    PCF8591_SetDAC_Data((unsigned char)t);
    UART_SendStr("[DEBUG] DAC OUT TEMP: ");
    {
        char xdata buf[8]; // 放到xdata区
        unsigned int temp_val = (unsigned char)t;
        sprintf(buf, "%u\r\n", temp_val);
        UART_SendStr(buf);
    }
    Delay100ms();
    // 再输出湿度
    PCF8591_SetDAC_Data((unsigned char)h);
    UART_SendStr("[DEBUG] DAC OUT HUMI: ");
    {
        char xdata buf[8]; // 放到xdata区
        unsigned int humi_val = (unsigned char)h;
        sprintf(buf, "%u\r\n", humi_val);
        UART_SendStr(buf);
    }
    Delay100ms();
}

// 新增：解析并输出减半频率值到DAC
void handle_half_freq(const char* str) {
    int f = 0;
    UART_SendStr("[DEBUG] RAW FREQ BUF: ");
    UART_SendStr(str);
    UART_SendStr("\r\n");
    sscanf(str, "%d", &f);
    PCF8591_SetDAC_Data((unsigned char)f);
    UART_SendStr("[DEBUG] DAC OUT FREQ: ");
    {
        char xdata buf[8];
        unsigned int freq_val = (unsigned char)f;
        sprintf(buf, "%u\r\n", freq_val);
        UART_SendStr(buf);
    }
    Delay100ms();
}

// 新增：校验和计算函数
unsigned int calculate_checksum(char *str) {
    unsigned int checksum = 0;
    while(*str) {
        checksum += *str++;
    }
    return checksum;
}

void UART_Init() {
    SCON = 0x50;      // 8位数据,可变波特率
    TMOD |= 0x20;     // 定时器1，8位自动重装
    TH1 = 0xFD;       // 9600波特率
    TL1 = 0xFD;
    TR1 = 1;
    ES = 1;
    EA = 1;
}

void Timer0_Init() {
    TMOD &= 0xF0;
    TMOD |= 0x01; // T0方式1
    TH0 = (65536 - 50000) / 256; // 50ms定时
    TL0 = (65536 - 50000) % 256;
    ET0 = 1;
    TR0 = 1;
}

void Timer1_Init() {
    TMOD &= 0x0F;
    TMOD |= 0x50; // T1方式1，计数器模式
    TH1 = 0;
    TL1 = 0;
    TR1 = 1;
}

void INT0_Init() {
    IT0 = 1; // 下降沿触发
}

void UART_SendStr(char *str) {
    while(*str) {
        SBUF = *str++;
        while(!TI);
        TI = 0;
    }
}

void UART_ISR() interrupt 4 {
    char ch;
    char *check_pos;
    unsigned int received_checksum, calculated_checksum;
    
    if(RI) {
        ch = SBUF;
        RI = 0;
        // 接收一行，遇到回车/换行处理
        if(num_idx < sizeof(num_buf) - 1 && ch != '\r' && ch != '\n') {
            num_buf[num_idx++] = ch;
        }
        if(ch == '\r' || ch == '\n') {
            if(num_idx > 0) {
                num_buf[num_idx] = '\0';
                // 判断是否为命令行
                if(strncmp((char*)num_buf, "CMD:", 4) == 0 && num_idx >= 5) {
                    char cmd = num_buf[4];
                    // 处理命令
                    if(cmd == 'S') collect_flag = 1;
                    if(cmd == 'E') collect_flag = 0;
                    if(cmd == 'A') {
                        current_channel = 0;
                        freq_count = 0;
                        freq_sample_flag = 0;
                        LCD_ShowString(0,0,"                ");
                        LCD_ShowString(1,0,"                ");
                    }
                    if(cmd == 'B') {
                        current_channel = 1;
                        freq_count = 0;
                        t0_count = 0;
                        freq_sample_flag = 0;
                        LCD_ShowString(0,0,"                ");
                        LCD_ShowString(1,0,"                ");
                    }
                    if(cmd == 'X'){
                        LED1 = 0;
                        UART_SendStr("TEMPER ALARM\r\n");
                    }
                    if(cmd == 'Y'){
                        LED2 = 0;
                        UART_SendStr("HUMI ALARM\r\n");
                    }
                    if(cmd == 'Z'){
                        LED3 = 0;
                        UART_SendStr("FREQ ALARM\r\n");
                    }
                    if(cmd == 'x'){
                        LED1 = 1;
                        UART_SendStr("TEMPER NORMAL\r\n");
                    }
                    if(cmd == 'y'){
                        LED2 = 1;
                        UART_SendStr("HUMI NORMAL\r\n");
                    }
                    if(cmd == 'z'){
                        LED3 = 1;
                        UART_SendStr("FREQ NORMAL\r\n");
                    }
                } else {
                    // 不是命令，检查是否包含校验和
                    check_pos = strstr((char*)num_buf, " CHECKSUM:");
                    if(check_pos) {
                        // 包含校验和的数据
                        *check_pos = '\0'; // 分离数据和校验和
                        received_checksum = atoi(check_pos + 10); // 跳过" CHECKSUM:"
                        calculated_checksum = calculate_checksum((char*)num_buf);
                        
                        if(received_checksum == calculated_checksum) {
                            // 校验和正确，处理数据
                            UART_SendStr("[DEBUG] CHECKSUM OK\r\n");
                            UART_SendStr("HALF VALUE: ");
                            UART_SendStr((char*)num_buf);
                            UART_SendStr("\r\n");
                            if(current_channel == 0) {
                                handle_half_value((char*)num_buf);
                            } else if(current_channel == 1) {
                                handle_half_freq((char*)num_buf);
                            }
                        } else {
                            // 校验和错误
                            UART_SendStr("[DEBUG] CHECKSUM ERROR\r\n");
                        }
                    } else {
                        // 不包含校验和的数据（兼容旧格式）
                        UART_SendStr("HALF VALUE: ");
                        UART_SendStr((char*)num_buf);
                        UART_SendStr("\r\n");
                        if(current_channel == 0) {
                            handle_half_value((char*)num_buf);
                        } else if(current_channel == 1) {
                            handle_half_freq((char*)num_buf);
                        }
                    }
                }
                num_idx = 0;
            }
        }
    }
}

void Timer0_ISR() interrupt 1 {
    TH0 = (65536 - 50000) / 256;
    TL0 = (65536 - 50000) % 256;
    t0_count++;
    if (t0_count >= 20) { // 20 * 50ms = 1000ms = 1s
        t0_count = 0;
        freq_sample_flag = 1; // 产生1s采样标志
    }
}

void INT0_ISR() interrupt 0 {
    freq_count++;
}

extern void Delay1000ms();
sbit FREQ_IN = P3^2;

void main() {
    // 简化局部变量，只保留必要的
    unsigned char temp, humi;
    char xdata buf[20]; // 放到xdata区
    unsigned int checksum; // 新增：校验和变量声明

    UART_SendStr("[DEBUG] UART_Init\r\n");
    UART_Init();
    UART_SendStr("[DEBUG] LCD_Init\r\n");
    LCD_Init();
    UART_SendStr("[DEBUG] Timer0_Init\r\n");
    Timer0_Init();
    UART_SendStr("[DEBUG] INT0_Init\r\n");
    INT0_Init();
    EA = 1; // 总中断使能
    UART_SendStr("[DEBUG] Init Done\r\n");
    LCD_ShowString(0,0,"WAIT CMD      ");
    while(1) {
        // --- 硬件状态控制器 ---
        // 根据软件状态，实时决定是否开启外部中断进行频率计数
        if (collect_flag && current_channel == 1) {
            EX0 = 1; // 启动采集且在频率通道时，使能外部中断
        } else {
            EX0 = 0; // 其他所有情况（停止或在温湿度通道），都关闭外部中断
        }

        if(collect_flag) {
            if(current_channel == 1) { // 555频率测量 (硬件中断计数法)
                // 轮询代码已删除，计数在后台由INT0_ISR自动完成
                if(freq_sample_flag) {
                   
                    freq_sample_flag = 0; // 清除标志，为下个周期做准备

                    EA = 0; // 关总中断，保证原子操作
                    freq_value = freq_count; // 1s内的计数值就是频率
                    freq_count = 0;          // 将脉冲计数器清零，开始新的计数周期
                    EA = 1; // 开总中断

                    LCD_ShowString(0,0,"FREQ:       Hz");
                    LCD_ShowNum(0,6,freq_value,5);
                    // 修改：添加校验和
                    sprintf(buf, "FREQ:%u", freq_value);
                    checksum = calculate_checksum(buf);
                    sprintf(buf, "FREQ:%u CHECKSUM:%u\r\n", freq_value, checksum);
                    UART_SendStr(buf);
                }
            } else if(current_channel == 0) { // DHT11温湿度
                // freq_count = 0; // 确保在DHT11模式下，频率计数器是清零的
                if (freq_sample_flag) { // 复用1秒的定时器门控
                    
                    freq_sample_flag = 0;
                    
                    EA = 0; // 关闭总中断
                    if(DHT11_Read(&temp, &humi) == 0) {
                        EA = 1; // 恢复总中断
                        LCD_ShowString(0,0,"Temp:    C");
                        LCD_ShowString(1,0,"Humi:    %");
                        LCD_ShowNum(0,6,temp,2);
                        LCD_ShowNum(1,6,humi,2);
                        // 修改：添加校验和
                        sprintf(buf, "T:%u H:%u", (unsigned int)temp, (unsigned int)humi);
                        checksum = calculate_checksum(buf);
                        sprintf(buf, "T:%u H:%u CHECKSUM:%u\r\n", (unsigned int)temp, (unsigned int)humi, checksum);
                        UART_SendStr(buf);
                    } else {
                        EA = 1; // 恢复总中断
                        UART_SendStr("[DEBUG] DHT11 FAIL\r\n");
                        LCD_ShowString(0,0,"Temp:    C");
                        LCD_ShowString(1,0,"Humi:    %");
                        LCD_ShowNum(0,6,99,2);
                        LCD_ShowNum(1,6,99,2);
                        UART_SendStr("DHT11 FAIL\r\n");
                    }
                }
            }
        } else {
            freq_count = 0; // 停止采集时，也清零频率计数器
            LCD_ShowString(0,0,"WAIT CMD      ");
            LCD_ShowString(1,0,"              ");
            Delay1000ms();
        }
        Delay100ms(); // 新增：每次主循环末尾短暂延时，降低CPU占用
    }
} 