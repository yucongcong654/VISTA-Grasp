import time
import logging
import numpy as np
from pytransform3d import rotations

from pilot.kinematics import TransWrapper

from bridge.bot_interface import RealManRealRobot, RobotStateSyncClient

from pilot.manager import XRResourceManager, XRState

from communication.tserver import TeleopServer
from communication.rtcrelay import WebRTCRelay
from teleop_env import env_int, env_str

# logging.basicConfig(level=logging.INFO, 
#                     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# logger = logging.getLogger("Main Control Loop")


log_formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger = logging.getLogger("Main Control Loop")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.propagate = False

def calc_matries_from_xr_state(xr_state: XRState):

    if xr_state is None or xr_state.head is None:
        return None

    head_quat = xr_state.head.rotation
    head_p = xr_state.head.position

    if xr_state.isControllerMode:
        if xr_state.left_controller is None or xr_state.right_controller is None:
            return None
        left_quat = xr_state.left_controller.rotation
        left_p = xr_state.left_controller.position
        right_quat = xr_state.right_controller.rotation
        right_p = xr_state.right_controller.position
    else:
        if xr_state.left_hand is None or xr_state.right_hand is None:
            return None
        left_quat = xr_state.left_hand.rotation
        left_p = xr_state.left_hand.position
        right_quat = xr_state.right_hand.rotation
        right_p = xr_state.right_hand.position

    if head_quat is None or head_p is None or left_quat is None or left_p is None or right_quat is None or right_p is None:
        return None
    head_rmat = rotations.matrix_from_quaternion(
        [head_quat.w, head_quat.x, head_quat.y, head_quat.z]
    )
    left_rmat = rotations.matrix_from_quaternion(
        [left_quat.w, left_quat.x, left_quat.y, left_quat.z]
    )
    right_rmat = rotations.matrix_from_quaternion(
        [right_quat.w, right_quat.x, right_quat.y, right_quat.z]
    )
    head_mat = np.eye(4)
    head_mat[:3, :3] = head_rmat
    head_mat[:3, 3] = np.array([head_p.x, head_p.y, head_p.z])
    left_wrist_mat = np.eye(4)
    left_wrist_mat[:3, :3] = left_rmat
    left_wrist_mat[:3, 3] = np.array([left_p.x, left_p.y, left_p.z])
    right_wrist_mat = np.eye(4)
    right_wrist_mat[:3, :3] = right_rmat
    right_wrist_mat[:3, 3] = np.array([right_p.x, right_p.y, right_p.z])
    return head_mat, left_wrist_mat, right_wrist_mat


def is_position_in_range(xr_state: XRState):
    if xr_state is None or xr_state.head is None:
        return False, "无法获取VR头盔位置"
    
    head_p = xr_state.head.position
    
    if xr_state.isControllerMode:
        if xr_state.left_controller is None or xr_state.right_controller is None:
            return False, "无法获取手柄位置"
        left_p = xr_state.left_controller.position
        right_p = xr_state.right_controller.position
    else:
        if xr_state.left_hand is None or xr_state.right_hand is None:
            return False, "无法获取手部位置"
        left_p = xr_state.left_hand.position
        right_p = xr_state.right_hand.position
    
    # 这里的阈值需要根据实际情况调整
    max_horizontal_distance = 0.6
    min_vertical_distance = 0.2
    max_vertical_distance = 0.8
    
    # 头部到左手的水平距离
    left_horizontal_dist = np.sqrt((head_p.x - left_p.x)**2 + (head_p.z - left_p.z)**2)
    # 头部到右手的水平距离
    right_horizontal_dist = np.sqrt((head_p.x - right_p.x)**2 + (head_p.z - right_p.z)**2)
    # 头部到左手的垂直距离
    left_vertical_dist = head_p.y - left_p.y
    # 头部到右手的垂直距离
    right_vertical_dist = head_p.y - right_p.y
    
    # 检查是否所有距离都在合理范围内
    if (left_horizontal_dist > max_horizontal_distance or 
        right_horizontal_dist > max_horizontal_distance):
        return False, "手部水平距离过远，请将手靠近身体"
    
    if (left_vertical_dist < min_vertical_distance or 
        right_vertical_dist < min_vertical_distance):
        return False, "手部位置过高，请将手放低"
    
    if (left_vertical_dist > max_vertical_distance or 
        right_vertical_dist > max_vertical_distance):
        return False, "手部位置过低，请抬起手"
    
    # 检查左右手之间的距离是否合理
    hands_distance = np.sqrt(
        (left_p.x - right_p.x)**2 + 
        (left_p.y - right_p.y)**2 + 
        (left_p.z - right_p.z)**2
    )
    max_hands_distance = 0.8  # 左右手最大距离（米）
    min_hands_distance = 0.2  # 左右手最小距离（米）
    
    if hands_distance > max_hands_distance:
        return False, "左右手距离过远，请将手靠拢"
    
    if hands_distance < min_hands_distance:
        return False, "左右手距离过近，请将手分开"
    
    return True, "位置正确，请保持姿势"


