import sys
import os
parent_dirpath = os.path.dirname(os.path.abspath(__file__))
sys.path.append(parent_dirpath)

import argparse
import threading
import json
import cv2
import rospy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import websockets
import asyncio
import numpy as np
from typing import List
from geometry_msgs.msg import Twist, Vector3
from servo_ros.msg import ServoMove,ServoAngle
from dual_arm_msgs.msg import MoveJ_P , MoveJ,Lift_Height,Lift_Speed, JointPos
from std_msgs.msg import Float32, Float64
from sensor_msgs.msg import JointState

import numpy as np
from cam.bot_message import WebRTCOfferMsg, WebRTCIceCandidateMsg, WebRTCAnswerMsg
from cam.rtc import RTCManager
from cam.track import ROSVideoTrack


import logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# logger = logging.getLogger("teleop_ros_bridge.py/ROSBridgeServer")

log_formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log_file_handler = logging.FileHandler('ros_bridge_server.log', mode='w')
log_file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("teleop_ros_bridge.py/ROSBridgeServer")
logger.setLevel(logging.DEBUG)
logger.addHandler(log_file_handler)
logger.addHandler(console_handler)
logger.propagate = False


_ENV_LOADED = False


def _env_file_candidates():
    explicit_env_file = os.environ.get("TELEOP_ENV_FILE")
    if explicit_env_file:
        yield os.path.expanduser(explicit_env_file)

    for start in (parent_dirpath, os.getcwd()):
        current = os.path.abspath(start)
        while True:
            yield os.path.join(current, ".env")
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent


