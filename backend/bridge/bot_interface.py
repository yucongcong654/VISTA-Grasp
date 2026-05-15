import asyncio
import json
import time
import threading
import websockets
import numpy as np
from pathlib import Path
from abc import ABC, abstractmethod
from typing import List, Union, Dict, Callable
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bot_interface.py")



class RobotStateSyncClient:
    def __init__(self, host: str, port: int):
        self.url = f"ws://{host}:{port}"
        self.websocket = None
        self.img = None
        self.l_arm_q = None
        self.r_arm_q = None
        self.head_yaw = None
        self.head_pitch = None
        self.curr_height = None
        self.init_height = None
        self.left_controller_state = None
        self.right_controller_state = None
        self.left_hand_state = None
        self.right_hand_state = None
        self.arm_state = None  # 来自真实机器人的数据
        self.thread = None

        self._message_queues: Dict[str, List[asyncio.Queue]] = {}
        self._message_callbacks: Dict[str, List[Callable[[dict], None]]] = {}

    def register_queue(self, msg_type: str, queue: asyncio.Queue) -> None:
        self._message_queues.setdefault(msg_type, []).append(queue)

    def register_callback(self, msg_type: str, callback: Callable[[dict], None]) -> None:
        self._message_callbacks.setdefault(msg_type, []).append(callback)

    def wait_for_connection(self):
        while self.websocket is None:
            time.sleep(0.1)

    def get_image(self):
        return self.img

    def set_head_yaw_pitch(self, yaw, pitch):
        self.head_yaw = yaw
        self.head_pitch = pitch

    def set_height(self, curr_height, init_height):
        self.curr_height = curr_height
        self.init_height = init_height

    def get_head_yaw_pitch_data(self):
        if self.head_yaw is None or self.head_pitch is None:
            return None
        return {"type": "head_control", "data": {"yaw": self.head_yaw, "pitch": self.head_pitch}}

    def set_left_arm_q(self, q: Union[np.ndarray, list]):
        if isinstance(q, np.ndarray):
            q = q.tolist()
        self.l_arm_q = q

    def get_left_right_arm_q_data(self):
        if self.l_arm_q is None or self.r_arm_q is None:
            return None
        return {"type": "l_r_arm_control", "data": {"left": {"q": self.l_arm_q}, "right": {"q": self.r_arm_q}}}

    def get_height_data(self):
        if self.curr_height is None or self.init_height is None:
            return None
        return {"type": "lift_control", "data": {"curr_height": self.curr_height, "init_height": self.init_height}}

    def set_right_arm_q(self, q: Union[np.ndarray, list]):
        if isinstance(q, np.ndarray):
            q = q.tolist()
        self.r_arm_q = q

    def set_left_controller_state(self, state: dict):
        self.left_controller_state = state

    def get_left_controller_state_data(self):
        if self.left_controller_state is None:
            return None
        return {"type": "left_controller_state", "data": self.left_controller_state}

    def set_right_controller_state(self, state: dict):
        self.right_controller_state = state

    def get_right_controller_state_data(self):
        if self.right_controller_state is None:
            return None
        return {"type": "right_controller_state", "data": self.right_controller_state}
    
    def set_left_hand_state(self, state: dict):
        self.left_hand_state = state

    def get_left_hand_state_data(self):
        if self.left_hand_state is None:
            return None
        return {"type": "left_hand_state", "data": self.left_hand_state}

    def set_right_hand_state(self, state: dict):
        self.right_hand_state = state

    def get_right_hand_state_data(self):
        if self.right_hand_state is None:
            return None
        return {"type": "right_hand_state", "data": self.right_hand_state}

    async def connect(self):
        logger.debug(f"正在连接到{self.url}")
        self.websocket = await websockets.connect(self.url, close_timeout=20)
        if self.websocket is None:
            exit("Failed to connect to server")
        logger.info(f"已连接到{self.url}")

    async def receive_messages(self):
        async for message in self.websocket:
            try:
                message = json.loads(message)

                queues = self._message_queues.get(message["type"], [])
                for q in queues:
                    for q in queues:
                        await q.put(message)
                
                for cb in self._message_callbacks.get(message.get("type"), []):
                    result = cb(message)
                    if asyncio.iscoroutinefunction(cb):
                        await result
                if message["type"] == "sensor":
                    # 处理传感器数据
                    pass
                elif message["type"] == "arm_state":
                    self.arm_state = message["data"]
                
                
            except Exception as e:
                logger.error(f"接收信息错误: {e}")

    async def send_control_commands(self):
        while True:
            try:
                start_time = time.time()
                head_data = self.get_head_yaw_pitch_data()
                if head_data:
                    await self.websocket.send(json.dumps(head_data))
                arm_data = self.get_left_right_arm_q_data()
                if arm_data:
                    await self.websocket.send(json.dumps(arm_data))
                height_data = self.get_height_data()
                if height_data:
                    await self.websocket.send(json.dumps(height_data))
                left_controller_state_data = self.get_left_controller_state_data()
                if left_controller_state_data:
                    await self.websocket.send(json.dumps(left_controller_state_data))
                right_controller_state_data = self.get_right_controller_state_data()
                if right_controller_state_data:
                    await self.websocket.send(json.dumps(right_controller_state_data))
                elapsed_time = time.time() - start_time
                await asyncio.sleep(max(0.1 - elapsed_time, 0))
            except websockets.ConnectionClosed:
                logger.warning("WebSocket 连接关闭")
                break
            except Exception as e:
                logger.error(f"发送控制命令错误: {e}")

    async def run(self):
        try:
            await self.connect()
            receive_task = asyncio.create_task(self.receive_messages())
            send_task = asyncio.create_task(self.send_control_commands())
            await asyncio.gather(receive_task, send_task)
        except Exception as e:
            logger.error(f"WebSocket客户端错误: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()
                logger.warning("WebSocket连接关闭")

    def _start_daemon_tasks(self):
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.run())
            loop.close()
        thread = threading.Thread(target=run_async_loop, daemon=True)
        thread.start()
        self.thread = thread

    def stop(self):
        async def close_websocket():
            if self.websocket:
                await self.websocket.close()
                logger.info("调用客户端 stop 方法, WebSocket 连接关闭")
        if self.websocket:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(close_websocket())
            finally:
                loop.close()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
                logger.info("调用客户端 stop 方法, 客户端线程停止")

