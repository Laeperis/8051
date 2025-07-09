#include <reg51.h>
#include <stdio.h>
#include "lcd1602.h"
#include "dht11.h"

sbit KEY = P3^2; // 启动/停止按键

bit collect_flag = 0; // 采集标志
volatile char last_rx = 0;
volatile bit rx_flag = 0;
char debug[17]; // 全局变量

volatile unsigned char current_channel = 0; // 0=DHT11, 1=555频率
volatile bit freq_sample_flag = 0;
volatile unsigned char t0_count = 0;
volatile unsigned int freq_count = 0; // 中断计数值
unsigned int freq_value = 0;        // 主循环读取值

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
    // EX0 = 1; // 不再默认使能INT0
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
        last_rx = SBUF;
        rx_flag = 1;
        RI = 0;

        // 1. Update state variables based on command
        if(last_rx == 'S') collect_flag = 1;
        if(last_rx == 'E') collect_flag = 0;
        if(last_rx == 'A') {
            current_channel = 0;
            LCD_ShowString(0,0,"                "); // 清空第一行
            LCD_ShowString(1,0,"                "); // 清空第二行
        }
        if(last_rx == 'B') {
            current_channel = 1;
            LCD_ShowString(0,0,"                "); // 清空第一行
            LCD_ShowString(1,0,"                "); // 清空第二行
        }

        // 2. Set hardware state based on current system state
        if(collect_flag && current_channel == 1) {
            // Only enable interrupt if collecting AND in frequency mode
            EX0 = 1;
        } else {
            // In all other cases (stopped OR in temp mode), disable it.
            EX0 = 0;
        }
    }
}

void Timer0_ISR() interrupt 1 {
    TH0 = (65536 - 50000) / 256;
    TL0 = (65536 - 50000) % 256;
    t0_count++;
    if (t0_count >= 2) { // 2*50ms=100ms
        t0_count = 0;
        freq_sample_flag = 1; // 产生100ms采样标志
    }
}

extern void Delay1000ms();
sbit FREQ_IN = P3^2;

void main() {
    static unsigned char last_mode = 0xFF; // 不可能的初值，保证首次切换
    unsigned char temp, humi;
    char buf[20];
    unsigned int count;
    unsigned int freq_value = 0;
    unsigned int pulse_count;
    unsigned long i;
    bit last_p32_state;

    UART_SendStr("[DEBUG] UART_Init\r\n");
    UART_Init();
    UART_SendStr("[DEBUG] LCD_Init\r\n");
    LCD_Init();
    UART_SendStr("[DEBUG] Timer0_Init\r\n");
    Timer0_Init();
    EA = 1; // 总中断使能
    EX0 = 0; // 默认关闭外部中断0
    UART_SendStr("[DEBUG] Init Done\r\n");
    LCD_ShowString(0,0,"WAIT CMD      ");
    while(1) {
        if(collect_flag) {
            if(current_channel == 1) { // 555频率测量 (手动轮询)
                if(freq_sample_flag) {
                    freq_sample_flag = 0;
                    pulse_count = 0;
                    last_p32_state = FREQ_IN;
                    // 在100ms内进行轮询检测
                    for(i=0; i<30000; i++) { // 这是一个粗略的延时
                        if(last_p32_state == 1 && FREQ_IN == 0) {
                            pulse_count++;
                        }
                        last_p32_state = FREQ_IN;
                    }
                    freq_value = pulse_count * 10; // 100ms的计数值*10=1s的频率
                    LCD_ShowString(0,0,"FREQ:      Hz");
                    LCD_ShowNum(0,5,freq_value,5);
                    sprintf(buf, "FREQ:%u\r\n", freq_value);
                    UART_SendStr(buf);
                }
            } else if(current_channel == 0) { // DHT11温湿度
                Delay1000ms(); // 每次读取之间必须有延时
                EA = 0; // 关闭总中断
                if(DHT11_Read(&temp, &humi) == 0) {
                    EA = 1; // 恢复总中断
                    UART_SendStr("[DEBUG] DHT11 OK\r\n");
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
        } else {
            LCD_ShowString(0,0,"WAIT CMD      ");
            LCD_ShowString(1,0,"              ");
            Delay1000ms();
        }
    }
} 