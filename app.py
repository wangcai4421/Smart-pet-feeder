# app.py
import io
import cv2
import time
import threading
import hardware # 导入我们整合的硬件模块
from flask import Flask, render_template, Response, request, jsonify, redirect, url_for, session, flash
from picamera2 import Picamera2
from ultralytics import YOLO
import RPi.GPIO as GPIO # 需要导入 GPIO 以便 hardware 模块正常工作
from functools import wraps
import models # 导入我们创建的用户和喂食计划模型
from datetime import datetime, timedelta

# --- 配置 ---
WEIGHTS_PATH = "best.pt"
IMG_SIZE = 320 # 图像大小，应与 detect.py 保持一致
CONF_THRESHOLD = 0.5 # 置信度阈值
DEVICE = "cpu" # 或者 "cuda" 如果有 GPU

# --- 全局变量 ---
app = Flask(__name__)
app.secret_key = "cat_feeder_secret_key"  # 用于会话加密
app.permanent_session_lifetime = timedelta(days=30)  # 设置会话有效期

camera = None
model = None
last_frame = None # 用于存储最新的视频帧 (带标注)
last_sensor_data = {
    "temperature": None,
    "humidity": None,
    "weight": None,
    "cat_detected": False, # 新增：猫咪检测状态
    "last_detection_time": None
}
feeding_mode = "manual" # 'manual' or 'auto'
feed_cooldown = 60 # 自动喂食冷却时间（秒）
last_auto_feed_time = 0
cat_detected_flag = False # 标记是否检测到猫

# 线程锁，用于安全地访问共享变量
frame_lock = threading.Lock()
sensor_lock = threading.Lock()
mode_lock = threading.Lock()
detection_lock = threading.Lock()

# --- 初始化 ---
def initialize_system():
    """初始化硬件、摄像头和模型"""
    global camera, model
    print("正在初始化系统...")
    try:
        # 初始化数据库
        models.init_db()
        print("数据库初始化成功。")
        
        # 初始化硬件 (GPIO, 传感器, 舵机)
        if not hardware.initialize_hardware():
            raise RuntimeError("硬件初始化失败!")
        print("硬件初始化成功。")

        # 初始化摄像头
        camera = Picamera2()
        config = camera.create_video_configuration(
            main={"size": (IMG_SIZE, IMG_SIZE), "format": "RGB888"}
        )
        camera.configure(config)
        camera.start()
        # 等待摄像头稳定
        time.sleep(2)
        print("摄像头启动成功。")

        # 加载模型
        model = YOLO(WEIGHTS_PATH)
        # 尝试进行一次推理以预热模型（可选）
        dummy_frame = camera.capture_array("main")
        model(dummy_frame, imgsz=IMG_SIZE, conf=CONF_THRESHOLD, device=DEVICE, verbose=False)
        print(f"YOLO 模型 '{WEIGHTS_PATH}' 加载成功。")

        print("系统初始化完成。")
        return True

    except Exception as e:
        print(f"系统初始化过程中发生错误: {e}")
        # 尝试清理资源
        if camera:
            try:
                camera.stop()
            except Exception as cam_e:
                print(f"停止摄像头时出错: {cam_e}")
        hardware.cleanup_gpio()
        return False

# --- 后台线程 ---
def sensor_reading_thread():
    """后台线程：持续读取传感器数据"""
    global last_sensor_data
    while True:
        try:
            temp, hum = hardware.read_temperature_humidity()
            weight = hardware.read_weight_kg() # 使用更新后的函数

            with sensor_lock:
                last_sensor_data["temperature"] = round(temp, 1) if temp is not None else None
                last_sensor_data["humidity"] = round(hum, 1) if hum is not None else None
                last_sensor_data["weight"] = weight if weight is not None else None
                # cat_detected 状态由 detection_thread 更新
                # last_detection_time 由 detection_thread 更新

            # print(f"Sensor Update: T={temp}, H={hum}, W={weight}") # Debug
        except Exception as e:
            print(f"传感器读取线程错误: {e}")
            # 防止因错误快速循环消耗 CPU
            time.sleep(5)
        # 读取间隔
        time.sleep(2)

