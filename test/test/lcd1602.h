#ifndef __LCD1602_H__
#define __LCD1602_H__

void LCD_Init(void);
void LCD_ShowString(unsigned char row, unsigned char col, char *str);
void LCD_ShowNum(unsigned char row, unsigned char col, unsigned char num, unsigned char len);

#endif 