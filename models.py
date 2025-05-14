import sqlite3
import hashlib
import os
from datetime import datetime, time

# 数据库初始化
def init_db():
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建喂食计划表（简化版）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feeding_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,  -- 存储为 HH:MM 格式
        amount REAL NOT NULL  -- 喂食量(克)
    )
    ''')
    
    # 创建喂食记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feeding_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL NOT NULL,  -- 喂食量(克)
        mode TEXT NOT NULL,  -- 'auto' 或 'manual'
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')

    # 创建系统设置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        setting_key TEXT NOT NULL,
        setting_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# 用户相关功能
def generate_salt():
    """生成随机盐值"""
    return os.urandom(16).hex()

def hash_password(password, salt):
    """哈希密码"""
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()

def register_user(username, password):
    """注册新用户"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        # 检查用户是否已存在
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return False, "用户名已存在"
        
        # 生成盐值和密码哈希
        salt = generate_salt()
        password_hash = hash_password(password, salt)
        
        # 插入新用户
        cursor.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, password_hash, salt)
        )
        
        # 获取新用户ID
        user_id = cursor.lastrowid
        
        # 为新用户创建默认设置
        default_settings = [
            ("default_feed_amount", "30"),  # 默认喂食量(克)
            ("min_food_level", "0.5"),     # 最小食物阈值(kg)
            ("auto_feed_enabled", "1")      # 自动喂食启用
        ]
        
        for key, value in default_settings:
            cursor.execute(
                "INSERT INTO system_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                (user_id, key, value)
            )
        
        conn.commit()
        conn.close()
        return True, user_id
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"注册失败: {str(e)}"

def authenticate_user(username, password):
    """验证用户登录"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        # 获取用户记录
        cursor.execute("SELECT id, password_hash, salt FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return False, "用户名不存在"
        
        user_id, stored_hash, salt = user
        
        # 验证密码
        input_hash = hash_password(password, salt)
        if input_hash == stored_hash:
            conn.close()
            return True, user_id
        else:
            conn.close()
            return False, "密码错误"
    
    except Exception as e:
        conn.close()
        return False, f"登录失败: {str(e)}"

# 喂食计划相关功能
def add_feeding_schedule(feed_time, amount):
    """添加喂食计划"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO feeding_schedules (time, amount) VALUES (?, ?)",
            (feed_time, amount)
        )
        conn.commit()
        schedule_id = cursor.lastrowid
        conn.close()
        return True, schedule_id
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"添加喂食计划失败: {str(e)}"

def get_feeding_schedules():
    """获取所有喂食计划"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id, time, amount FROM feeding_schedules ORDER BY time"
        )
        schedules = []
        for row in cursor.fetchall():
            schedule_id, feed_time, amount = row
            schedules.append({
                "id": schedule_id,
                "time": feed_time,
                "amount": amount
            })
        
        conn.close()
        return schedules
    
    except Exception as e:
        conn.close()
        return []

def update_feeding_schedule(schedule_id, feed_time=None, amount=None):
    """更新喂食计划"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        updates = []
        params = []
        
        if feed_time is not None:
            updates.append("time = ?")
            params.append(feed_time)
        
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        
        if not updates:
            conn.close()
            return True  # 没有要更新的内容
        
        query = f"UPDATE feeding_schedules SET {', '.join(updates)} WHERE id = ?"
        params.append(schedule_id)
        
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return False

def delete_feeding_schedule(schedule_id):
    """删除喂食计划"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM feeding_schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return False

# 系统设置相关功能
def get_user_setting(user_id, key, default=None):
    """获取用户设置"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT setting_value FROM system_settings WHERE user_id = ? AND setting_key = ?",
            (user_id, key)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        return default
    
    except Exception:
        conn.close()
        return default

def set_user_setting(user_id, key, value):
    """设置或更新用户设置"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        # 检查设置是否已存在
        cursor.execute(
            "SELECT id FROM system_settings WHERE user_id = ? AND setting_key = ?",
            (user_id, key)
        )
        if cursor.fetchone():
            # 更新现有设置
            cursor.execute(
                "UPDATE system_settings SET setting_value = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND setting_key = ?",
                (value, user_id, key)
            )
        else:
            # 创建新设置
            cursor.execute(
                "INSERT INTO system_settings (user_id, setting_key, setting_value) VALUES (?, ?, ?)",
                (user_id, key, value)
            )
        
        conn.commit()
        conn.close()
        return True
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return False

# 喂食记录相关功能
def log_feeding(user_id, amount, mode='manual'):
    """记录喂食事件"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO feeding_logs (user_id, amount, mode) VALUES (?, ?, ?)",
            (user_id, amount, mode)
        )
        conn.commit()
        conn.close()
        return True
    
    except Exception:
        conn.rollback()
        conn.close()
        return False

def get_feeding_logs(user_id, limit=10):
    """获取用户的喂食记录"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id, amount, mode, timestamp FROM feeding_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit)
        )
        logs = []
        for row in cursor.fetchall():
            log_id, amount, mode, timestamp = row
            logs.append({
                "id": log_id,
                "amount": amount,
                "mode": mode,
                "timestamp": timestamp
            })
        
        conn.close()
        return logs
    
    except Exception:
        conn.close()
        return []

# 检查是否应该进行喂食
def should_feed_now():
    """根据当前时间检查是否应该进行喂食"""
    conn = sqlite3.connect('catfeeder.db')
    cursor = conn.cursor()
    
    try:
        # 获取当前时间
        current_time = datetime.now().time()
        current_time_str = current_time.strftime("%H:%M")
        
        # 查找当前时间匹配的喂食计划
        cursor.execute(
            "SELECT id, amount FROM feeding_schedules WHERE time = ?",
            (current_time_str,)
        )
        schedule = cursor.fetchone()
        
        conn.close()
        
        if schedule:
            return True, schedule[1]  # 返回应该喂食和喂食量
        return False, 0
    
    except Exception:
        conn.close()
        return False, 0

# 初始化
if __name__ == "__main__":
    init_db() 