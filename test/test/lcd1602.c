#include <reg51.h>
#include "lcd1602.h"

sbit RS = P2^0;
sbit RW = P2^1;
sbit E  = P2^2;
#define DataPort P0

void LCD_Delay() {
    unsigned char i = 200;
    while(i--);
}

void LCD_WriteCmd(unsigned char cmd) {
    RS = 0;
    RW = 0;
    DataPort = cmd;
    E = 1;
    LCD_Delay();
    E = 0;
    LCD_Delay();
}

void LCD_WriteData(unsigned char dat) {
    RS = 1;
    RW = 0;
    DataPort = dat;
    E = 1;
    LCD_Delay();
    E = 0;
    LCD_Delay();
}

void LCD_Init() {
    LCD_WriteCmd(0x38);
    LCD_WriteCmd(0x0C);
    LCD_WriteCmd(0x06);
    LCD_WriteCmd(0x01);
}

void LCD_ShowString(unsigned char row, unsigned char col, char *str) {
    unsigned char addr = (row == 0) ? 0x80 + col : 0xC0 + col;
    LCD_WriteCmd(addr);
    while(*str) {
        LCD_WriteData(*str++);
    }
}

void LCD_ShowNum(unsigned char row, unsigned char col, unsigned int num, unsigned char len) {
    unsigned char i;
    for(i=0;i<len;i++) {
        LCD_WriteCmd((row==0?0x80:0xC0)+col+len-1-i);
        LCD_WriteData(num%10+'0');
        num /= 10;
    }
} 