class Robot(ABC):
    def __init__(self, robot_urdf_path: str, assets_dirpath: str):
        super().__init__()
        # 初始化逆运动学求解器（算法部分放在 kinematics 模块中，此处直接引用）
        from pilot.kinematics import DualArmIk  # 根据实际路径调整
        self.ik_solver = DualArmIk(robot_urdf_path, assets_dirpath)
        self.curr_arm_q = None  # 真实机器人当前关节角度，用于 IK 求解的初始化
        self.curr_arm_dq = None

    def set_left_right_wrist(self, left_wrist: np.ndarray, right_wrist: np.ndarray):
        self.left_wrist = left_wrist
        sol_q, sol_tauff = self.ik_solver.solve_ik(left_wrist, right_wrist, self.curr_arm_q, self.curr_arm_dq)
        self.send_q_tauff(sol_q, sol_tauff)

    @abstractmethod
    def get_images(self) -> List[np.ndarray]:
        """返回当前获取的图像"""
        pass

    @abstractmethod
    def send_q_tauff(self, sol_q: np.ndarray, sol_tauff: np.ndarray):
        """将计算得到的关节角度（以及力矩）发送给机器人"""
        pass

    @abstractmethod
    def stop(self):
        """停止机器人控制"""
        pass

class RealManRobotConfig:
    _current_dir = Path(__file__).parent.parent
    assets_dirpath = str((_current_dir / "pilot" / "assets" / "realman").resolve())
    urdf_rel_path = "urdf/overseas_75_b_v_description.urdf"
    urdf_abs_path = str((Path(assets_dirpath) / urdf_rel_path).resolve())

class RealManRealRobot(Robot, RealManRobotConfig):
    def __init__(self, client: RobotStateSyncClient):
        super().__init__(self.urdf_abs_path, self.assets_dirpath)
        self.client = client

    def send_q_tauff(self, sol_q: np.ndarray, sol_tauff: np.ndarray):
        self.client.set_left_arm_q(sol_q[:7])
        self.client.set_right_arm_q(sol_q[7:])

    def set_head_yaw_pitch(self, yaw: float, pitch: float):
        self.client.set_head_yaw_pitch(yaw, pitch)

    def set_height(self, curr_height: float, init_height: float):
        self.client.set_height(curr_height, init_height)

    def get_images(self):
        return [self.client.get_image()]

    def set_left_right_wrist(self, left_wrist: np.ndarray, right_wrist: np.ndarray):
        self.curr_arm_q = self.client.arm_state  # 获取当前关节角度（如果有）
        super().set_left_right_wrist(left_wrist, right_wrist)

    def stop(self):
        self.client.stop()
