import cv2
from picamera2 import Picamera2
from ultralytics import YOLO

def main(weights_path, imgsz=320, conf=0.5, device="cpu"):
    # 加载 YOLOv8 模型
    model = YOLO(weights_path)
    print(f"模型 {weights_path} 加载成功！")
    
    # 初始化摄像头
    camera = Picamera2()
    config = camera.create_video_configuration(
        main={"size": (imgsz, imgsz), "format": "RGB888"}  # 确保输出为 RGB 格式
    )
    camera.configure(config)
    camera.start()
    print("摄像头启动成功！")
    
    try:
        while True:
            # 捕获图像
            frame = camera.capture_array("main")  # 获取 RGB 图像
            
            # 打印图像形状以调试
            print(f"Captured frame shape: {frame.shape}")
            
            # 确保图像格式正确
            if frame.shape[2] == 1:  # 如果是灰度图像，转换为 RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            elif frame.shape[2] == 2:  # 如果是 YUV 格式，转换为 RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_YUV2RGB_YUYV)
            elif frame.shape[2] == 4:  # 如果有 Alpha 通道（RGBA），去掉 Alpha 通道
                frame = frame[:, :, :3]
            
            # 确保图像尺寸匹配
            frame = cv2.resize(frame, (imgsz, imgsz))
            
            # 使用 YOLOv8 进行推理（直接使用 RGB 图像）
            results = model(frame, imgsz=imgsz, conf=conf, device=device)
            
            # 绘制检测结果
            annotated_frame = results[0].plot()
            
            # 显示结果（使用 BGR 格式显示）
            annotated_frame_bgr = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
            cv2.imshow("Detection", annotated_frame_bgr)
            
            # 按下 'q' 键退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        # 释放资源
        camera.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    weights_path = "best.pt"  
    main(weights_path)
