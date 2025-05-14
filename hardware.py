# hardware.py

import time
import sys
import signal
import math
import smbus
import board
import adafruit_dht
import RPi.GPIO as GPIO
from hx711v0_5_1 import HX711  # 确保 hx711v0_5_1.py 在同一目录或 Python 路径中

# --- 全局变量和配置 ---
# DHT11
DHT_PIN = board.D17  # DHT11 数据引脚 (BCM 17)
dht_sensor = None

# HX711 (Weight Sensor)
WEIGHT_DATA_PIN = 5   # HX711 DOUT 引脚 (BCM 5)
WEIGHT_CLOCK_PIN = 6  # HX711 SCK 引脚 (BCM 6)
WEIGHT_REFERENCE_UNIT = 400 # 重量传感器校准值 (需要根据实际情况调整)
hx711 = None

# MAX30102 (Heart Rate & SpO2)
max30102 = None
# 默认 I2C 总线为 1
I2C_BUS = 1

# Servo Motor
SERVO_PIN = 18 # 舵机信号引脚 (BCM 18)
servo_pwm = None

# 添加喂食相关配置
FEED_OPEN_ANGLE = 90   # 喂食器打开角度
FEED_CLOSE_ANGLE = 0   # 喂食器关闭角度
FEED_RATE = 5.0        # 每秒流出的猫粮克数（需要根据实际情况调整）
MIN_FEED_TIME = 0.5    # 最小喂食时间（秒）
MAX_FEED_TIME = 10.0   # 最大喂食时间（秒）

