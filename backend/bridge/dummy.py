import asyncio
import json
import logging
import argparse
import sys
from pathlib import Path
from typing import List
import websockets

sys.path.append(str(Path(__file__).resolve().parents[1]))
from teleop_env import env_bool, env_int, env_str

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DummyRobotBridge")

log_formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("DummyRobotBridge")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.propagate = False

class DummyRobotBridge:
    def __init__(self, host=None, port=None, test_mode=False):
        self.host = host or env_str("TELEOP_ROBOT_BRIDGE_HOST", "localhost")
        self.port = port if port is not None else env_int("TELEOP_ROBOT_PORT", 5175)
        self.clients = set()
        self.test_mode = test_mode
        
        # 如果是测试模式，才添加文件日志处理器
        if self.test_mode:
            log_file_handler = logging.FileHandler('dummy_robot_bridge.log', 'w')
            log_file_handler.setFormatter(log_formatter)
            logger.addHandler(log_file_handler)
            logger.info("[DUMMY] 测试模式已启用，日志将保存到文件")

    def send_head_control(self, yaw: float, pitch: float):
        logger.info(f"[DUMMY] 头部控制: 头摆={yaw:.2f}, 俯仰={pitch:.2f}")

    def send_arm_control(self, q_list: List[float], is_left_arm: bool):
        logger.info(f"[DUMMY] {'左' if is_left_arm else '右'} 手臂控制: {q_list}")

    def send_lift_control(self, curr_height: float, init_height: float):
        logger.info(f"[DUMMY] 升降控制: curr_height={curr_height}, init_height={init_height}")

    def send_lift_speed_control(self, speed: float):
        logger.info(f"[DUMMY] 升降速度控制: speed={speed:.2f}")

    def send_left_hand_control(self, ratio: float):
        logger.info(f"[DUMMY] 左手控制: ratio={ratio:.2f}")

    def send_right_gripper_control(self, ratio: float):
        logger.info(f"[DUMMY] 右手控制: ratio={ratio:.2f}")

    def react_on_left_controller_state(self, data: dict):
        logger.info(f"[DUMMY] 左手控制器状态: {data}")

    def react_on_right_controller_state(self, data: dict):
        logger.info(f"[DUMMY] 右手控制器状态: {data}")

    async def handle_client(self, websocket):
        """处理每个客户端的连接"""
        self.clients.add(websocket)
        logger.info(f"WebSocket 客户端连接: {websocket.remote_address}")
        try:
            async for message in websocket:
                command = json.loads(message)
                msg_type = command.get("type")
                data = command.get("data")

                if msg_type == "head_control":
                    self.send_head_control(data["yaw"], data["pitch"])
                elif msg_type == "l_r_arm_control":
                    self.send_arm_control(data["left"]["q"], True)
                    self.send_arm_control(data["right"]["q"], False)
                elif msg_type == "lift_control":
                    self.send_lift_control(data["curr_height"], data["init_height"])
                elif msg_type == "left_controller_state":
                    self.react_on_left_controller_state(data)
                elif msg_type == "right_controller_state":
                    self.react_on_right_controller_state(data)
        except Exception as e:
            logger.error(f"[DUMMY] 错误: {e}")
        finally:
            self.clients.discard(websocket)
            logger.warning(f"[DUMMY] 客户端已断开: {websocket.remote_address}")

    async def websocket_handler(self):
        """启动 WebSocket 服务器"""
        logger.info(f"[DUMMY] WebSocket 服务器开始于 ws://{self.host}:{self.port}")
        server = await websockets.serve(self.handle_client, self.host, self.port)
        await server.wait_closed()

    def run(self):
        """运行服务器"""
        logger.info("[DUMMY] DummyRobotBridge 运行中 — 按 Ctrl+C 停止.")
        try:
            asyncio.run(self.websocket_handler())
        except KeyboardInterrupt:
            logger.error("[DUMMY] 服务器停止.")


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='DummyRobotBridge 服务器')
    parser.add_argument('--test', action='store_true', default=env_bool("TELEOP_DUMMY_TEST", False), help='启用测试模式，保存日志到文件')
    parser.add_argument('--host', default=env_str("TELEOP_ROBOT_BRIDGE_HOST", "localhost"), help='WebSocket 监听地址')
    parser.add_argument('--port', type=int, default=env_int("TELEOP_ROBOT_PORT", 5175), help='WebSocket 监听端口')
    
    args = parser.parse_args()
    
    # 创建并运行服务器，传入命令行参数
    DummyRobotBridge(host=args.host, port=args.port, test_mode=args.test).run()
