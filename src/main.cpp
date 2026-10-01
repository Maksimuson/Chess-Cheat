#pragma comment(linker, "/SUBSYSTEM:WINDOWS")
#pragma comment(linker, "/ENTRY:mainCRTStartup")
#include <windows.h>
#include "screenshot.h"

int main()
{
    return RunOverlay();
}