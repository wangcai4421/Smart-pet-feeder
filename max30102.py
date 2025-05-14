import smbus
import time
import math

class MAX30102:
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

    def __init__(self, i2c_bus=1):
        self.bus = smbus.SMBus(i2c_bus)
        self.reset()
        self.initialize()

    def write_register(self, reg, value):
        """写入单个寄存器"""
        self.bus.write_byte_data(self.I2C_ADDR, reg, value)

    def read_register(self, reg):
        """读取单个寄存器"""
        return self.bus.read_byte_data(self.I2C_ADDR, reg)

    def reset(self):
        """复位传感器"""
        self.write_register(self.REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)

    def initialize(self):
        """初始化传感器配置"""
        # 配置中断
        self.write_register(self.REG_INTR_ENABLE_1, 0xC0)
        self.write_register(self.REG_INTR_ENABLE_2, 0x00)

        # FIFO配置
        self.write_register(self.REG_FIFO_WR_PTR, 0x00)
        self.write_register(self.REG_OVF_COUNTER, 0x00)
        self.write_register(self.REG_FIFO_RD_PTR, 0x00)
        self.write_register(self.REG_FIFO_CONFIG, 0x0F)  # 几乎满阈值17

        # 模式配置（SpO2模式）
        self.write_register(self.REG_MODE_CONFIG, 0x03)

        # SpO2配置（100Hz采样率，400μs脉冲宽度）
        self.write_register(self.REG_SPO2_CONFIG, 0x27)

        # LED电流配置（7mA红光，7mA红外，25mA环境）
        self.write_register(self.REG_LED1_PA, 0x24)
        self.write_register(self.REG_LED2_PA, 0x24)
        self.write_register(self.REG_PILOT_PA, 0x7F)

    def read_fifo(self):
        """读取FIFO数据（返回红光和红外值）"""
        # 读取6字节数据
        data = self.bus.read_i2c_block_data(self.I2C_ADDR, self.REG_FIFO_DATA, 6)

        # 解析红光数据（24位转18位）
        red = (data[0] << 16) | (data[1] << 8) | data[2]
        red &= 0x3FFFF  # 保留18位

        # 解析红外数据
        ir = (data[3] << 16) | (data[4] << 8) | data[5]
        ir &= 0x3FFFF

        return red, ir

    def get_sensor_data(self, sample_size=500):
        """获取指定数量的样本数据"""
        red_buffer = []
        ir_buffer = []

        for _ in range(sample_size):
            # 等待数据就绪（简单轮询）
            while (self.read_register(self.REG_INTR_STATUS_1) & 0x40) == 0:
                time.sleep(0.001)

            red, ir = self.read_fifo()
            red_buffer.append(red)
            ir_buffer.append(ir)

        return red_buffer, ir_buffer

    def calculate_hr_and_spo2(self, ir_data, red_data):
        """
        计算心率和血氧值
        :param ir_data: 红外信号数据
        :param red_data: 红光信号数据
        :return: 心率, 血氧值, 是否有效
        """
        BUFFER_SIZE = len(ir_data)
        # 去除直流分量
        ir_mean = sum(ir_data) // BUFFER_SIZE
        red_mean = sum(red_data) // BUFFER_SIZE
        ir_ac = [val - ir_mean for val in ir_data]
        red_ac = [val - red_mean for val in red_data]

        # 差分信号
        dx = [ir_ac[i + 1] - ir_ac[i] for i in range(BUFFER_SIZE - 1)]

        # 找到峰值位置
        peaks = self.find_peaks(dx, threshold=max(dx) // 2, min_distance=5)

        if len(peaks) < 2:
            return -1, -1, False

        # 计算心跳间隔
        peak_intervals = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        avg_interval = sum(peak_intervals) // len(peak_intervals)
        heart_rate = 60 * 100 // avg_interval  # 采样率为100Hz

        # 计算R值
        ac_red = max(red_ac) - min(red_ac)
        dc_red = red_mean
        ac_ir = max(ir_ac) - min(ir_ac)
        dc_ir = ir_mean

        R = (ac_red / dc_red) / (ac_ir / dc_ir)

        # 使用经验公式计算血氧值
        spo2 = 110 - 25 * R

        # 判断有效性
        hr_valid = 40 <= heart_rate <= 220
        spo2_valid = 80 <= spo2 <= 100

        return heart_rate, spo2, hr_valid and spo2_valid

    @staticmethod
    def find_peaks(signal, threshold, min_distance):
        """
        查找信号中的峰值位置
        :param signal: 输入信号
        :param threshold: 峰值最小高度
        :param min_distance: 峰值之间的最小距离
        :return: 峰值位置列表
        """
        peaks = []
        for i in range(1, len(signal) - 1):
            if signal[i] > threshold and signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
                if not peaks or i - peaks[-1] >= min_distance:
                    peaks.append(i)
        return peaks

class MAX30102App:
    """
    封装 MAX30102 应用逻辑的类，
    内部创建 MAX30102 对象，并通过 run() 方法启动数据采集和计算心率、血氧值。
    """
    def __init__(self, i2c_bus=1, sample_size=500):
        self.sensor = MAX30102(i2c_bus)
        self.sample_size = sample_size
        self.last_heart_rate = 0

    def run(self):
        try:
            while True:
                # 获取指定数量的样本数据
                red_data, ir_data = self.sensor.get_sensor_data(self.sample_size)

                # 计算心率和血氧值
                heart_rate, spo2, valid = self.sensor.calculate_hr_and_spo2(ir_data, red_data)

                if valid:
                    self.last_heart_rate = heart_rate  # 更新最新心率
                    print(f"心率: {heart_rate} bpm, 血氧: {spo2:.2f}%")
                else:
                    print("数据无效，请重试")
                    self.last_heart_rate = 0

                time.sleep(1)
        except KeyboardInterrupt:
            print("程序终止")

if __name__ == "__main__":
    app = MAX30102App()
    app.run()
