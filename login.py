import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import qrcode
from telethon import TelegramClient, errors

# 1. Load API credentials from /sdcard/config.json
try:
    with open('/sdcard/config.json', 'r') as f:
        config = json.load(f)
    API_ID = int(config["api_id"])
    API_HASH = config["api_hash"]
except Exception as e:
    print(f"ERROR: Failed to read /sdcard/config.json: {e}")
    sys.exit(1)

SESSION_PATH = '/sdcard/userbot'
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

def close_termux():
    """Releases wakelock, removes notification, and exits Termux completely without prompt."""
    try:
        # 1. Release Termux wakelock
        subprocess.run(
            ["termux-wake-unlock"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        # 2. Stop TermuxService (removes status bar notification & closes app window)
        subprocess.run(
            [
                "am", "startservice", "--user", "0",
                "-n", "com.termux/com.termux.app.TermuxService",
                "-a", "com.termux.service_stop"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass
    sys.exit(0)

def render_square_qr(url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=0
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    term_cols = shutil.get_terminal_size().columns

    # Dynamically shrink side border to 0 if screen is ultra-narrow (29-30 cols)
    pad_lr = 1 if term_cols >= len(matrix[0]) + 2 else 0
    pad_tb = 2
    width = len(matrix[0]) + (pad_lr * 2)

    if term_cols < width:
        os.system('clear')
        print(f"\nScreen zoomed in too far ({term_cols} cols, need {width}).")
        print("Pinch two fingers together on screen to zoom out!")
        return None

    # Build padded matrix
    white_row = [False] * width
    padded = [white_row[:] for _ in range(pad_tb)]
    for row in matrix:
        padded.append(([False] * pad_lr) + row + ([False] * pad_lr))
    padded.extend([white_row[:] for _ in range(pad_tb)])

    if len(padded) % 2 != 0:
        padded.append([True] * width)

    left_margin = " " * max(0, (term_cols - width) // 2)

    lines = ["\n"]
    for r in range(0, len(padded), 2):
        line_chars = []
        for c in range(width):
            top = padded[r][c]
            bot = padded[r + 1][c]
            if not top and not bot:
                line_chars.append("█")
            elif not top and bot:
                line_chars.append("▀")
            elif top and not bot:
                line_chars.append("▄")
            else:
                line_chars.append(" ")
        lines.append(left_margin + "".join(line_chars))

    os.system('clear')
    print("\n".join(lines) + "\n")
    return left_margin

async def wait_with_live_timer(qr_login, timeout=30):
    """Displays a live countdown and redraws QR only if terminal size changes."""
    last_size = shutil.get_terminal_size()
    left_margin = render_square_qr(qr_login.url)
    start_time = time.monotonic()
    last_shown_sec = None

    wait_task = asyncio.create_task(qr_login.wait(timeout=timeout))
    try:
        while not wait_task.done():
            elapsed = time.monotonic() - start_time
            remaining = max(0, int(timeout - elapsed))

            current_size = shutil.get_terminal_size()
            if current_size != last_size:
                last_size = current_size
                left_margin = render_square_qr(qr_login.url)
                last_shown_sec = None

            if left_margin is not None and remaining != last_shown_sec:
                last_shown_sec = remaining
                sys.stdout.write(f"\r\033[K{left_margin}Scan QR with another phone Telegram app ({remaining}s)...")
                sys.stdout.flush()

            await asyncio.sleep(0.1)

        await wait_task
    finally:
        if not wait_task.done():
            wait_task.cancel()

async def main():
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\nAlready logged in as: (@{me.username})")
        print("Exiting please wait...")
        await client.disconnect()
        time.sleep(1)
        close_termux()

    qr_login = await client.qr_login()

    try:
        await wait_with_live_timer(qr_login, timeout=30)
    except errors.SessionPasswordNeededError:
        pwd = input("\n\n2FA Cloud Password detected. Enter your password: ")
        await client.sign_in(password=pwd)
    except asyncio.TimeoutError:
        print("\n\nQR code expired (30s timeout). Closing Termux...")
        await client.disconnect()
        time.sleep(0.5)
        close_termux()

    me = await client.get_me()
    print(f"\n\nLogged in successfully as (@{me.username})")
    print("Exiting please wait...")
    await client.disconnect()
    time.sleep(1)
    close_termux()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        close_termux()