def _parse_env_value(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if " #" in value:
        return value.split(" #", 1)[0].rstrip()
    return value


def _load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    for env_path in _env_file_candidates():
        if not os.path.isfile(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, raw_value = line.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = _parse_env_value(raw_value)
        break
    _ENV_LOADED = True


def _env_str(name, default):
    _load_env()
    return os.environ.get(name) or default


def _env_int(name, default):
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_bool(name, default):
    value = _env_str(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default



class ROSBridgeServer:
    topic_name_foot_img = _env_str('TELEOP_CAMERA1_TOPIC', '/camera_1/color/image_raw')
    topic_name_head_img = _env_str('TELEOP_CAMERA0_TOPIC', '/camera_0/color/image_raw')
    topic_name_head_control = _env_str('TELEOP_HEAD_CONTROL_TOPIC', '/servo_control/move')
    topic_name_head_control_yaw_pitch = _env_str('TELEOP_HEAD_CONTROL_YAW_PITCH_TOPIC', '/servo_control/move_double')
    topic_name_lift_control = _env_str('TELEOP_LIFT_CONTROL_TOPIC', '/l_arm/rm_driver/Lift_SetHeight')
    topic_name_lift_speed_control = _env_str('TELEOP_LIFT_SPEED_CONTROL_TOPIC', '/l_arm/rm_driver/Lift_SetSpeed')
    topic_name_l_arm_control = _env_str('TELEOP_LEFT_ARM_CONTROL_TOPIC', '/l_arm/rm_driver/JointPos')
    topic_name_l_hand_control = _env_str('TELEOP_LEFT_HAND_CONTROL_TOPIC', "/rx_gripper_control")
    topic_name_r_arm_control = _env_str('TELEOP_RIGHT_ARM_CONTROL_TOPIC', '/r_arm/rm_driver/JointPos')
    topic_name_r_gripper = _env_str('TELEOP_RIGHT_GRIPPER_CONTROL_TOPIC', '/gripper_control')
    topic_name_underpan_control = _env_str('TELEOP_UNDERPAN_CONTROL_TOPIC', '/base_cmd_vel')
    topic_name_l_arm_state = _env_str('TELEOP_LEFT_ARM_STATE_TOPIC', '/l_arm/joint_states')
    topic_name_r_arm_state = _env_str('TELEOP_RIGHT_ARM_STATE_TOPIC', '/r_arm/joint_states')
    head_pitch_number_min_max = (0,1000) # refer to msg
    head_pitch_radian_min_max = (-60/180*np.pi, 60/180*np.pi)
    head_yaw_number_min_max = (0,1000)
    head_yaw_radian_min_max = (-80/180*np.pi, 80/180*np.pi)
    # lift_height_min_max = (10,2600)
    lift_height_min_max = (2000, 2600)

    def __init__(self, host=None, port=None, no_head=False):
        self.host = host or _env_str("TELEOP_ROBOT_BRIDGE_HOST", "localhost")
        self.port = port if port is not None else _env_int("TELEOP_ROBOT_PORT", 5175)
        self.clients = set()
        self.bridge = CvBridge()

        # ROS1 初始化
        rospy.init_node("ros_bridge_server", anonymous=True)

        # ROS1 订阅者
        # self.head_img_sub  = rospy.Subscriber(self.topic_name_head_img, Image, self.image_callback)
        # 当不需要测试手臂时, 请注释掉以下代码
        self.l_arm_state_sub  = rospy.Subscriber(self.topic_name_l_arm_state, JointState, self.l_arm_state_callback)
        self.r_arm_state_sub  = rospy.Subscriber(self.topic_name_r_arm_state, JointState, self.r_arm_state_callback)
         
        # ROS1 发布者
        self.head_control = rospy.Publisher(self.topic_name_head_control,ServoMove, queue_size=1)
        self.head_control2 = rospy.Publisher(self.topic_name_head_control_yaw_pitch, ServoAngle, queue_size=1)
        self.lift_control = rospy.Publisher(self.topic_name_lift_control,Lift_Height, queue_size=1)
        self.lift_speed_control = rospy.Publisher(self.topic_name_lift_speed_control,Lift_Speed,queue_size=1)
        self.l_arm_control = rospy.Publisher(self.topic_name_l_arm_control,JointPos, queue_size=1)
        self.l_hand_control = rospy.Publisher(self.topic_name_l_hand_control,Float64, queue_size=1)
        self.r_gripper_control = rospy.Publisher(self.topic_name_r_gripper,Float64, queue_size=1)
        self.r_arm_control = rospy.Publisher(self.topic_name_r_arm_control,JointPos, queue_size=1)
        self.underpan_control = rospy.Publisher(self.topic_name_underpan_control, Twist, queue_size=1)

        # 数据缓冲区
        self.latest_image = None
        self.latest_sensor_data = None
        self.latest_l_arm_state = None
        self.latest_r_arm_state = None

        # WebSocket 服务器线程
        self.rtc = RTCManager(self._send_via_ws)

        self.server_thread = threading.Thread(target=self.start_websocket_server)
        self.server_thread.daemon = True
        self.last_send_lift_height = None # range 10 - 2600
        self.last_trigger_send_height = None

        self.no_head = no_head

    def image_callback(self, msg):
        """ROS1 图像话题回调函数"""
        try:
            self.latest_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            rospy.logerr(f"Failed to convert image: {e}")
    def l_arm_state_callback(self, msg):
        """ROS1 传感器话题回调函数"""  
        self.latest_l_arm_state = msg.position
    
    def r_arm_state_callback(self, msg):
        """ROS1 传感器话题回调函数"""  
        self.latest_r_arm_state = msg.position

    def sensor_callback(self, msg):
        """ROS1 传感器话题回调函数"""
        self.latest_sensor_data = msg.data

    def send_head_control(self, yaw: float, pitch:float):
        def calc_yaw_output(yaw):
            yaw = np.clip(yaw, *self.head_yaw_radian_min_max)
            yaw_output= (yaw - self.head_yaw_radian_min_max[0] )/(self.head_yaw_radian_min_max[1] - self.head_yaw_radian_min_max[0])
            final_yaw_output = yaw_output*(self.head_yaw_number_min_max[1]-self.head_yaw_number_min_max[0])+ self.head_yaw_number_min_max[0]
            logger.info(f"yaw: {yaw_output}, {final_yaw_output}")
            return final_yaw_output

        def calc_pitch_output(pitch):
            pitch = np.clip(pitch, *self.head_pitch_radian_min_max)
            pitch_output= (pitch - self.head_pitch_radian_min_max[0] )/(self.head_pitch_radian_min_max[1] - self.head_pitch_radian_min_max[0])
            final_pitch_output = pitch_output*(self.head_pitch_number_min_max[1]-self.head_pitch_number_min_max[0])+ self.head_pitch_number_min_max[0]
            logger.info(f"pitch: {pitch_output}, {final_pitch_output}")
            return final_pitch_output

        # 方式一
        # move_msg1 = ServoMove()
        # move_msg1.servo_id = 1 #pitch
        # move_msg1.angle = int(calc_pitch_output(pitch))
        # move_msg2 = ServoMove()
        # move_msg2.servo_id = 2 # yaw
        # move_msg2.angle = int(calc_yaw_output(yaw))
        # self.head_control.publish(move_msg1)
        # self.head_control.publish(move_msg2)
        # logger.debug(f"给机器人的 head_control 公布了 move_msg1 : {move_msg1}")
        # logger.debug(f"给机器人的 head_control 公布了 move_msg2 : {move_msg2}")
        #方式二
        move_msg = ServoAngle()
        move_msg.servo_id_1 = 1
        move_msg.angle_1 = int(calc_pitch_output(pitch))
        move_msg.servo_id_2 = 2
        move_msg.angle_2 = int(calc_yaw_output(yaw))
        self.head_control2.publish(move_msg)
        logger.info(f"给机器人的 head_control 公布了 move_msg : {move_msg}")
        



    def send_lift_control(self, curr_height: float, init_height: float): 
        def calc_lift_output(curr_height, init_height):
            if self.last_send_lift_height is None:
                return self.lift_height_min_max[1] 
            if curr_height> init_height:
                return None
            if self.last_trigger_send_height is None or curr_height - self.last_send_lift_height < .04:
                return None
            diff = init_height - curr_height
            lift_output = self.lift_height_min_max[1] - diff   
            lift_output = np.clip(lift_output, *self.lift_height_min_max)
            return lift_output
        lift_output = calc_lift_output(curr_height, init_height)
        if lift_output is None:
            return
        lift_msg = Lift_Height()
        lift_msg.height = int(lift_output)
        lift_msg.speed = 100
        self.lift_control.publish(lift_msg)
        logger.debug(f"给机器人的 lift_control 公布了 lift_msg : {lift_msg}")
        self.last_send_lift_height = lift_output
        self.last_trigger_send_height = curr_height
    
    def send_lift_speed_control(self, speed: float):
        control_msg = Lift_Speed()
        control_msg.speed = int(speed)
        self.lift_speed_control.publish(control_msg)
        logger.debug(f"给机器人的 lift_speed_control 公布了 control_msg : {control_msg}")

    def send_left_hand_control(self,ratio:float):  
        control_msg = Float64()
        control_msg.data = ratio
        self.l_hand_control.publish(control_msg)
        logger.debug(f"给机器人的 l_hand_control 公布了 control_msg : {control_msg}")

    def send_right_gripper_control(self,ratio:float):  
        control_msg = Float64()
        control_msg.data = 1 - ratio #  乐白是反的
        self.r_gripper_control.publish(control_msg)
        logger.debug(f"给机器人的 r_gripper_control 公布了 control_msg : {control_msg}")

    def react_on_left_controller_state(self, data):
        def move_robot(x, y):
            self.underpan_control.publish(Twist(linear=Vector3(x,0,0), angular=Vector3(0,0,y)))
            logger.debug(f"给机器人的 underpan_control 公布了 msg : Twist(linear=Vector3(x,0,0), angular=Vector3(0,0,y))")
            pass

        def hand_control(ratio):
            self.send_left_hand_control(ratio)

        if "thumbstickValue" in data:
            move_robot(-data["thumbstickValue"][1]*0.2, -data["thumbstickValue"][0]*0.2)

        if "triggerValue" in data:        
            hand_control(data["triggerValue"])

    def react_on_right_controller_state(self, data):
        def move_up_down(y):
            if abs(y) < 0.1:
                y = 0
            y = -50*y
            self.send_lift_speed_control(y)
        def control_gripper(ratio):
            self.send_right_gripper_control(ratio)
            
        if "thumbstickValue" in data:
            move_up_down(data["thumbstickValue"][1])

        if "triggerValue" in data:
            control_gripper(data["triggerValue"])

    def send_arm_control(self, q_list: List[float],is_left_arm: bool):
        # 测试moveJ 左臂回到零点，单位是弧度。
        assert len(q_list) == 7
        joint_pose = JointPos()
        joint_pose.joint = q_list
        if is_left_arm:
            self.l_arm_control.publish(joint_pose)
            logger.info(f"给机器人的 l_arm_control 公布了 joint_pose : {joint_pose}")
            pass
        else:
            self.r_arm_control.publish(joint_pose)
            logger.info(f"给机器人的 r_arm_control 公布了 joint_pose : {joint_pose}")
            pass
        rospy.loginfo("Published MoveJ Command to /l_arm/MoveJ_Cmd")

    def start_websocket_server(self):
        """启动 WebSocket 服务端"""
        asyncio.new_event_loop().run_until_complete(self.websocket_handler())

    async def _send_via_ws(self, msg):
        if isinstance(msg, WebRTCAnswerMsg):
            payload = {
                "type": "webrtc",
                "action": msg.action,     
                "streamId": msg.streamId,  
                "sdp": msg.sdp,
            }
        elif isinstance(msg, WebRTCIceCandidateMsg):
            payload = {
                "type": "webrtc",
                "action": msg.action,      # "ice_candidate"
                "streamId": msg.streamId,
                "candidate": msg.candidate,  # WebRTCCandidate 对象或 dict
            }
        else:
            # 如果未来还有别的 msg 类型，也可以 fallback 到 msg.__dict__ 或者抛错
            payload = msg.__dict__

        text = json.dumps(payload)
        await asyncio.gather(*(client.send(text) for client in self.clients), return_exceptions=True)

    async def websocket_handler(self):
        """WebSocket 服务端处理逻辑"""
        async def handle_client(websocket):
            self.clients.add(websocket)
            rospy.loginfo(f"客户端已连接: {websocket.remote_address}")
            try:
                async for message in websocket:
                    # 接收客户端控制指令并转发到 ROS1
                    control_command = json.loads(message)
                    if control_command["type"] == "head_control":
                        data = control_command["data"]
                        yaw = data["yaw"]
                        pitch = data["pitch"]
                        if not self.no_head:
                            self.send_head_control(yaw, pitch)
                        rospy.loginfo(f"send head yaw, pitch  {(yaw,pitch)}")
                    # if control_command["type"] == "lift_control":
                    #     data = control_command["data"]
                    #     curr_height = data["curr_height"]
                    #     init_height = data["init_height"]
                    #     self.send_lift_control(curr_height,init_height)
                    #     rospy.loginfo(f"send lift height: {curr_height}")
                    if control_command["type"] == "l_r_arm_control":
                        data = control_command["data"]
                        l_q = data["left"]["q"]
                        r_q = data["right"]["q"]
                        self.send_arm_control(l_q,True)
                        self.send_arm_control(r_q,False)
                        rospy.loginfo(f"send l_q: {l_q}, r_q: {r_q}")
                    if control_command["type"] == "left_controller_state":
                        data = control_command["data"]
                        if data:
                            self.react_on_left_controller_state(data)
                    if control_command["type"] == "right_controller_state":
                        data = control_command["data"]
                        if data:
                            self.react_on_right_controller_state(data)
                    if control_command["type"] == "webrtc":
                        if control_command["action"] == "offer":
                            offer = WebRTCOfferMsg(
                                streamId=control_command["streamId"],
                                sdp={"sdp": control_command["sdp"], "type": "offer"}
                            )
                            if offer.streamId == "camera0":
                                tn = self.topic_name_head_img
                            elif offer.streamId == "camera1":
                                tn = self.topic_name_foot_img
                            # 如需添加更多摄像头，添加 elif 语句，将tn绑定到对应的 ROS 话题
                            else:
                                tn = None
                                raise RuntimeError(f"你传入的streamId什么鬼 offer.streamId：{offer.streamId}")
                            await self.rtc.handle_offer(offer, lambda sid: ROSVideoTrack(self.bridge, tn))
                        elif control_command["action"] == "ice_candidate":
                            ice = WebRTCIceCandidateMsg(
                                streamId=control_command["streamId"],
                                candidate=control_command["candidate"]
                            )
                            await self.rtc.handle_ice_candidate(ice)

            except websockets.ConnectionClosed:
                rospy.loginfo(f"客户端断开连接: {websocket.remote_address}")
                self.clients.remove(websocket)
            except Exception as e:
                rospy.logerr(f"处理客户端错误,  详细: {e}, 客户端将会断开连接")

        async def send_data_to_clients():
            """向所有客户端发送最新的图像和传感器数据"""
            while not rospy.is_shutdown():
                if self.clients:
                    # 发送图像数据
                    if self.latest_image is not None:
                        _, buffer = cv2.imencode(".jpg", self.latest_image)
                        image_data = buffer.tobytes()
                        message = json.dumps({"type": "image", "data": image_data.hex()})
                        await asyncio.gather(*(client.send(message) for client in self.clients), return_exceptions=True)
                    if self.latest_l_arm_state is not None and self.latest_r_arm_state is not None:
                        message = json.dumps({"type": "arm_state", "data": self.latest_l_arm_state + self.latest_r_arm_state})
                        await asyncio.gather(*(client.send(message) for client in self.clients))

                    # 发送传感器数据
                    if self.latest_sensor_data is not None:
                        message = json.dumps({"type": "sensor", "data": self.latest_sensor_data})
                        await asyncio.gather(*(client.send(message) for client in self.clients))

                await asyncio.sleep(0.1)  # 控制发送频率

        # 启动 WebSocket 服务端
        server = await websockets.serve(handle_client, self.host, self.port)
        rospy.loginfo(f"WebSocket server started on ws://{self.host}:{self.port}")

        # 启动数据发送任务
        await send_data_to_clients()

        # 等待 WebSocket 服务端关闭
        await server.wait_closed()

    def run(self):
        """运行 ROS Bridge 服务端"""
        # 启动 WebSocket 服务器线程
        self.server_thread.start()

        # 保持 ROS1 节点运行
        rospy.spin()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=_env_str("TELEOP_ROBOT_BRIDGE_HOST", "localhost"), help="WebSocket 监听地址")
    parser.add_argument("--port", type=int, default=_env_int("TELEOP_ROBOT_PORT", 5175), help="WebSocket 监听端口")
    parser.add_argument("--nohead", action="store_true", default=_env_bool("TELEOP_ROBOT_NO_HEAD", False), help="不启用头部控制")
    args = parser.parse_args()

    logger.info(f"是否启用头部控制: not args.nohead = {not args.nohead}")

    server = ROSBridgeServer(host=args.host, port=args.port, no_head=args.nohead)
    server.run()
