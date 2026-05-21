"""
POC v3 — Test multiple typing methods on CE.
"""
import time
import pyautogui
import pygetwindow as gw

print("Looking for Claude window...")
windows = gw.getWindowsWithTitle("Claude")
if not windows:
    for alt in ["Cowork", "Claude Desktop", "Claude.ai"]:
        windows = gw.getWindowsWithTitle(alt)
        if windows:
            break

if not windows:
    print("ERROR: No Claude window found!")
    for w in gw.getAllWindows():
        if w.title.strip():
            print(f"  '{w.title}'")
    exit(1)

win = windows[0]
print(f"Found: '{win.title}' at ({win.left}, {win.top}) size {win.width}x{win.height}")

try:
    if win.isMinimized:
        win.restore()
    win.activate()
    time.sleep(1)
except Exception as e:
    print(f"  Warning: {e}")

input_x = win.left + (win.width // 2)
input_y = win.top + win.height - 80

print(f"Click target: ({input_x}, {input_y})")
print("\n--- METHOD 1: pyautogui.write() (direct keystrokes) ---")
print("Clicking in 3 seconds... switch to Claude!")
time.sleep(3)

pyautogui.click(input_x, input_y)
time.sleep(0.5)
pyautogui.write("test123", interval=0.05)
time.sleep(1)

print("Did 'test123' appear? (y/n): ", end="")
r1 = input().strip().lower()

print("\n--- METHOD 2: PowerShell clipboard + ctrl+v ---")
print("Clicking in 3 seconds... switch to Claude!")
time.sleep(3)

import subprocess
subprocess.run(["powershell", "-command", "Set-Clipboard -Value 'hello-from-powershell'"], check=True)
time.sleep(0.3)

pyautogui.click(input_x, input_y)
time.sleep(0.5)
pyautogui.hotkey("ctrl", "v")
time.sleep(1)

print("Did 'hello-from-powershell' appear? (y/n): ", end="")
r2 = input().strip().lower()

print("\n--- METHOD 3: win32 clipboard + ctrl+v ---")
print("Clicking in 3 seconds... switch to Claude!")
time.sleep(3)

try:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    text = "hello-from-win32"

    user32.OpenClipboard(0)
    user32.EmptyClipboard()

    hMem = kernel32.GlobalAlloc(GMEM_MOVEABLE, (len(text) + 1) * 2)
    pMem = kernel32.GlobalLock(hMem)
    ctypes.cdll.msvcrt.wcscpy_s(ctypes.c_wchar_p(pMem), len(text) + 1, text)
    kernel32.GlobalUnlock(hMem)
    user32.SetClipboardData(CF_UNICODETEXT, hMem)
    user32.CloseClipboard()

    pyautogui.click(input_x, input_y)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1)

    print("Did 'hello-from-win32' appear? (y/n): ", end="")
    r3 = input().strip().lower()
except Exception as e:
    r3 = "error"
    print(f"  Error: {e}")

print(f"\nResults: method1={r1} method2={r2} method3={r3}")
print("Report these back to CL!")
