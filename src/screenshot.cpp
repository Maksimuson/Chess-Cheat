#include <windows.h>
#include <shlobj.h>
#include <gdiplus.h>
#include <string>
#include "screenshot.h"

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "uuid.lib")

using namespace Gdiplus;

static const int BTN_W = 60;
static const int BTN_H = 60;
static bool g_hovered = false;
static bool g_busy = false;   // Python is working, ignore clicks

static const UINT WM_BOARD_READY = WM_APP + 1;
static std::wstring g_root;
static std::wstring g_shotPath;
static std::wstring g_scriptPath;

static void InitPaths()
{
    PWSTR desktop = NULL;
    if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_Desktop, 0, NULL, &desktop)))
    {
        g_root = std::wstring(desktop) + L"\\Chess cheat";
        CoTaskMemFree(desktop);
    }
    CreateDirectoryW((g_root + L"\\screenshots").c_str(), NULL);
    g_shotPath = g_root + L"\\screenshots\\shot.bmp";
    g_scriptPath = g_root + L"\\src\\board_reader.py";
}

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

// ---------------------------------------------------------------------------
// Run "python board_reader.py shot.bmp" without a console window and return
// everything it prints (the 8x8 matrix, or an error text).
// ---------------------------------------------------------------------------
static std::string RunPython(const std::wstring& script, const std::wstring& shot)
{
    SECURITY_ATTRIBUTES sa = {};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE hRead = NULL, hWrite = NULL;
    if (!CreatePipe(&hRead, &hWrite, &sa, 0))
        return "ERROR: CreatePipe failed";
    SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si = {};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = hWrite;
    si.hStdError = hWrite;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);

    PROCESS_INFORMATION pi = {};
    std::wstring cmd = L"python \"" + script + L"\" move w \"" + shot + L"\"";
    std::wstring workDir = script.substr(0, script.find_last_of(L'\\'));

    BOOL started = CreateProcessW(NULL, &cmd[0], NULL, NULL, TRUE, CREATE_NO_WINDOW,
        NULL, workDir.c_str(), &si, &pi);
    CloseHandle(hWrite); // our copy of the write end; the child keeps its own
    if (!started)
    {
        CloseHandle(hRead);
        return "ERROR: cannot start python. Is Python in PATH? Does the script exist?\n" +
            std::string("(check g_scriptPath in InitPaths)");
    }

    std::string out;
    char buf[4096]; // Allocate a 4 KB buffer to read data in chunks from the channel
    DWORD n = 0;
    while (ReadFile(hRead, buf, sizeof(buf), &n, NULL) && n > 0)
        out.append(buf, n);

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    CloseHandle(hRead);

    if (code != 0)
        out = "ERROR (python exit code " + std::to_string(code) + "):\n" + out;
    return out;
}

static DWORD WINAPI Worker(LPVOID param)
{
    HWND hwnd = (HWND)param;
    std::string* result = new std::string(RunPython(g_scriptPath, g_shotPath));
    PostMessageW(hwnd, WM_BOARD_READY, 0, (LPARAM)result); // handled on the UI thread
    return 0;
}


// Declaration of a static function, `Utf8ToWide`, which takes a UTF-8 string and returns a UTF-16 wide string
static std::wstring Utf8ToWide(const std::string& s)
{
    if (s.empty())
        return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), NULL, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &w[0], n);
    return w;
}

// ---------------------------------------------------------------------------
// Called on the UI thread when Python has finished.
// `result` is the text printed by board_reader.py.
// ---------------------------------------------------------------------------
static void OnBoardReady(HWND hwnd, const std::string& result)
{
    // Display a pop-up window with the title “Board,” the text “result” converted from UTF-8 to UTF-16, an OK button, and the window displayed on top of all other windows
    MessageBeep(result.compare(0, 5, "ERROR") == 0 ? MB_ICONERROR : MB_OK);
    MessageBoxW(hwnd, Utf8ToWide(result).c_str(), L"Board",
        MB_OK | MB_TOPMOST | MB_SETFOREGROUND);
}


static void DrawButton(HDC hdc, bool hovered, bool busy)
{
    Graphics graphics(hdc);
    graphics.SetSmoothingMode(SmoothingModeAntiAlias);

    Color bgColor = busy ? Color(230, 20, 80, 150)
        : (hovered ? Color(230, 60, 60, 60) : Color(200, 30, 30, 30));
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
    case WM_PAINT: // Handling the WM_PAINT message to redraw the window's contents
    {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);

        HDC memDC = CreateCompatibleDC(hdc);
        HBITMAP memBmp = CreateCompatibleBitmap(hdc, BTN_W, BTN_H);
        HBITMAP oldBmp = (HBITMAP)SelectObject(memDC, memBmp);

        RECT rc = { 0, 0, BTN_W, BTN_H };
        FillRect(memDC, &rc, (HBRUSH)GetStockObject(BLACK_BRUSH)); // black = transparent (color key)
        DrawButton(memDC, g_hovered, g_busy);

        BitBlt(hdc, 0, 0, BTN_W, BTN_H, memDC, 0, 0, SRCCOPY);
        SelectObject(memDC, oldBmp);
        DeleteObject(memBmp);
        DeleteDC(memDC);

        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_LBUTTONUP: // Handle the left-mouse-button release event (click)
    {
        if (g_busy)
            return 0;
        g_busy = true;

        // Hide the button so it does not appear in the screenshot
        ShowWindow(hwnd, SW_HIDE);
        Sleep(150);
        bool ok = SaveScreenBmp(g_shotPath.c_str());
        ShowWindow(hwnd, SW_SHOW);

        if (!ok)
        {
            g_busy = false;
            MessageBeep(MB_ICONERROR);
            return 0;
        }

        InvalidateRect(hwnd, NULL, FALSE); // show the "busy" color
        HANDLE hThread = CreateThread(NULL, 0, Worker, hwnd, 0, NULL);
        if (hThread)
            CloseHandle(hThread);
        else
            g_busy = false;
        return 0;
    }

    case WM_BOARD_READY:  // Handle the user notification that the results are ready from the background thread
    {
        std::string* result = (std::string*)lParam;
        g_busy = false;
        InvalidateRect(hwnd, NULL, FALSE);
        OnBoardReady(hwnd, *result);
        delete result;
        return 0;
    }

    case WM_RBUTTONUP:  // Handling the right-click event
        DestroyWindow(hwnd); // right click destroy the button
        return 0;

    case WM_MOUSEMOVE:  // Handling mouse cursor movement over the window
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

    case WM_MOUSELEAVE:  // Handle the event that occurs when the mouse cursor moves outside the window
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
    InitPaths();

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