def detection_thread():
    """后台线程：持续进行猫咪检测和处理自动喂食"""
    global last_frame, last_sensor_data, feeding_mode, last_auto_feed_time, cat_detected_flag
    if not camera or not model:
        print("错误：摄像头或模型未初始化，检测线程无法启动。")
        return

    while True:
        current_time = time.time()
        local_cat_detected = False # 本次循环是否检测到
        try:
            # 捕获图像
            frame_raw = camera.capture_array("main")

            # 进行推理
            results = model(frame_raw, imgsz=IMG_SIZE, conf=CONF_THRESHOLD, device=DEVICE, verbose=False)

            # 绘制结果并更新最新帧
            annotated_frame_rgb = results[0].plot() # 假设 plot() 返回 RGB

            # *** 新增：将颜色通道从 RGB 翻转到 BGR ***
            annotated_frame_bgr = cv2.cvtColor(annotated_frame_rgb, cv2.COLOR_RGB2BGR)

            with frame_lock:
                # 将处理后的 BGR 帧编码为 JPEG
                ret, buffer = cv2.imencode('.jpg', annotated_frame_bgr) # 使用 BGR 帧进行编码
                if ret:
                    last_frame = buffer.tobytes()

            # 检查是否有检测到目标 (假设 'cat' 是类别 0 或特定类别名称)
            detected_cats = 0
            if len(results[0].boxes) > 0:
                 # 检查检测到的类别名称或 ID
                 # 注意: 需要根据你的 'best.pt' 模型的实际类别来调整
                 for box in results[0].boxes:
                     class_id = int(box.cls[0])
                     class_name = model.names[class_id] # 获取类别名称
                     # print(f"Detected: {class_name} (ID: {class_id})") # Debug
                     if class_name == 'cat': # 或者使用 ID if class_id == 0:
                         detected_cats += 1


            local_cat_detected = detected_cats > 0

            # 更新全局检测状态
            with detection_lock:
                cat_detected_flag = local_cat_detected
                if local_cat_detected:
                    last_sensor_data["last_detection_time"] = current_time


            # --- 自动喂食逻辑 ---
            with mode_lock:
                current_mode = feeding_mode # 获取当前模式

            if current_mode == "auto" and local_cat_detected:
                 print("自动模式：检测到猫咪！")
                 # 检查冷却时间
                 if current_time - last_auto_feed_time > feed_cooldown:
                     print("冷却时间已过，执行自动喂食...")
                     success = hardware.set_servo_angle(90) # 打开舵机（假设90度是打开）
                     if success:
                         time.sleep(2) # 保持打开一段时间（例如2秒）
                         hardware.set_servo_angle(0) # 关闭舵机（假设0度是关闭）
                         last_auto_feed_time = current_time # 更新上次喂食时间
                         print("自动喂食完成。")
                     else:
                         print("自动喂食舵机控制失败。")
                 else:
                     print(f"自动喂食冷却中... 还需 {feed_cooldown - (current_time - last_auto_feed_time):.1f} 秒")


            # 短暂休眠，避免CPU占用过高，同时控制检测帧率
            time.sleep(0.1) # 大约 10 FPS

        except Exception as e:
            print(f"检测线程错误: {e}")
            time.sleep(1) # 发生错误时等待长一点

