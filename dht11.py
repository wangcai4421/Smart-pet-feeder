import time
import board
import adafruit_dht
import RPi.GPIO as GPIO

# 全局变量
dht_device = None

class DHTSensor:
    def __init__(self, pin=board.D17, sensor_type='DHT11'):
        """
        初始化传感器类
        :param pin: 传感器连接的 GPIO 引脚（例如 board.D17）
        :param sensor_type: 传感器类型，当前支持 'DHT11'，如需扩展可添加其他类型
        """
        self.pin = pin
        self.sensor_type = sensor_type
        if sensor_type == 'DHT11':
            self.sensor = adafruit_dht.DHT11(pin)
        else:
            raise ValueError("暂不支持的传感器类型: {}".format(sensor_type))
    
    def read(self):
        """
        读取温度（摄氏度）和湿度数据
        :return: (temperature, humidity) 如果读取失败，则返回 (None, None)
        """
        try:
            temperature = self.sensor.temperature
            humidity = self.sensor.humidity
            return temperature, humidity
        except RuntimeError as error:
            # DHT传感器读取失败时会抛出 RuntimeError，直接打印错误信息后返回空值
            print("读取错误:", error.args[0])
            return None, None
        except Exception as error:
            # 出现其他错误时释放资源并抛出异常
            self.sensor.exit()
            raise error

    def cleanup(self):
        """
        释放传感器占用的资源
        """
        self.sensor.exit()

# 添加缺失的init_gpio函数
def init_gpio():
    GPIO.setmode(GPIO.BCM)
    print("GPIO初始化完成")

# 添加init_dht_sensor函数
def init_dht_sensor():
    global dht_device
    try:
        # 初始化一个空的变量，但不实际创建传感器对象
        dht_device = None
        print("DHT传感器变量初始化")
    except Exception as e:
        print(f"初始化DHT传感器变量时出错: {e}")

def main():
    print("Initializing system...")
    init_gpio()
    init_dht_sensor()  # 添加这一行初始化DHT11传感器
    
    # 初始化 DHT11 传感器类（假设 DATA 接到 GPIO17）
    dht_sensor = DHTSensor(pin=board.D17, sensor_type='DHT11')
    
    try:
        while True:
            temp, humidity = dht_sensor.read()
            if temp is not None and humidity is not None:
                print("Temp: {:.1f}°C  Humidity: {}%".format(temp, humidity))
            # 每2秒读取一次
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("程序退出")
    finally:
        dht_sensor.cleanup()

def cleanup_resources():
    global dht_device
    if dht_device is not None:
        dht_device.exit()
    GPIO.cleanup()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Program terminated by user")
        cleanup_resources()
    except Exception as e:
        print(f"An error occurred: {e}")
        cleanup_resources()
