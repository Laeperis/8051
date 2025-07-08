#include <reg51.h>
#include "dht11.h"
#include <intrins.h>

sbit DHT11_IO = P1^0;
char datas[5];

void Delay40us() {
    unsigned char i;
    i = 10;
    while (--i);
}

void Delay30ms() {
    unsigned char i, j;
    i = 54;
    j = 199;
    do {
        while (--j);
    } while (--i);
}

void Delay1000ms() {
    unsigned char i, j, k;
    _nop_();
    i = 8;
    j = 1;
    k = 243;
    do {
        do {
            while (--k);
        } while (--j);
    } while (--i);
}

void DHT11_Start() {
    DHT11_IO = 1;
    DHT11_IO = 0;
    Delay30ms();
    DHT11_IO = 1;
    while(DHT11_IO);
    while(!DHT11_IO);
    while(DHT11_IO);
}

void Read_Data_From_DHT() {
    int i, j;
    char tmp, flag;
    DHT11_Start();
    for(i=0;i<5;i++){
        tmp = 0;
        for(j=0;j<8;j++){
            while(!DHT11_IO);
            Delay40us();
            if(DHT11_IO == 1){
                flag = 1;
                while(DHT11_IO);
            }else{
                flag = 0;
            }
            tmp = (tmp << 1) | flag;
        }
        datas[i] = tmp;
    }
}

unsigned char DHT11_Read(unsigned char *temp, unsigned char *humi) {
    Read_Data_From_DHT();
    if(datas[4] == (datas[0] + datas[1] + datas[2] + datas[3])) {
        *humi = datas[0];
        *temp = datas[2];
        return 0;
    } else {
        *humi = 0xFF;
        *temp = 0xFF;
        return 1;
    }
} 