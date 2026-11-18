#ifndef PROJECT_LOGIC_H
#define PROJECT_LOGIC_H
typedef unsigned short u16;
extern unsigned char project_led;
extern u16 project_remaining;
extern u16 project_uptime;
void project_init(void);
void project_tick(void);
/* 0 applied, 1 unknown command, 2 invalid parameter. */
unsigned char project_apply(char *operation, u16 value);
#endif
