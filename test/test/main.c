#include <reg51.h>
#include <stdio.h>
#include "lcd1602.h"
#include "dht11.h"

sbit KEY = P3^2; // 启动/停止按键

bit collect_flag = 0; // 采集标志

volatile char last_rx = 0;
volatile bit rx_flag = 0;
char debug[17]; // 全局变量

void UART_Init() {
    SCON = 0x50;      // 8位数据,可变波特率
    TMOD |= 0x20;     // 定时器1，8位自动重装
    TH1 = 0xFD;       // 9600波特率
    TL1 = 0xFD;
    TR1 = 1;
    ES = 1;
    EA = 1;
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
        if(last_rx == 'S') collect_flag = 1; // 启动
        if(last_rx == 'E') collect_flag = 0; // 停止
    }
}

extern void Delay1000ms();

void main() {
    unsigned char temp, humi;
    char buf[20];
    UART_Init();
    LCD_Init();
    UART_SendStr("Init OK\r\n");
    Delay1000ms();
    Delay1000ms();
    LCD_ShowString(0,0,"Temp:    C");
    LCD_ShowString(1,0,"Humi:    %");
    UART_SendStr("Wait for collect_flag...\r\n");
    while(1) {
        if(rx_flag) {
            sprintf(debug, "RX:%02X %c       ", last_rx, last_rx);
            UART_SendStr("RX: ");
            UART_SendStr(debug);
            UART_SendStr("\r\n");
            rx_flag = 0;
        }
        if(collect_flag) {
            UART_SendStr("Collecting...\r\n");
            UART_SendStr("Before DHT11\r\n");
            Delay1000ms(); // 采集前延时，保证DHT11稳定
            if(DHT11_Read(&temp, &humi) == 0) {
                LCD_ShowNum(0,6,temp,2);
                LCD_ShowNum(1,6,humi,2);
                UART_SendStr("DHT11 OK\r\n");
                sprintf(buf, "T:%u H:%u\r\n", (unsigned int)temp, (unsigned int)humi);
                UART_SendStr(buf);
            } else {
                LCD_ShowNum(0,6,99,2);
                LCD_ShowNum(1,6,99,2);
                UART_SendStr("DHT11 FAIL\r\n");
            }
            UART_SendStr("After DHT11\r\n");
            Delay1000ms(); // 1秒采集一次
        }
    }
} 