#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import sys
import signal
import RPi.GPIO as GPIO
from hx711v0_5_1 import HX711

# 参数设置
DATA_PIN = 5  # HX711的DOUT引脚
CLOCK_PIN = 6  # HX711的SCK引脚
REFERENCE_UNIT = 400  # 基于测试结果的校准值
READING_INTERVAL = 0.5  # 读数间隔（秒）

# 读取模式设置
READ_MODE_INTERRUPT_BASED = "--interrupt-based"
READ_MODE_POLLING_BASED = "--polling-based"
TARE_MODE = "--tare"

# 解析命令行参数
read_mode = READ_MODE_POLLING_BASED  # 默认为轮询模式
do_tare = False  # 是否执行去皮操作

for arg in sys.argv[1:]:
    if arg == READ_MODE_INTERRUPT_BASED:
        read_mode = READ_MODE_INTERRUPT_BASED
        print("[设置] 读取模式为'中断模式'")
    elif arg == READ_MODE_POLLING_BASED:
        read_mode = READ_MODE_POLLING_BASED
        print("[设置] 读取模式为'轮询模式'")
    elif arg == TARE_MODE:
        do_tare = True
        print("[设置] 将在启动时执行去皮操作")
    else:
        print(f"[警告] 未知参数: {arg}")
        print(f"[提示] 可用参数: {READ_MODE_INTERRUPT_BASED}, {READ_MODE_POLLING_BASED}, {TARE_MODE}")

if read_mode == READ_MODE_POLLING_BASED:
    print("[设置] 读取模式为'轮询模式'")

# 初始化传感器
print("[初始化] 正在设置HX711...")
hx = HX711(DATA_PIN, CLOCK_PIN)

# 设置读取格式，如果读数不稳定，可以尝试切换LSB/MSB
hx.setReadingFormat("MSB", "MSB")

# 自动设置偏移量
print("[校准] 正在自动设置偏移量...")
print("[提示] 请确保称重盘上没有物体")
time.sleep(1)
hx.autosetOffset()
offset_value = hx.getOffset()
print(f"[校准] 偏移量设置完成，值为: {offset_value}")

# 设置参考单位
print(f"[校准] 设置参考单位为: {REFERENCE_UNIT}")
hx.setReferenceUnit(REFERENCE_UNIT)

# 执行去皮操作（如果指定）
if do_tare:
    print("[去皮] 正在进行去皮操作...")
    hx.reset()
    hx.tare()
    print("[去皮] 去皮完成，当前重量设为零点")

# 读取重量并返回千克值
def read_weight_kg():
    try:
        # 读取重量（不使用times参数）
        weight_g = hx.getWeight()
        # 转换为千克并保留3位小数
        weight_kg = round(weight_g / 1000, 3)
        return weight_kg
    except Exception as e:
        print(f"[错误] 读取重量时出错: {e}")
        return 0

# 中断模式下的回调函数
def weight_callback(raw_bytes):
    weight_kg = round(hx.rawBytesToWeight(raw_bytes) / 1000, 3)
    print(f"重量: {weight_kg} 千克")

# 信号处理函数，用于清理退出
def signal_handler(sig, frame):
    print("\n[退出] 正在清理并退出...")
    GPIO.cleanup()
    sys.exit(0)

# 注册信号处理函数
signal.signal(signal.SIGINT, signal_handler)

# 主程序
print("[就绪] 现在可以开始称重")
print("[操作] 按Ctrl+C退出程序")

# 如果使用中断模式，启用回调
if read_mode == READ_MODE_INTERRUPT_BASED:
    print("[中断] 启用中断回调...")
    hx.enableReadyCallback(weight_callback)

# 主循环
try:
    while True:
        if read_mode == READ_MODE_POLLING_BASED:
            # 轮询模式下读取重量
            weight_kg = read_weight_kg()
            print(f"重量: {weight_kg} 千克")
            # 等待一段时间再读取下一个值
            time.sleep(READING_INTERVAL)
        else:
            # 中断模式下只需等待，回调会自动处理读数
            time.sleep(1)
            
except KeyboardInterrupt:
    print("\n[退出] 正在清理并退出...")
    GPIO.cleanup()
    sys.exit(0)
except Exception as e:
    print(f"[错误] 发生异常: {e}")
    GPIO.cleanup()
    sys.exit(1) 