# --- 用户登录相关函数 ---
def login_required(f):
    """验证用户是否已登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Flask 路由 ---
@app.route('/')
@login_required
def index():
    """渲染主页"""
    user_id = session.get('user_id')
    username = session.get('username')
    
    # 获取默认喂食量设置
    default_amount = float(models.get_user_setting(user_id, 'default_feed_amount', '30'))
    
    # 获取最小食物级别设置
    min_food_level = float(models.get_user_setting(user_id, 'min_food_level', '0.5'))
    
    # 获取所有喂食计划
    schedules = models.get_feeding_schedules()
    
    return render_template('index.html', 
                          username=username,
                          default_amount=default_amount,
                          min_food_level=min_food_level,
                          schedules=schedules)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('login.html', error='请填写用户名和密码')
        
        success, result = models.authenticate_user(username, password)
        
        if success:
            # 设置会话
            session['user_id'] = result
            session['username'] = username
            session.permanent = True
            return redirect(url_for('index'))
        else:
            # 登录失败
            return render_template('login.html', error=result)
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            return render_template('register.html', error='请填写所有必填字段')
        
        if password != confirm_password:
            return render_template('register.html', error='两次输入的密码不匹配')
        
        success, result = models.register_user(username, password)
        
        if success:
            # 注册成功，自动登录
            session['user_id'] = result
            session['username'] = username
            session.permanent = True
            return redirect(url_for('index'))
        else:
            # 注册失败
            return render_template('register.html', error=result)
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """用户登出"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/video_feed')
@login_required
def video_feed():
    """提供视频流"""
    def generate_frames():
        while True:
            with frame_lock:
                frame_bytes = last_frame
            if frame_bytes is None:
                # 可以生成一个 "无信号" 或 "加载中" 的图像
                time.sleep(0.1)
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.05) # 控制发送帧率

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/sensor_data')
@login_required
def api_sensor_data():
    """提供最新的传感器数据和模式"""
    global last_auto_feed_time
    user_id = session.get('user_id')
    
    with sensor_lock, mode_lock, detection_lock:
        data_copy = last_sensor_data.copy()
        data_copy["mode"] = feeding_mode
        # 结合 detection_lock 获取最新状态
        data_copy["cat_detected"] = cat_detected_flag
        
        # 获取最新的喂食计划，用于前端显示
        data_copy["schedules"] = models.get_feeding_schedules()
        
        # 检查是否需要根据时间计划进行喂食
        should_feed, amount = models.should_feed_now()
        if should_feed and feeding_mode == 'auto':
            # 获取当前时间
            current_time = time.time()
            
            # 检查是否超过喂食冷却时间
            if current_time - last_auto_feed_time > feed_cooldown:
                print(f"定时喂食计划触发，喂食量：{amount}g")
                
                # 实际执行喂食操作
                try:
                    hardware.feed(amount)
                    # 更新最后喂食时间
                    last_auto_feed_time = current_time
                    # 记录喂食事件
                    models.log_feeding(user_id, amount, 'auto')
                    # 设置成功标志
                    data_copy["scheduled_feed"] = True
                    data_copy["feed_amount"] = amount
                    data_copy["feed_success"] = True
                    data_copy["feed_message"] = f"已执行定时喂食，喂食量：{amount}g"
                except Exception as e:
                    # 喂食失败
                    data_copy["scheduled_feed"] = True
                    data_copy["feed_amount"] = amount
                    data_copy["feed_success"] = False
                    data_copy["feed_message"] = f"定时喂食失败：{str(e)}"
                    print(f"定时喂食执行失败：{str(e)}")
            else:
                # 喂食冷却中
                time_left = feed_cooldown - (current_time - last_auto_feed_time)
                data_copy["scheduled_feed"] = True
                data_copy["feed_amount"] = amount
                data_copy["feed_cooldown"] = True
                data_copy["cooldown_time"] = round(time_left, 1)
                data_copy["feed_message"] = f"喂食冷却中，还需等待 {round(time_left, 1)} 秒"
                print(f"定时喂食冷却中，还需等待 {round(time_left, 1)} 秒")
        else:
            data_copy["scheduled_feed"] = False
            
    return jsonify(data_copy)

@app.route('/api/feed', methods=['POST'])
@login_required
def api_feed():
    """触发喂食操作"""
    user_id = session.get('user_id')
    
    # 获取喂食量，如果未指定则使用默认值
    feed_amount = request.json.get('amount') if request.is_json else None
    if not feed_amount:
        feed_amount = float(models.get_user_setting(user_id, 'default_feed_amount', '30'))
    
    try:
        # 发出喂食指令 (假设 hardware 模块有提供这样的接口)
        hardware.feed(feed_amount)
        
        # 记录喂食事件
        mode = 'manual' if feeding_mode == 'manual' else 'auto'
        models.log_feeding(user_id, feed_amount, mode)
        
        return jsonify({"status": "success", "message": f"成功喂食 {feed_amount}g 猫粮"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"喂食失败: {str(e)}"}), 500

@app.route('/api/mode', methods=['POST'])
@login_required
def api_mode():
    """切换喂食模式"""
    global feeding_mode
    data = request.get_json()
    new_mode = data.get('mode')

    if new_mode not in ['manual', 'auto']:
        return jsonify({"status": "error", "message": "无效的模式"}), 400

    with mode_lock:
        feeding_mode = new_mode
    print(f"喂食模式已切换为: {new_mode}")
    return jsonify({"status": "success", "message": f"模式已切换为 {new_mode}", "current_mode": new_mode})

