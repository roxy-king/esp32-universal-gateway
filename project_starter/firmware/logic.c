/* Replace this file when adapting the project. LED demo only, no pump driver. */
#include <string.h>
#include "logic.h"
unsigned char project_led;
u16 project_remaining;
u16 project_uptime;
void project_init(void) {project_led=0;project_remaining=0;project_uptime=0;}
void project_tick(void) {
    project_uptime++;
    if(project_remaining && --project_remaining==0)project_led=0;
}
unsigned char project_apply(char *operation,u16 value) {
    if(strcmp(operation,"LED")==0) {
        if(value>1)return 2;
        project_led=(unsigned char)value;project_remaining=0;return 0;
    }
    if(strcmp(operation,"PULSE")==0) {
        if(value<1 || value>60)return 2;
        project_led=1;project_remaining=value;return 0;
    }
    if(strcmp(operation,"STOP")==0) {
        if(value!=0)return 2;
        project_led=0;project_remaining=0;return 0;
    }
    return 1;
}
