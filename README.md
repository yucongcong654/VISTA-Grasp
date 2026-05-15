<div align="center">

# VISTA-Grasp: 具身智能双臂机器人遥操作系统

**由 [QiongMing-Intelligence] 研发的轻量级、低延迟 WebXR 遥操方案**

</div>

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](#)
[![中文](https://img.shields.io/badge/Language-中文-blue)](#)
<br>
[![Project](https://img.shields.io/badge/Project-Website-blue)](#)
[![ROS1](https://img.shields.io/badge/ROS-Noetic-green)](#)
[![Python](https://img.shields.io/badge/Python-3.8+-orange)](#)
[![React](https://img.shields.io/badge/React-19-purple)](#)
[![License](https://img.shields.io/badge/License-Apache--2.0-green)](LICENSE)

</div>

<br>

<div align="center">

![🥽 第一人称视角实时遥操](docs/images/image43.mp4) ![🤖 真实机器人第三人称视角](docs/images/media7.mp4)

_(图示：基于 Meta Quest 3 的实时遥操双视角演示)_

</div>

---

### 🥽 欢迎使用 VISTA-Grasp！我们构建了一套面向具身智能的端到端 WebXR 遥操框架！ 🦾🌍

VISTA-Grasp 核心特性：

- **多模态 XR 控制**：基于 WebXR，在浏览器中即可实现高精度的头部姿态跟踪与双手控制器位姿采集，完美适配 Meta Quest 3 等主流头显。
- **超低延迟视频回传**：集成了双路 WebRTC 视频流，将机器人视角的 `camera0` 与 `camera1` 无缝推送到 VR 头显中，打造极度沉浸的第一人称体验。
- **高性能双臂运动学**：在开发机端基于 Pinocchio 与 CasADi 运行毫秒级高频 IK 解算，将你的手部动作平滑映射到真实机械臂的 7 自由度关节上。
- **开箱即用的极简部署**：一键式 `tmux` 启动脚本管理，前后端分离架构，并提供标准的 ROS 桥接层，轻松适配头部、双臂、夹爪及底盘的控制话题。

---

# ⚙️ 快速开始

## 环境安装

**1. 克隆项目代码**

```bash
git clone https://github.com/your-company/yqbz_teleop.git
cd yqbz_teleop
```

**2. 配置后端环境 (以 AMD64 为例，macOS 使用 `env_arm64.yaml`)**

```bash
conda env create -f env_amd64.yaml
conda activate teleop
```

**3. 安装前端依赖**

```bash
cd frontend
npm install
cd ..
```

---

## 🚀 启动系统

### 步骤一：启动核心服务

在开发机上，使用自动化脚本一键启动前端页面与后端控制中心：

```bash
cd run
./start.sh
```

### 步骤二：启动机器人端

在连接机器人的终端上（通过 SSH），启动 ROS 桥接与摄像头节点：

```bash
cd run
./rob.sh
```

> 如果你没有真实机器人，可以通过运行 `python backend/bridge/dummy.py` 来开启无头模拟模式。

### 步骤三：连接 VR 头显

推荐使用 **Meta Quest Developer Hub (MQDH)** 进行可视化连接。若使用命令行，请执行以下命令进行本地端口映射：

```bash
adb connect <你的VR_IP>:5555
adb reverse tcp:5173 tcp:5173
adb reverse tcp:5174 tcp:5174
```

戴上头显，在浏览器中访问 `http://localhost:5173`，点击“进入 AR”即可开始你的遥操之旅！

---

# 📚 进阶文档

为了满足企业级的高级定制需求，详细的架构说明与配置文档请移步：

- [系统配置与自定义端口指南](docs/configuration.md)
- [ROS 话题映射规范详解](docs/ros_topics.md)
- [WebRTC 视频流与调试说明](docs/webrtc_troubleshooting.md)
- [如何为本项目贡献代码 (CONTRIBUTING)](CONTRIBUTING.md)

---

# 📜 许可证 & 免责声明

本项目采用 **Apache License 2.0** 许可证开源。详细信息请参阅 [LICENSE](https://www.apache.org/licenses/LICENSE-2.0) 文件。

> **免责声明**：本项目涉及真实机器人实物控制。在将本软件用于真实硬件前，请务必进行充分的仿真测试与安全评估，并确保现场具备物理急停、安全看护等保障措施。对于因使用本项目直接或间接引发的任何硬件损坏或安全风险，开源主体不承担任何连带责任。

# 社区与交流

- GitHub Issues：用于提交Bug、功能需求和问题咨询。
- 微信群：欢迎添加微信号“13681751192”（小助手）， 加入交流群
- 也可以扫描小助手微信二维码入群：

<img src="docs/images/1b945b1e82a3b088a62f5e63356b6c35.jpg" alt="微信群二维码" width="15%" />

- 邮箱：yucongcong654@gmail.com（用于正式合作和问题咨询）

# ✨ 致谢

感谢所有为本项目做出贡献的开发者！
本项目的动力学解算依赖于优秀的开源库 [Pinocchio](https://github.com/stack-of-tasks/pinocchio) 与 [CasADi](https://github.com/casadi/casadi)。