# --- 喂食计划管理 ---
@app.route('/api/schedule', methods=['POST'])
@login_required
def add_schedule():
    """添加喂食计划"""
    if not request.is_json:
        return jsonify({"status": "error", "message": "需要JSON格式数据"}), 400
    
    data = request.get_json()
    feed_time = data.get('time')
    amount = data.get('amount')
    
    if not feed_time or not amount:
        return jsonify({"status": "error", "message": "时间和喂食量为必填项"}), 400
    
    try:
        amount = float(amount)
        success, result = models.add_feeding_schedule(feed_time, amount)
        
        if success:
            return jsonify({
                "status": "success", 
                "message": "喂食计划添加成功",
                "schedule_id": result
            })
        else:
            return jsonify({"status": "error", "message": result}), 500
    except ValueError:
        return jsonify({"status": "error", "message": "喂食量必须是有效数字"}), 400

@app.route('/api/schedule/<int:schedule_id>', methods=['PUT'])
@login_required
def update_schedule(schedule_id):
    """更新喂食计划"""
    if not request.is_json:
        return jsonify({"status": "error", "message": "需要JSON格式数据"}), 400
    
    data = request.get_json()
    feed_time = data.get('time')
    amount = data.get('amount')
    
    try:
        if amount is not None:
            amount = float(amount)
        
        success = models.update_feeding_schedule(schedule_id, feed_time, amount)
        
        if success:
            return jsonify({"status": "success", "message": "喂食计划更新成功"})
        else:
            return jsonify({"status": "error", "message": "更新喂食计划失败"}), 500
    except ValueError:
        return jsonify({"status": "error", "message": "喂食量必须是有效数字"}), 400

@app.route('/api/schedule/<int:schedule_id>', methods=['DELETE'])
@login_required
def delete_schedule(schedule_id):
    """删除喂食计划"""
    success = models.delete_feeding_schedule(schedule_id)
    
    if success:
        return jsonify({"status": "success", "message": "喂食计划删除成功"})
    else:
        return jsonify({"status": "error", "message": "删除喂食计划失败"}), 500

@app.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    """更新用户设置"""
    user_id = session.get('user_id')
    if not request.is_json:
        return jsonify({"status": "error", "message": "需要JSON格式数据"}), 400
    
    data = request.get_json()
    updates = {}
    
    # 检查是否有设置更新
    if 'default_feed_amount' in data:
        try:
            amount = float(data['default_feed_amount'])
            updates['default_feed_amount'] = str(amount)
        except ValueError:
            return jsonify({"status": "error", "message": "默认喂食量必须是有效数字"}), 400
    
    if 'min_food_level' in data:
        try:
            level = float(data['min_food_level'])
            updates['min_food_level'] = str(level)
        except ValueError:
            return jsonify({"status": "error", "message": "最小食物水平必须是有效数字"}), 400
    
    if 'auto_feed_enabled' in data:
        updates['auto_feed_enabled'] = '1' if data['auto_feed_enabled'] else '0'
    
    # 更新设置
    success = True
    for key, value in updates.items():
        if not models.set_user_setting(user_id, key, value):
            success = False
    
    if success:
        return jsonify({"status": "success", "message": "设置更新成功"})
    else:
        return jsonify({"status": "error", "message": "更新设置失败"}), 500

# --- 程序入口 ---
if __name__ == '__main__':
    if initialize_system():
        # 启动后台线程
        sensor_thread = threading.Thread(target=sensor_reading_thread, daemon=True)
        detect_thread = threading.Thread(target=detection_thread, daemon=True)
        sensor_thread.start()
        detect_thread.start()

        # 启动 Flask 应用
        # host='0.0.0.0' 允许局域网访问
        print("启动 Flask 应用...")
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True) # 使用 threaded=True 允许并发请求
    else:
        print("系统初始化失败，无法启动应用。")

    # 在程序退出时清理 GPIO (虽然 Flask run 通常会阻塞，但以防万一)
    print("应用即将退出，清理资源...")
    if camera:
        try:
            camera.stop()
        except: pass
    hardware.cleanup_gpio() 