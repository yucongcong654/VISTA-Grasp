import logging
import time
import logging
import asyncio
import threading
from dataclasses import dataclass
from typing import Optional, Callable, List

from communication.tserver import TeleopServer
from pilot.components.head import (
    HeadReceiver, 
    HeadData
)
from pilot.components.controller import (
    ControllerReceiver,
    ControllerData
)
from pilot.components.hand import (
    HandReceiver, 
    HandData
)
from teleop_env import env_str

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("XRResourceManager")

@dataclass
class XRState:
    head: Optional[HeadData] = None
    left_controller: Optional[ControllerData] = None
    right_controller: Optional[ControllerData] = None
    left_hand: Optional[HandData] = None
    right_hand: Optional[HandData] = None
    isControllerMode: bool = True
    timestamp: Optional[float] = None
    all_valid: bool = False

class XRResourceManager:
    def __init__(self, server: TeleopServer = None,):
        # Create server
        self.server = server

        # Components
        self.head_receiver: Optional[HeadReceiver] = None
        self.controller_receiver: Optional[ControllerReceiver] = None
        self.hand_receiver: Optional[HandReceiver] = None

        # Current state
        self.current_state = XRState()

        # Default Mode
        self.isControllerMode = env_str("TELEOP_MODE", "controller_mode") != "hand_mode"

        # Thread synchronization
        self._lock = threading.RLock()

        # Callbacks for state changes
        self.state_callbacks: List[Callable[[XRState], None]] = []

        # Thread control
        self.running = False
        self.xr_thread = None
        self._loop = None

    async def _setup_components(self):
        # Initialize head receiver
        self.head_receiver = HeadReceiver(self.server)
        self.head_receiver.register_callback(self._on_head_data)

        # Set Up the Controller or Hand 
        if self.isControllerMode:
            self.controller_receiver = ControllerReceiver(self.server)
            self.controller_receiver.register_callback(
                self._on_controller_data, "left_controller"
            )
            self.controller_receiver.register_callback(
                self._on_controller_data, "right_controller"
            )
        else:        # Init hand receiver
            self.hand_receiver = HandReceiver(self.server)
            self.hand_receiver.register_callback(
                self._on_hand_data, "left_hand"
            )
            self.hand_receiver.register_callback(
                self._on_hand_data, "right_hand"
            )

        logger.info("XR 组件初始化完成")

    def _on_head_data(self, data: HeadData):
        with self._lock:
            self.current_state.head = data
            self.current_state.timestamp = data.timestamp
            if not self.current_state.all_valid:
                if (
                    (self.current_state.left_controller
                    and self.current_state.right_controller)
                    or
                    (self.current_state.left_hand
                    and self.current_state.right_hand)
                ):
                    self.current_state.all_valid = True
                if (self.isControllerMode):
                    if (self.current_state.left_controller and self.current_state.right_controller):
                        self.current_state.all_valid = True
                else:
                    if (self.current_state.left_hand and self.current_state.right_hand):
                        self.current_state.all_valid = True

        # Notify state change
        # self._notify_state_change()

        logger.debug("手部数据已更新")

    def _on_controller_data(self, data: ControllerData):
        with self._lock:
            if data.isLeft:
                self.current_state.left_controller = data
            else:
                self.current_state.right_controller = data
            if not self.current_state.all_valid:
                self.current_state.all_valid = (
                    self.current_state.left_controller is not None
                    and self.current_state.right_controller is not None
                    and self.current_state.head is not None
                )
            self.current_state.timestamp = data.timestamp

        # Notify state change
        self._notify_state_change()

        logger.debug(f"{'左' if data.isLeft else '右'} 控制器数据已更新")

    def _on_hand_data(self, data: HandData):
        with self._lock:
            if data.isLeft:
                self.current_state.left_hand = data
            else:
                self.current_state.right_hand = data
            if not self.current_state.all_valid:
                self.current_state.all_valid = (
                    self.current_state.left_hand is not None
                    and self.current_state.right_hand is not None
                    and self.current_state.head is not None
                )
            self.current_state.timestamp = data.timestamp

        # Notify state change
        self._notify_state_change()

        logger.debug(f"{'左' if data.is_left else '右'} 手部数据已更新")

    def _notify_state_change(self):
        state_copy = None
        with self._lock:
            state_copy = XRState(
                head=self.current_state.head,
                left_controller=self.current_state.left_controller,
                right_controller=self.current_state.right_controller,
                left_hand=self.current_state.left_hand,
                right_hand=self.current_state.right_hand,
                timestamp=self.current_state.timestamp,
            )

        for callback in self.state_callbacks:
            try:
                callback(state_copy)
            except Exception as e:
                logger.error(f"执行状态改变回调错误: {str(e)}")

    async def _run_server(self):
        try:
            await self.server.start_server()
            logger.info(f"XR 服务器开始于 {self.server.host}:{self.server.port}")
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("XR 服务器任务已取消")
        except Exception as e:
            logger.error(f"XR 服务器错误: {str(e)}")
        finally:
            if self.head_receiver:
                self.head_receiver.cleanup()
            if self.controller_receiver:
                self.controller_receiver.cleanup()
            if self.hand_receiver:
                self.hand_receiver.cleanup()
            await self.server.stop_server()
            logger.info("XR 服务器停止")

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        setup_task = self._loop.create_task(self._setup_components())
        self._loop.run_until_complete(setup_task)
        server_task = self._loop.create_task(self._run_server())

        try:
            self._loop.run_until_complete(server_task)
        except Exception as e:
            logger.error(f"XR 事件循环错误: {str(e)}")
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
            self._loop.close()
            logger.info("XR 事件循环关闭")

    def start(self):
        if self.running:
            logger.warning("XR 资源管理器已经在运行")
            return
        self.running = True
        self.xr_thread = threading.Thread(target=self._run_event_loop, name="XRThread")
        self.xr_thread.daemon = True
        self.xr_thread.start()

        logger.info("XR 资源管理器启动")

    def stop(self):
        if not self.running:
            logger.warning("XR Resource Manager 不在运行")
            return

        self.running = False
        if self.xr_thread and self.xr_thread.is_alive():
            self.xr_thread.join(timeout=5)

        logger.info("XR Resource Manager 停止")

    def register_state_callback(self, callback: Callable[[XRState], None]) -> str:

        callback_id = f"state_callback_{id(callback)}"
        self.state_callbacks.append(callback)
        logger.debug(f"已注册的状态回调 {callback_id}")
        return callback_id

    def unregister_state_callback(self, callback: Callable[[XRState], None]) -> bool:
        if callback in self.state_callbacks:
            self.state_callbacks.remove(callback)
            logger.debug("未注册的状态的回调")
            return True
        return False

    def get_xr_state(self) -> XRState:
        with self._lock:
            return XRState(
                head=self.current_state.head,
                left_controller=self.current_state.left_controller,
                right_controller=self.current_state.right_controller,
                left_hand=self.current_state.left_hand,
                right_hand=self.current_state.right_hand,
                isControllerMode = self.isControllerMode,
                timestamp=self.current_state.timestamp,
                all_valid=self.current_state.all_valid,
            )

    def get_head_state(self) -> Optional[HeadData]:
        with self._lock:
            return self.current_state.head

    def get_left_controller_state(self) -> Optional[ControllerData]:
        with self._lock:
            return self.current_state.left_controller

    def get_right_controller_state(self) -> Optional[ControllerData]:
        with self._lock:
            return self.current_state.right_controller

    def get_left_hand_state(self) -> Optional[HandData]:
        with self._lock:
            return self.current_state.left_hand

    def get_right_hand_state(self) -> Optional[HandData]:
        with self._lock:
            return self.current_state.right_hand

    def wait_for_all_valid(self):
        logger.debug("持续等待所有数据有效")
        while not self.current_state.all_valid:
            time.sleep(0.1)
