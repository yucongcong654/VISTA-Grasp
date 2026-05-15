# ROS 话题映射规范详解

在机器人端代码 `robot/teleop_ros_bridge.py` 中，我们标准化了从开发机下发的控制指令到真实机器人执行器之间的 ROS 话题（Topic）映射关系。

当前代码基线默认针对**睿尔曼（RealMan）具身双臂升降平台**进行了适配。如果您使用了相同的硬件，启动项目即可直接生效。

## 默认话题映射清单

以下是桥接节点默认监听和发布的 ROS 话题清单。

| 硬件功能模块 | ROS 话题 (Topic) | 消息类型 (Message Type) | 用途说明 |
| --- | --- | --- | --- |
| **头部控制 (Head)** | `/servo_control/move` <br> `/servo_control/move_double` | `std_msgs/Float32MultiArray` | 接收并映射 VR 头显的 Pitch/Yaw 姿态，驱动机器人云台。 |
| **左臂控制 (Left Arm)** | `/l_arm/rm_driver/JointPos` | `rm_msgs/JointPos` | 后端 IK 解算输出的左臂 7 自由度目标关节角指令。 |
| **右臂控制 (Right Arm)** | `/r_arm/rm_driver/JointPos` | `rm_msgs/JointPos` | 后端 IK 解算输出的右臂 7 自由度目标关节角指令。 |
| **左臂状态反馈** | `/l_arm/joint_states` | `sensor_msgs/JointState` | 实时订阅左臂的真实关节状态，用于提供给后端的数值优化器作为 IK 求解的平滑初值。 |
| **右臂状态反馈** | `/r_arm/joint_states` | `sensor_msgs/JointState` | 同上，订阅真实右臂的关节状态。 |
| **夹爪/末端控制 (Gripper)**| `/rx_gripper_control` <br> `/gripper_control` | `std_msgs/Float32` | 将 VR 手柄的 Trigger 扳机键按压深度映射为夹爪的开合角度或力度。 |
| **底盘移动 (Chassis)** | `/base_cmd_vel` | `geometry_msgs/Twist` | 监听 VR 手柄摇杆输入，发布底盘运动速度，用于全向或差速底盘。 |

## 如何适配自定义机器人 (HAL 扩展)

为了实现强兼容性，我们在后端架构设计上预留了硬件抽象层（Hardware Abstraction Layer）。

如果您要适配其他的机器人平台（例如 Unitree, Franka 等）：
1. **替换 URDF**：将您的机器人的 URDF 或 MJCF 文件放置到后端的 `assets` 目录下。
2. **新增硬件接口**：在 `backend/pilot/components` 目录下创建一个新的 `hand.py` 或 `controller.py` 的子类。
3. **修改桥接脚本**：在机器人端的 `teleop_ros_bridge.py` 中，根据您硬件厂商提供的包名，修改上述表格中的 `Topic` 和 `Message Type` 导入逻辑即可。
