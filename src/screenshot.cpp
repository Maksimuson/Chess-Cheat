#include <windows.h>
#include <gdiplus.h>
#include "screenshot.h"

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")

using namespace Gdiplus;

static const int BTN_W = 60;
static const int BTN_H = 60;
static bool g_hovered = false;

bool SaveScreenBmp(const wchar_t* filePath)
{
    HDC hScreenDC = GetDC(NULL);
    HDC hMemoryDC = CreateCompatibleDC(hScreenDC);

    int width = GetSystemMetrics(SM_CXSCREEN);
    int height = GetSystemMetrics(SM_CYSCREEN);

    HBITMAP hBitmap = CreateCompatibleBitmap(hScreenDC, width, height);
    HBITMAP hOldBitmap = (HBITMAP)SelectObject(hMemoryDC, hBitmap);

    BitBlt(hMemoryDC, 0, 0, width, height, hScreenDC, 0, 0, SRCCOPY | CAPTUREBLT);

    // Deselect the bitmap before GetDIBits
    SelectObject(hMemoryDC, hOldBitmap);

    BITMAPFILEHEADER bfHeader = {};
    BITMAPINFOHEADER biHeader = {};

    biHeader.biSize = sizeof(BITMAPINFOHEADER);
    biHeader.biHeight = height;
    biHeader.biWidth = width;
    biHeader.biPlanes = 1;
    biHeader.biBitCount = 24;
    biHeader.biCompression = BI_RGB;

    DWORD dwBmpSize = ((width * biHeader.biBitCount + 31) / 32) * 4 * height;

    HANDLE hDIB = GlobalAlloc(GHND, dwBmpSize);
    char* lpbitmap = (char*)GlobalLock(hDIB);

    GetDIBits(hScreenDC, hBitmap, 0, (UINT)height, lpbitmap, (BITMAPINFO*)&biHeader, DIB_RGB_COLORS);

    HANDLE hFile = CreateFileW(filePath, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE)
    {
        GlobalUnlock(hDIB);
        GlobalFree(hDIB);
        DeleteObject(hBitmap);
        DeleteDC(hMemoryDC);
        ReleaseDC(NULL, hScreenDC);
        return false;
    }

    DWORD dwSizeHeader = sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER);
    bfHeader.bfType = 0x4D42; // "BM"
    bfHeader.bfSize = dwSizeHeader + dwBmpSize;
    bfHeader.bfOffBits = dwSizeHeader;

    DWORD dwWritten = 0;
    WriteFile(hFile, &bfHeader, sizeof(BITMAPFILEHEADER), &dwWritten, NULL);
    WriteFile(hFile, &biHeader, sizeof(BITMAPINFOHEADER), &dwWritten, NULL);
    WriteFile(hFile, lpbitmap, dwBmpSize, &dwWritten, NULL);

    CloseHandle(hFile);
    GlobalUnlock(hDIB);
    GlobalFree(hDIB);
    DeleteObject(hBitmap);
    DeleteDC(hMemoryDC);
    ReleaseDC(NULL, hScreenDC);

    return true;
}

static void DrawButton(HDC hdc, bool hovered)
{
    Graphics graphics(hdc);
    graphics.SetSmoothingMode(SmoothingModeAntiAlias);

    Color bgColor = hovered ? Color(230, 60, 60, 60) : Color(200, 30, 30, 30);
    SolidBrush brush(bgColor);
    graphics.FillEllipse(&brush, 2, 2, BTN_W - 4, BTN_H - 4);

    Pen pen(Color(255, 255, 255, 255), 2);
    graphics.DrawEllipse(&pen, 2, 2, BTN_W - 4, BTN_H - 4);

    // Simple camera icon: body + lens
    SolidBrush iconBrush(Color(255, 255, 255, 255));
    graphics.FillRectangle(&iconBrush, BTN_W / 2 - 14, BTN_H / 2 - 8, 28, 18);
    SolidBrush lensBrush(Color(255, 30, 30, 30));
    graphics.FillEllipse(&lensBrush, BTN_W / 2 - 6, BTN_H / 2 - 4, 12, 12);
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    switch (msg)
    {
    case WM_PAINT:
    {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);

        HDC memDC = CreateCompatibleDC(hdc);
        HBITMAP memBmp = CreateCompatibleBitmap(hdc, BTN_W, BTN_H);
        HBITMAP oldBmp = (HBITMAP)SelectObject(memDC, memBmp);

        RECT rc = { 0, 0, BTN_W, BTN_H };
        FillRect(memDC, &rc, (HBRUSH)GetStockObject(BLACK_BRUSH)); // black = transparent (color key)
        DrawButton(memDC, g_hovered);

        BitBlt(hdc, 0, 0, BTN_W, BTN_H, memDC, 0, 0, SRCCOPY);
        SelectObject(memDC, oldBmp);
        DeleteObject(memBmp);
        DeleteDC(memDC);

        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_LBUTTONUP:
    {
        // Hide the button so it does not appear in the screenshot
        ShowWindow(hwnd, SW_HIDE);
        Sleep(150);
        bool ok = SaveScreenBmp(L"C:\\Users\\shagm\\OneDrive\\Рабочий стол\\Chess cheat\\screenshots\\shot.bmp"); 
        ShowWindow(hwnd, SW_SHOW);

        MessageBeep(ok ? MB_OK : MB_ICONERROR);
        return 0;
    }

    case WM_RBUTTONUP:
        DestroyWindow(hwnd); // right click closes the button
        return 0;

    case WM_MOUSEMOVE:
    {
        if (!g_hovered)
        {
            g_hovered = true;
            InvalidateRect(hwnd, NULL, FALSE);

            TRACKMOUSEEVENT tme = { sizeof(tme) };
            tme.dwFlags = TME_LEAVE;
            tme.hwndTrack = hwnd;
            TrackMouseEvent(&tme);
        }
        return 0;
    }

    case WM_MOUSELEAVE:
        g_hovered = false;
        InvalidateRect(hwnd, NULL, FALSE);
        return 0;

    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);
}

int RunOverlay()
{
    SetProcessDPIAware(); // capture the real screen resolution on scaled displays

    HINSTANCE hInstance = GetModuleHandleW(NULL);

    GdiplusStartupInput gdiplusStartupInput;
    ULONG_PTR gdiplusToken;
    GdiplusStartup(&gdiplusToken, &gdiplusStartupInput, NULL);

    WNDCLASSW wc = {};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = L"OverlayButtonClass";
    wc.hCursor = LoadCursor(NULL, IDC_HAND);
    RegisterClassW(&wc);

    // Always on top, no taskbar entry, black pixels are transparent
    HWND hwnd = CreateWindowExW(
        WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"OverlayButtonClass", L"",
        WS_POPUP,
        20, 20, BTN_W, BTN_H,
        NULL, NULL, hInstance, NULL);

    if (!hwnd)
    {
        GdiplusShutdown(gdiplusToken);
        return 1;
    }

    SetLayeredWindowAttributes(hwnd, RGB(0, 0, 0), 255, LWA_COLORKEY);

    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0))
    {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    GdiplusShutdown(gdiplusToken);
    return (int)msg.wParam;
}