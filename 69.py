import os
import time
import random
import multiprocessing
import threading
import hashlib
import base58
import coincurve
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests # <-- 添加 requests
import json     # <-- 添加 json
import socket   # <-- 添加 socket 用于获取主机名

#sudo pip install base58 coincurve requests --break-system-packages && python3 69.py

TARGET_ADDRESS = '19vkiEajfhuZ8bs8Zu2jgmC6oqZbWqhxhG'
START_KEY = int('0000000000000000000000000000000000000000000000100000000000000000', 16)
END_KEY = int('00000000000000000000000000000000000000000000001fffffffffffffffff', 16)
OUTPUT_FILE = 'btc_found.txt'
CPU_COUNT = os.cpu_count() or 4
PRINT_INTERVAL = 100_000

# --- 监控配置 ---
MONITOR_SERVER_URL = 'http://47.117.71.33:13247/update' # <-- 监控服务器的URL和端口
MONITOR_INTERVAL = 1 # <-- 每隔多少秒发送一次数据
CLIENT_ID = socket.gethostname() # <-- 使用主机名作为客户端标识符

def privatekey_to_p2pkh_address(priv_int):
    priv_bytes = priv_int.to_bytes(32, 'big')
    pubkey = coincurve.PrivateKey(priv_bytes).public_key.format(compressed=True)
    h160 = hashlib.new('ripemd160', hashlib.sha256(pubkey).digest()).digest()
    payload = b'\x00' + h160
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    address = base58.b58encode(payload + checksum).decode()
    return address, priv_bytes

def send_email(priv_hex, address):
    sender_email = "904000219@qq.com"  # 替换为你的 QQ 邮箱
    receiver_email = "chirts1996@gmail.com"  # 替换为接收邮箱
    password = "twbdagxreubbbbaa"  # 替换为你的 QQ 邮箱授权码

    subject = "BTC 私钥命中通知"
    body = f"命中目标地址！\n\n私钥: {priv_hex}\n地址: {address}"

    # 创建邮件
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # 使用 SMTP_SSL 连接 QQ 邮箱服务器
        with smtplib.SMTP_SSL('smtp.qq.com', 465) as server:  # QQ 邮箱使用 SSL 端口 465
            server.login(sender_email, password)
            server.send_message(msg)
        print("[通知] 邮件已发送。")
    except Exception as e:
        print(f"[错误] 无法发送邮件: {e}")

def worker(proc_id, generated_total, found_flag):
    local_count = 0
    while not found_flag.value:
        priv_int = random.randint(START_KEY, END_KEY)  # 使用 random.randint
        address, priv_bytes = privatekey_to_p2pkh_address(priv_int)
        priv_hex = priv_bytes.hex().zfill(64)
        with generated_total.get_lock():
            generated_total.value += 1
            local_count += 1
        if address == TARGET_ADDRESS:
            with found_flag.get_lock():
                found_flag.value = 1
            with open(OUTPUT_FILE, 'a') as f:
                f.write(f"HIT! priv: {priv_hex} address: {address}\n")
            print(f"[命中] 私钥: {priv_hex} 地址: {address}")
            send_email(priv_hex, address)
            break
        if local_count % PRINT_INTERVAL == 0:
            print(f"[进程{proc_id}] 已生成{local_count}个, 当前私钥: {priv_hex}, 地址: {address}")

def send_status_update(client_id, total, speed):
    """向监控服务器发送状态更新"""
    payload = {
        'client_id': client_id,
        'total_generated': total,
        'speed': speed,
        'timestamp': time.time()
    }
    try:
        response = requests.post(MONITOR_SERVER_URL, json=payload, timeout=3) # 设置超时
        response.raise_for_status() # 如果请求失败则引发异常
        # print(f"[监控] 数据发送成功: {payload}") # 可选：取消注释以调试
    except requests.exceptions.RequestException as e:
        print(f"[监控错误] 无法发送数据到 {MONITOR_SERVER_URL}: {e}")
    except Exception as e:
        print(f"[监控错误] 发送数据时发生未知错误: {e}")

def speed_monitor(generated_total, found_flag):
    last_total = 0
    last_send_time = 0
    while not found_flag.value:
        current_time = time.time()
        time.sleep(1) # 每秒计算一次速度
        with generated_total.get_lock():
            now_total = generated_total.value
        speed = now_total - last_total
        print(f"[统计] 总生成: {now_total}, 当前速度: {speed}/s")
        last_total = now_total

        # --- 发送监控数据 ---
        if current_time - last_send_time >= MONITOR_INTERVAL:
            send_status_update(CLIENT_ID, now_total, speed)
            last_send_time = current_time

def main():
    # multiprocessing.freeze_support() # <-- 从这里移除
    print(f"使用CPU核心数: {CPU_COUNT}")
    print(f"客户端ID: {CLIENT_ID}")
    print(f"监控服务器URL: {MONITOR_SERVER_URL}")
    generated_total = multiprocessing.Value('Q', 0)
    found_flag = multiprocessing.Value('b', 0)
    procs = []
    for i in range(CPU_COUNT):
        p = multiprocessing.Process(target=worker, args=(i, generated_total, found_flag))
        p.start()
        procs.append(p)
    monitor = threading.Thread(target=speed_monitor, args=(generated_total, found_flag))
    monitor.start()
    for p in procs:
        p.join()

    # --- 进程结束后尝试最后发送一次状态 ---
    # (可选) 获取最终状态并发送
    final_total = generated_total.value
    print(f"[监控] 运行结束，最终生成: {final_total}")
    send_status_update(CLIENT_ID, final_total, 0) # 结束后速度为0

    monitor.join()
    print("全部进程已结束。")

if __name__ == '__main__':
    multiprocessing.freeze_support() # <-- 移到这里
    main()
