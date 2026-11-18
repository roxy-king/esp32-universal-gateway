/* CT107D / IAP15F2K61S2, UART1 RX=P3.6 TX=P3.7, 9600 8N1.
 * Compile with Keil C51. No dynamic memory, no blocking delays in business logic.
 * P1,C,bench,0123abcd,PULSE,5\r\n -> P1,A,bench,0123abcd,OK,applied
 */
#include <REG52.H>
#include <string.h>
#include "project_config.h"
#include "logic.h"
#ifndef SYSTEM_CLOCK
#define SYSTEM_CLOCK PROJECT_CLOCK
#endif
#define T0_RELOAD (65536UL-((SYSTEM_CLOCK+6000UL)/12000UL))
#define UART_RELOAD (65536UL-(SYSTEM_CLOCK/4UL/PROJECT_BAUD))
sfr AUXR=0x8E;
sfr T2H=0xD6;
sfr T2L=0xD7;
sfr P_SW1=0xA2;
static volatile char xdata rx[96];
static char xdata line[96];
static volatile unsigned char rx_len;
static volatile bit rx_ready,rx_drop,tx_done;
static volatile u16 ticks;
static volatile unsigned char seconds_due;
static char xdata ids[8][9];
static char xdata ops[8][17];
static u16 xdata values[8];
static unsigned char xdata results[8];
static unsigned char cache_at;

static void latch(unsigned char address,unsigned char value) {
    P0=value;P2=(P2&0x1F)|address;P2&=0x1F;
}
static void tx_byte(unsigned char v) {tx_done=0;SBUF=v;while(!tx_done);}
static void text(char *s) {while(*s)tx_byte(*s++);}
static void number(u16 v) {
    char digits[5];unsigned char i=0;
    do {digits[i++]=(char)('0'+v%10);v/=10;}while(v);
    while(i)tx_byte(digits[--i]);
}
static void state(void) {
    text("P1,S," PROJECT_ID ",led=");number(project_led);
    text(";remaining=");number(project_remaining);
    text(";uptime=");number(project_uptime);text("\r\n");
}
static void ack(char *id,unsigned char result) {
    text("P1,A," PROJECT_ID ",");text(id);
    if(result==0)text(",OK,applied\r\n");
    else if(result==1)text(",ERR,unknown_command\r\n");
    else if(result==2)text(",ERR,out_of_range\r\n");
    else text(",ERR,id_conflict\r\n");
}
static bit valid_id(char *s) {
    unsigned char i;
    if(strlen(s)!=8)return 0;
    for(i=0;i<8;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return 1;
}
static void command(void) {
    char *parts[6];unsigned char n=1,i,result;u16 value=0;char *p;
    parts[0]=line;
    for(p=line;*p;p++)if(*p==',') {if(n>=6)return;*p=0;parts[n++]=p+1;}
    if(n!=6||strcmp(parts[0],"P1")||strcmp(parts[1],"C")||strcmp(parts[2],PROJECT_ID)||!valid_id(parts[3]))return;
    if(strlen(parts[4])<1||strlen(parts[4])>16||strlen(parts[5])<1||strlen(parts[5])>5){ack(parts[3],2);return;}
    for(p=parts[5];*p;p++) {
        if(*p<'0'||*p>'9'||value>6553||(value==6553&&*p>'5')){ack(parts[3],2);return;}
        value=value*10+(*p-'0');
    }
    for(i=0;i<8;i++)if(strcmp(ids[i],parts[3])==0) {
        if(strcmp(ops[i],parts[4])||values[i]!=value)ack(parts[3],3);
        else ack(parts[3],results[i]);
        return;
    }
    result=project_apply(parts[4],value);
    latch(0x80,project_led?0xFE:0xFF);
    strcpy(ids[cache_at],parts[3]);strcpy(ops[cache_at],parts[4]);values[cache_at]=value;results[cache_at]=result;cache_at=(cache_at+1)&7;
    ack(parts[3],result);state();
}
void timer0_isr(void) interrupt 1 using 1 {
    TH0=(unsigned char)(T0_RELOAD>>8);TL0=(unsigned char)T0_RELOAD;
    if(++ticks>=1000){ticks=0;if(seconds_due<255)seconds_due++;}
}
void uart_isr(void) interrupt 4 using 2 {
    unsigned char c;
    if(TI){TI=0;tx_done=1;}
    if(RI){RI=0;c=SBUF;
        if(!rx_ready){
            if(c=='\n'){
                if(!rx_drop&&rx_len){rx[rx_len]=0;rx_ready=1;}
                else rx_len=0;
                rx_drop=0;
            }else if(c!='\r'){
                if(c<32||c>126||rx_len>=95)rx_drop=1;
                if(!rx_drop)rx[rx_len++]=c;
            }
        }
    }
}
void main(void) {
    unsigned char pending;
    EA=0;project_init();
    latch(0xA0,0);latch(0x80,0xFF);latch(0xC0,0);latch(0xE0,0xFF);
    P_SW1=(P_SW1&0x3F)|0x40;P3|=0xC0;SCON=0x50;
    T2H=(unsigned char)(UART_RELOAD>>8);T2L=(unsigned char)UART_RELOAD;AUXR|=0x15;TI=0;ES=1;
    AUXR&=0x7F;TMOD=(TMOD&0xF0)|1;TH0=(unsigned char)(T0_RELOAD>>8);TL0=(unsigned char)T0_RELOAD;ET0=1;TR0=1;EA=1;
    state();
    while(1){
        if(rx_ready){ES=0;strcpy(line,(char *)rx);rx_len=0;rx_ready=0;ES=1;command();}
        EA=0;pending=seconds_due;seconds_due=0;EA=1;
        if(pending){while(pending--)project_tick();latch(0x80,project_led?0xFE:0xFF);state();}
    }
}