# --- GPIO 初始化与清理 ---
def initialize_gpio():
    """初始化 GPIO 设置"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False) # 禁用 GPIO 警告
        print("GPIO 初始化完成 (BCM模式)")
    except Exception as e:
        print(f"GPIO 初始化失败: {e}")
        raise

def cleanup_gpio():
    """清理 GPIO 资源"""
    global servo_pwm
    print("正在清理 GPIO 资源...")
    if servo_pwm:
        servo_pwm.stop()
    GPIO.cleanup()
    print("GPIO 清理完成")

# --- DHT11 温湿度传感器 ---
class DHTSensor:
    def __init__(self, pin=DHT_PIN):
        self.pin = pin
        try:
            # 使用 adafruit_dht 库
            self.sensor = adafruit_dht.DHT11(pin)
            print(f"DHT11 传感器初始化成功 (引脚: {pin})")
        except Exception as e:
            print(f"初始化 DHT11 传感器失败: {e}")
            self.sensor = None
            raise

    def read(self):
        if not self.sensor:
            print("错误：DHT11 传感器未初始化")
            return None, None
        try:
            temperature = self.sensor.temperature
            humidity = self.sensor.humidity
            # adafruit_dht 有时会读取失败，返回 None
            if temperature is not None and humidity is not None:
                return temperature, humidity
            else:
                # print("DHT11 读取失败，尝试重试...")
                time.sleep(0.5) # 短暂等待后重试一次
                temperature = self.sensor.temperature
                humidity = self.sensor.humidity
                if temperature is not None and humidity is not None:
                    return temperature, humidity
                else:
                    print("DHT11 再次读取失败")
                    return None, None
        except RuntimeError as error:
            # DHT 传感器常见错误
            # print(f"DHT11 读取运行时错误: {error.args[0]}")
            return None, None
        except Exception as error:
            print(f"DHT11 读取时发生未知错误: {error}")
            # self.sensor.exit() # exit() 方法可能不存在于所有 adafruit_dht 版本
            raise error

    def cleanup(self):
        # adafruit_dht 对象通常不需要手动 cleanup，依赖 GPIO.cleanup()
        pass

def initialize_dht_sensor():
    """初始化 DHT11 传感器模块"""
    global dht_sensor
    try:
        dht_sensor = DHTSensor(pin=DHT_PIN)
    except Exception as e:
        print(f"创建 DHTSensor 实例失败: {e}")
        dht_sensor = None

def read_temperature_humidity():
    """读取温度和湿度"""
    if dht_sensor:
        return dht_sensor.read()
    else:
        print("错误: DHT11 传感器未初始化")
        return None, None

# --- MAX30102 心率血氧传感器 ---
class MAX30102_Sensor:
    # (这里省略了 MAX30102 类的内部实现，因为它很长，假设它与 max30102.py 中的一致)
    # 寄存器地址定义
    REG_INTR_STATUS_1 = 0x00
    REG_INTR_STATUS_2 = 0x01
    REG_INTR_ENABLE_1 = 0x02
    REG_INTR_ENABLE_2 = 0x03
    REG_FIFO_WR_PTR = 0x04
    REG_OVF_COUNTER = 0x05
    REG_FIFO_RD_PTR = 0x06
    REG_FIFO_DATA = 0x07
    REG_FIFO_CONFIG = 0x08
    REG_MODE_CONFIG = 0x09
    REG_SPO2_CONFIG = 0x0A
    REG_LED1_PA = 0x0C
    REG_LED2_PA = 0x0D
    REG_PILOT_PA = 0x10

    # I2C地址（默认）
    I2C_ADDR = 0x57

    def __init__(self, i2c_bus=I2C_BUS):
        try:
            self.bus = smbus.SMBus(i2c_bus)
            print(f"I2C 总线 {i2c_bus} 打开成功")
            self.reset()
            self.initialize()
            print("MAX30102 初始化成功")
        except FileNotFoundError:
            print(f"错误: I2C 总线 {i2c_bus} 未找到。请确保 I2C 已启用并且设备连接正确。")
            self.bus = None
            raise
        except Exception as e:
            print(f"初始化 MAX30102 失败: {e}")
            self.bus = None
            raise

    def write_register(self, reg, value):
        if not self.bus: return
        self.bus.write_byte_data(self.I2C_ADDR, reg, value)

    def read_register(self, reg):
        if not self.bus: return None
        return self.bus.read_byte_data(self.I2C_ADDR, reg)

    def reset(self):
        self.write_register(self.REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)

    def initialize(self):
        self.write_register(self.REG_INTR_ENABLE_1, 0xC0) # PPG_RDY_EN = 1, ALC_OVF_EN = 1
        self.write_register(self.REG_INTR_ENABLE_2, 0x00)
        self.write_register(self.REG_FIFO_WR_PTR, 0x00)
        self.write_register(self.REG_OVF_COUNTER, 0x00)
        self.write_register(self.REG_FIFO_RD_PTR, 0x00)
        # SMP_AVE = 4, FIFO_ROLLOVER_EN = 0, FIFO_A_FULL = 15 (Trigger interrupt when 1 sample remaining)
        self.write_register(self.REG_FIFO_CONFIG, 0x4F)
        self.write_register(self.REG_MODE_CONFIG, 0x03) # SpO2 mode
        # SPO2_ADC_RGE = 4096nA, SPO2_SR = 100Hz, LED_PW = 411us (18-bit ADC)
        self.write_register(self.REG_SPO2_CONFIG, 0x27)
        # LED Pulse Amplitude: Adjust these values as needed
        self.write_register(self.REG_LED1_PA, 0x24) # Red LED ~7mA
        self.write_register(self.REG_LED2_PA, 0x24) # IR LED ~7mA
        self.write_register(self.REG_PILOT_PA, 0x7F) # Pilot LED ~25mA (Not used in SpO2 mode typically)

    def read_fifo(self):
        if not self.bus: return None, None
        try:
            # Read 6 bytes (3 bytes Red, 3 bytes IR)
            data = self.bus.read_i2c_block_data(self.I2C_ADDR, self.REG_FIFO_DATA, 6)
            # Combine bytes & mask to 18 bits
            red = ((data[0] << 16) | (data[1] << 8) | data[2]) & 0x3FFFF
            ir = ((data[3] << 16) | (data[4] << 8) | data[5]) & 0x3FFFF
            return red, ir
        except IOError as e:
            print(f"MAX30102 读取 FIFO 时发生 I/O 错误: {e}")
            return None, None
        except Exception as e:
            print(f"MAX30102 读取 FIFO 时发生未知错误: {e}")
            return None, None


    def get_sensor_data(self, sample_size=100):
        """获取指定数量的样本数据"""
        if not self.bus: return [], []
        red_buffer = []
        ir_buffer = []
        samples_collected = 0
        start_time = time.time()
        max_wait_time = 5 # seconds

        while samples_collected < sample_size:
            # 检查中断状态寄存器是否有新数据 (PPG_RDY bit)
            intr_status = self.read_register(self.REG_INTR_STATUS_1)
            if intr_status is None: # I2C error
                 print("MAX30102 读取中断状态失败")
                 return [], []

            if (intr_status & 0x40): # PPG_RDY is set
                red, ir = self.read_fifo()
                if red is not None and ir is not None:
                    red_buffer.append(red)
                    ir_buffer.append(ir)
                    samples_collected += 1
                else:
                    # FIFO read error, maybe retry or break
                    print("MAX30102 FIFO 读取失败")
                    time.sleep(0.01) # Small delay before retry
            else:
                # No new data yet, wait briefly
                time.sleep(0.005)

            # Timeout check
            if time.time() - start_time > max_wait_time:
                print(f"MAX30102 获取 {sample_size} 个样本超时 ({max_wait_time}秒)")
                break

        return red_buffer, ir_buffer

    def calculate_hr_and_spo2(self, ir_data, red_data):
        """ (基本的心率血氧计算逻辑，可能需要根据实际信号调整) """
        BUFFER_SIZE = len(ir_data)
        if BUFFER_SIZE < 50: # 需要足够的数据点
            print("数据点不足，无法计算心率血氧")
            return -1, -1, False

        # 简单的直流滤波
        ir_mean = sum(ir_data) / BUFFER_SIZE
        red_mean = sum(red_data) / BUFFER_SIZE
        ir_ac = [(val - ir_mean) for val in ir_data]
        red_ac = [(val - red_mean) for val in red_data]

        # 寻找 IR 信号的峰值 (简易方法)
        peaks = self.find_peaks(ir_ac, threshold=max(ir_ac)*0.6 if max(ir_ac) > 0 else 1, min_distance=int(100/ (220/60))) # 100Hz sample rate, min HR ~40bpm, max HR ~220bpm

        if len(peaks) < 2:
            # print("未能检测到足够的峰值")
            return -1, -1, False

        # 计算心率
        peak_intervals_ms = [(peaks[i+1] - peaks[i]) * 10 for i in range(len(peaks)-1)] # interval in ms (100Hz -> 10ms per sample)
        avg_interval_ms = sum(peak_intervals_ms) / len(peak_intervals_ms)
        if avg_interval_ms == 0: return -1,-1, False
        heart_rate = 60000 / avg_interval_ms

        # 计算血氧 (使用 R 值)
        # R = (AC_red / DC_red) / (AC_ir / DC_ir)
        # SpO2 = a - b * R (a, b 为校准系数, 典型值 a=110, b=25)
        ac_sq_red = sum([x*x for x in red_ac]) / BUFFER_SIZE
        ac_sq_ir = sum([x*x for x in ir_ac]) / BUFFER_SIZE
        if red_mean == 0 or ir_mean == 0 or ac_sq_ir == 0: return heart_rate, -1, True # Return HR if valid, but SpO2 failed

        R = (math.sqrt(ac_sq_red) / red_mean) / (math.sqrt(ac_sq_ir) / ir_mean)

        # 经验公式 (可能需要根据具体情况调整)
        spo2 = 110 - 25 * R
        # spo2 = 104 - 17 * R # 另一种常见公式

        # 约束范围
        spo2 = max(80.0, min(99.9, spo2))
        heart_rate = max(40, min(220, heart_rate))

        return int(round(heart_rate)), round(spo2, 2), True

    @staticmethod
    def find_peaks(signal, threshold, min_distance):
        peaks = []
        last_peak_index = -min_distance
        for i in range(1, len(signal) - 1):
            if signal[i] > threshold and signal[i] > signal[i-1] and signal[i] > signal[i+1]:
                if i - last_peak_index >= min_distance:
                    peaks.append(i)
                    last_peak_index = i
        return peaks

def initialize_max30102_sensor():
    """初始化 MAX30102 传感器模块"""
    global max30102
    try:
        max30102 = MAX30102_Sensor(i2c_bus=I2C_BUS)
    except Exception as e:
        print(f"创建 MAX30102_Sensor 实例失败: {e}")
        max30102 = None

def read_heart_rate_spo2(samples=100):
    """读取心率和血氧值"""
    if not max30102:
        print("错误: MAX30102 传感器未初始化")
        return None, None, False
    try:
        red, ir = max30102.get_sensor_data(sample_size=samples)
        if not red or not ir:
            # print("未能从 MAX30102 获取有效数据")
            return None, None, False

        hr, spo2, valid = max30102.calculate_hr_and_spo2(ir, red)
        if valid:
            return hr, spo2, True
        else:
            # print("计算出的心率/血氧值无效")
            return None, None, False
    except Exception as e:
        print(f"读取心率血氧时出错: {e}")
        return None, None, False


# --- HX711 重量传感器 ---
def initialize_weight_sensor(data_pin=WEIGHT_DATA_PIN, clock_pin=WEIGHT_CLOCK_PIN, ref_unit=WEIGHT_REFERENCE_UNIT):
    """初始化 HX711 重量传感器模块"""
    global hx711
    try:
        hx711 = HX711(data_pin, clock_pin)
        print(f"HX711 传感器初始化成功 (DOUT: {data_pin}, SCK: {clock_pin})")

        # 设置读取格式 (MSB first)
        hx711.setReadingFormat("MSB", "MSB")

        # 设置参考单位
        print(f"设置 HX711 参考单位: {ref_unit}")
        hx711.setReferenceUnit(ref_unit)

        # 自动设置偏移量 (去皮) - 启动时执行一次
        print("HX711 正在进行初始去皮操作...")
        print("请确保称重传感器上无负载")
        time.sleep(2) # 等待稳定
        hx711.reset()
        # hx711.tare() # tare 会进行多次读数取平均，更稳定
        hx711.autosetOffset() # autosetOffset 通常足够快
        offset = hx711.getOffset()
        print(f"HX711 初始去皮完成，偏移量: {offset}")

    except Exception as e:
        print(f"初始化 HX711 失败: {e}")
        hx711 = None
        raise

def tare_weight_sensor():
    """执行去皮操作"""
    if hx711:
        try:
            print("执行去皮操作...")
            hx711.tare(times=10) # 读取10次取平均以增加稳定性
            print("去皮完成")
            return True
        except Exception as e:
            print(f"去皮操作失败: {e}")
            return False
    else:
        print("错误: 重量传感器未初始化")
        return False

def read_weight_kg(reads=5):
    """读取重量并返回千克值 (通过多次读数取平均)"""
    if hx711:
        try:
            # 手动进行多次读数并取平均
            values = []
            for _ in range(reads):
                val = hx711.getWeight() # 调用不带参数的 getWeight
                if val is not False: # 库在某些错误情况下可能返回 False
                    values.append(val)
                time.sleep(0.05) # 短暂间隔，避免过于频繁的读取

            if not values: # 如果所有读数都失败
                print("HX711 读取所有样本失败")
                return None

            weight_g = sum(values) / len(values)
            weight_kg = round(weight_g / 1000.0, 3)
            # print(f"Raw average weight (g): {weight_g}, kg: {weight_kg}") # Debugging
            return weight_kg
        except Exception as e:
            print(f"读取重量时出错: {e}")
            return None # 返回 None 表示读取失败
    else:
        print("错误: 重量传感器未初始化")
        return None

# --- Servo Motor 舵机控制 ---
def setup_servo(pin=SERVO_PIN, frequency=50):
    """设置舵机 PWM"""
    global servo_pwm
    try:
        GPIO.setup(pin, GPIO.OUT)
        servo_pwm = GPIO.PWM(pin, frequency) # 50Hz (20ms cycle) is standard for servos
        servo_pwm.start(0) # Start PWM with 0% duty cycle (off)
        print(f"舵机 PWM 初始化成功 (引脚: {pin}, 频率: {frequency}Hz)")
        return True
    except Exception as e:
        print(f"设置舵机 PWM 失败: {e}")
        servo_pwm = None
        return False

def set_servo_angle(angle):
    """
    设置舵机角度
    参数:
        angle: 舵机角度 (0-180度)
    返回:
        成功返回True，失败返回False
    """
    try:
        if not 0 <= angle <= 180:
            print(f"舵机角度超出范围: {angle}")
            return False
        
        duty = angle / 18 + 2.5  # 将角度转换为占空比 (2.5% - 12.5%)
        GPIO.output(SERVO_PIN, True)
        servo_pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)  # 给舵机一点时间移动
        GPIO.output(SERVO_PIN, False)  # 关闭PWM输出，减少抖动
        return True
    except Exception as e:
        print(f"设置舵机角度时出错: {e}")
        return False

def feed(amount_grams):
    """
    根据指定的克数进行喂食
    参数:
        amount_grams: 喂食量（克）
    返回:
        成功返回True，失败返回False
    """
    try:
        # 计算喂食时间
        feed_time = amount_grams / FEED_RATE
        
        # 限制喂食时间在安全范围内
        feed_time = max(MIN_FEED_TIME, min(feed_time, MAX_FEED_TIME))
        
        print(f"开始喂食 {amount_grams}g 猫粮，预计时间 {feed_time:.1f}秒")
        
        # 打开喂食口
        set_servo_angle(FEED_OPEN_ANGLE)
        
        # 等待指定时间
        time.sleep(feed_time)
        
        # 关闭喂食口
        set_servo_angle(FEED_CLOSE_ANGLE)
        
        print(f"喂食完成，实际时间 {feed_time:.1f}秒")
        return True
    except Exception as e:
        print(f"喂食操作失败: {e}")
        try:
            # 确保关闭喂食口，防止猫粮持续流出
            set_servo_angle(FEED_CLOSE_ANGLE)
        except:
            pass
        return False

# --- 主初始化函数 ---
def initialize_hardware():
    """初始化所有硬件组件"""
    print("开始初始化硬件...")
    try:
        initialize_gpio()
        initialize_dht_sensor()
        initialize_max30102_sensor()
        initialize_weight_sensor() # 注意：这个函数会去皮，确保此时称重传感器空载
        setup_servo()
        print("所有硬件初始化完成。")
        return True
    except Exception as e:
        print(f"硬件初始化过程中发生错误: {e}")
        cleanup_gpio() # 尝试清理已初始化的部分
        return False

# --- 示例用法 ---
if __name__ == '__main__':
    # 注册信号处理，确保 Ctrl+C 时能清理 GPIO
    signal.signal(signal.SIGINT, lambda sig, frame: (cleanup_gpio(), sys.exit(0)))

    if not initialize_hardware():
        print("硬件初始化失败，退出程序。")
        sys.exit(1)

    print("\n--- 开始硬件读数测试 (按 Ctrl+C 退出) ---")

    try:
        while True:
            # 读取温湿度
            temp, hum = read_temperature_humidity()
            if temp is not None and hum is not None:
                print(f"温湿度: {temp:.1f}°C, {hum:.1f}%")
            else:
                print("温湿度: 读取失败")

            # 读取心率血氧
            hr, spo2, valid = read_heart_rate_spo2(samples=100) # 减少样本量以加快读取速度
            if valid:
                print(f"心率血氧: {hr} bpm, {spo2}%")
            else:
                # print("心率血氧: 读取无效或失败")
                # 可能是没放手指，是正常情况
                pass


            # 读取重量
            weight = read_weight_kg()
            if weight is not None:
                print(f"重量: {weight:.3f} kg")
            else:
                print("重量: 读取失败")

            # 控制舵机 (示例：每10秒转到90度再转回0度)
            print("\n舵机测试: 转到 90 度")
            set_servo_angle(90)
            time.sleep(5)

            print("舵机测试: 转回 0 度")
            set_servo_angle(0)
            time.sleep(5)

            print("-" * 20)
            # time.sleep(2) # 主循环间隔

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n主循环发生错误: {e}")
    finally:
        cleanup_gpio() 