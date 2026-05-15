# WebRTC 视频流与常见问题排查 (Troubleshooting)

Joyin Teleop 使用了强大的 `aiortc` 和原生 WebRTC API，实现了从机器人端摄像头到 VR 头显浏览器的第一人称高清、超低延迟视频推流。

## 视频流架构流转链路

为了帮助您在遇到网络问题时快速定位，以下是视频流的握手与传输架构：
1. **采集层（机器人端）**：通过 OpenCV 调用或直接订阅 ROS 的 `cv_bridge` 获取原生物理摄像头画面（默认配置了 `camera0` 和 `camera1` 两路画面）。
2. **信令中继层（开发机后端）**：`backend/communication/rtcrelay.py` 充当了 WebRTC 握手中的信令服务器（Signaling Server），负责在 VR 前端与机器人桥接端之间交换 SDP 和 ICE 候选信息。
3. **渲染层（VR 前端）**：通过 WebSocket 接收到信令后，前端发起 WebRTC PeerConnection，将其渲染成视频纹理，并贴图到 Three.js 场景的空间画布上。

---

## 常见问题排查 (FAQ)

### 1. 前端（VR 头显内）提示 WebSocket 无法连接
- **原因分析**：开发机后端的 `TeleopServer` 服务未正常启动，或者 VR 头显无法访问开发机的 `5174` 端口。
- **解决办法**：
  1. 查看终端上 `python control.py` 的运行日志，确认服务已监听 `5174`。
  2. 确保在连接 VR 后，**已经成功执行了反向代理命令**：`adb reverse tcp:5174 tcp:5174`。

### 2. 后端日志一直被“等待机器人连接”刷屏
- **现象特征**：开发机日志提示 `trying to connect ws://localhost:5175... failed.`
- **原因分析**：后端的 `control.py` 正在试图连接机器人底层的桥接控制服务，但通道不通。
- **解决办法**：
  - 如果您是在**无实物模拟**环境下测试，请新开一个终端并运行 `python backend/bridge/dummy.py`。
  - 如果您是在连接**真实机器人硬件**，请检查是否在开发机成功建立了 SSH 隧道端口映射：`ssh -L 5175:localhost:5175 rm@<机器人局域网IP>`，并确保机器人机载电脑上已经运行了 `teleop_ros_bridge.py`。

### 3. 画面黑屏或只有 UI 没有视频画面
- **排查步骤**：
  1. **检查底层节点**：在机器人的 SSH 终端里输入 `rostopic hz /camera_0/color/image_raw`（替换为您实际的 topic），查看是否有稳定的图像帧率输出。
  2. **检查编解码器**：WebRTC 默认使用 H264 或 VP8 编码。请确保 `.env` 中的分辨率设置没有超出设备硬编解码的上限。
  3. **查看前端报错**：在电脑的 Chrome 浏览器中访问 `chrome://inspect/#devices`，检查 VR 浏览器控制台是否有 `ICE Connection Failed` 报错。

### 4. 运行 `start.sh` 或 Python 后端时提示缺少 `pinocchio` 或 `casadi`
- **原因分析**：这两个库涉及复杂的底层 C++ 编译环境绑定，使用常规的 `pip install` 很容易因为系统依赖缺失而失败。
- **解决办法**：强烈建议直接使用项目提供的 `env_amd64.yaml` 文件去创建完整的 Conda 虚拟环境。若是在已有环境中报错，请尝试使用 conda-forge 源进行安装：
  `conda install -c conda-forge pinocchio casadi`