def wait_for_stable_position(xr_manager, required_time=5.0):
    logger.info(f"等待用户进入并保持正确姿势 {required_time} 秒...")
    
    start_time = None
    last_message_time = 0
    message_interval = 1.0  # 消息提示间隔（秒）
    
    while True:
        xr_state = xr_manager.get_xr_state()
        in_range, message = is_position_in_range(xr_state)
        
        current_time = time.time()
        
        # 定期显示提示信息
        if current_time - last_message_time > message_interval:
            logger.info(message)
            last_message_time = current_time
        
        if in_range:
            if start_time is None:
                start_time = current_time
                logger.info(f"检测到正确姿势，开始计时...")
            
            elapsed_time = current_time - start_time
            if elapsed_time >= required_time:
                logger.info(f"用户已保持正确姿势 {required_time} 秒，准备开始控制")
                return True
            
            # 显示倒计时
            if current_time - last_message_time > message_interval:
                remaining = required_time - elapsed_time
                logger.info(f"请继续保持姿势，还需 {remaining:.1f} 秒")
        else:
            if start_time is not None:
                logger.info("姿势已改变，重新计时...")
                start_time = None
        
        time.sleep(0.1)


def main():
    import argparse
    import pinocchio as pin

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="日志记录、效率测试启动")
    args = parser.parse_args()    

    # 性能测试相关变量
    test_mode = args.test
    if test_mode:
        # 日志记录
        log_file_handler = logging.FileHandler('main_control_loop.log', mode='w')
        log_file_handler.setFormatter(log_formatter)
        logger.addHandler(log_file_handler)

    fps = env_int("TELEOP_CONTROL_FPS", 30)
    teleop_host = env_str("TELEOP_SERVER_HOST", "localhost")
    teleop_port = env_int("TELEOP_SERVER_PORT", 5174, aliases=("VITE_TELEOP_WS_PORT",))
    robot_host = env_str("TELEOP_ROBOT_HOST", "localhost")
    robot_port = env_int("TELEOP_ROBOT_PORT", 5175)

    teleop_server = TeleopServer(host=teleop_host, port=teleop_port)
    logger.debug(f"开启端口为 {teleop_port} 的发送操作信息的遥操服务器，实例化 Teleop_server : {teleop_server}")
    robot_client = RobotStateSyncClient(host=robot_host, port=robot_port)
    logger.debug(f"开启端口为 {robot_port} 的接收机器人消息的客户端，实例化 robot_client : {robot_client}")

    webrtc_relay = WebRTCRelay(teleop_server, robot_client)
    logger.debug(f"添加 发送操作信息的遥操服务器 teleop_server 与 接收机器人消息的客户端 robot_client ，实例化 webrtc_relay :{webrtc_relay}")
    xr_manager = XRResourceManager(server=teleop_server)
    logger.debug(f"将遥操服务器绑定到 XR 资源管理器，实例化 xr_manager : {xr_manager}")

    xr_manager.start()
    logger.info(f"XR 资源管理器启动")
    robot_client._start_daemon_tasks()
    logger.info(f"机器人消息客户端启动")

    xr_manager.wait_for_all_valid()
    logger.info(f"XR 资源管理器检查完毕，所有数据有效")
    robot_client.wait_for_connection()
    logger.info(f"机器人消息客户端连接完毕")
    robot = RealManRealRobot(robot_client)
    logger.info(f"将机器人消息客户端绑定在机器人上，实例化机器人对象 robot : {robot}")

    trans = TransWrapper()
    logger.debug(f"TransWrapper 实例化完成")
    
    # 在进入主控制循环前，等待用户进入并保持正确姿势
    logger.info("准备检查用户姿势...")
    # wait_for_stable_position(xr_manager, required_time=3.0)
    logger.info("跳过姿势检查，直接进入控制循环")
    logger.info("用户姿势检查通过，开始控制机器人")

    try:
        while True:
            start_time = time.time()
            logger.debug(f"循环开始，当前时间戳{start_time}")
            XRState = xr_manager.get_xr_state()
            logger.debug(f"XR 资源管理器获取XR 状态 : {XRState}")
            
            s = time.time()
            rlt = calc_matries_from_xr_state(XRState)
            e = time.time()
            if rlt is None:
                logger.warning(f"矩阵结果为空！")
                continue
            logger.info(f"通过 XRState 计算矩阵，结果为 : {rlt}, 耗时 {(e - s):.6f} 秒")
            
            head_mat, left_wrist_mat, right_wrist_mat = rlt
            logger.debug(f"矩阵结果分发 head_mat: {head_mat}, \nleft_wrist_mat: {left_wrist_mat}, right_wrist_mat: {right_wrist_mat}")
            
            s = time.time()
            (
                operator_head_rmat,
                operator_head_height,
                realman_left_wrist,
                realman_right_wrist,
            ) = trans.calc(head_mat, left_wrist_mat, right_wrist_mat)
            e = time.time()
            logger.info(f"计算出头部旋转矩阵 operator_head_rmat: {operator_head_rmat}, \n头部高度 operator_head_height: {operator_head_height}, \n睿尔曼左手腕 realman_left_wrist: {realman_left_wrist}, \n睿尔曼右手腕 realman_right_wrist: {realman_right_wrist}, 耗时 {(e - s):.6f} 秒")
            
            s = time.time()
            roll, pitch, yaw = pin.rpy.matrixToRpy(operator_head_rmat)
            e = time.time()
            logger.info(f"通过旋转矩阵计算出欧拉角 roll: {roll}, pitch: {pitch}, yaw: {yaw}, 耗时 {(e - s):.6f} 秒")
            pitch = -pitch
            

            robot.set_head_yaw_pitch(yaw, pitch)
            logger.info(f"设置机器人头部的偏航角和俯仰角\nyaw: {yaw}, pitch: {pitch}, \n耗时 {(e - s):.6f} 秒")
            
            
            s = time.time()
            robot.set_left_right_wrist(realman_left_wrist, realman_right_wrist)
            e = time.time()
            logger.info(f"设置机器人左右手腕的位姿\n左: \n{realman_left_wrist}, \n右: \n{realman_right_wrist}, \n解算耗时 {(e - s):.6f} 秒")
            
            
            if XRState.isControllerMode:
                logger.debug(f"XR 资源管理器处于控制器模式")
                robot.client.set_left_controller_state(XRState.left_controller.state.__dict__)
                logger.debug(f"设置机器人左手控制器的状态\n状态为 : {XRState.left_controller.state.__dict__}")
                robot.client.set_right_controller_state(XRState.right_controller.state.__dict__)
                logger.debug(f"设置机器人右手控制器的状态\n状态为 : {XRState.right_controller.state.__dict__}")
            else:
                logger.debug(f"XR 资源管理器处于手部模式")
                robot.client.set_left_hand_state(XRState.left_hand.state.__dict__)
                logger.debug(f"设置机器人左手的状态\n状态为 : {XRState.left_hand.state.__dict__}")
                robot.client.set_right_hand_state(XRState.right_hand.state.__dict__)
                logger.debug(f"设置机器人右手的状态\n状态为 : {XRState.right_hand.state.__dict__}")
            end_time = time.time()
            logger.info(f"循环结束，单次耗时{(end_time - start_time):.6f}秒")
            if 1 / fps - (end_time - start_time) > 0:
                logger.debug(f"定频中")
                time.sleep(1 / fps - (end_time - start_time))
    except KeyboardInterrupt:
        exit(0)

main()
