#include <reg51.h>
#include <stdio.h>
#include "lcd1602.h"
#include "dht11.h"

sbit KEY = P3^2; // 启动/停止按键

bit collect_flag = 0; // 采集标志
volatile char last_rx = 0;
volatile bit rx_flag = 0;
char debug[17]; // 全局变量

// 新增：用于接收上位机回发的数字
char num_buf[16];
unsigned char num_idx = 0;

volatile unsigned char current_channel = 0; // 0=DHT11, 1=555频率
volatile bit freq_sample_flag = 0;
volatile unsigned char t0_count = 0;

// -- 频率测量所需的状态变量 --
volatile unsigned int freq_count = 0; // 用于累加脉冲数量
unsigned int freq_value = 0;        // 用于存放最终计算出的频率值
static bit last_p32_state = 1;      // 用于检测P3.2引脚的下降沿

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
    if(RI) {
        char ch = SBUF;
        RI = 0;
        // 判断是否为数字、空格或回车
        if((ch >= '0' && ch <= '9') || ch == ' '){
            num_buf[num_idx++] = ch;
            if(num_idx >= sizeof(num_buf)-1) num_idx = 0; // 防止溢出
        } else if(ch == '\r' || ch == '\n') {
            if(num_idx > 0) {
                num_buf[num_idx] = '\0';
                UART_SendStr("HALF VALUE: ");
                UART_SendStr(num_buf);
                UART_SendStr("\r\n");
                num_idx = 0;
            }
        } else {
            // 其他命令处理
            last_rx = ch;
            rx_flag = 1;
            // 1. Update state variables based on command
            if(last_rx == 'S') collect_flag = 1;
            if(last_rx == 'E') collect_flag = 0;
            if(last_rx == 'A') {
                current_channel = 0;
                freq_count = 0;       // 切换通道时，清零脉冲计数
                freq_sample_flag = 0; // 清除可能残留的采样标志
                LCD_ShowString(0,0,"                "); // 清空第一行
                LCD_ShowString(1,0,"                "); // 清空第二行
            }
            if(last_rx == 'B') {
                current_channel = 1;
                freq_count = 0;       // 切换通道时，清零脉冲计数
                t0_count = 0;         // 同时复位1秒定时器的中间计数
                freq_sample_flag = 0; // 清除可能残留的采样标志
                LCD_ShowString(0,0,"                "); // 清空第一行
                LCD_ShowString(1,0,"                "); // 清空第二行
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
    char buf[20];

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
                    sprintf(buf, "FREQ:%u\r\n", freq_value);
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
                        sprintf(buf, "T:%u H:%u\r\n", (unsigned int)temp, (unsigned int)humi);
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
    }
} 