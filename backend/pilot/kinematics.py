import numpy as np
import casadi
import pinocchio as pin
from typing import Tuple
from pinocchio import casadi as cpin
from pinocchio.visualize import MeshcatVisualizer

from pilot.utils.mat_tool import mat_update, fast_mat_inv
from pilot.utils.weighted_moving_filter import WeightedMovingFilter

class DualArmIk:
    DIST_WRIST_COMPENSATION = 0.0

    def __init__(self, urdf_filepath: str, assets_dirpath: str, Visualization=False, calc_tau=False, apply_filter=False):
        np.set_printoptions(precision=5, suppress=True, linewidth=200)
        self.Visualization = Visualization
        self.calc_tau = calc_tau
        self.apply_filter = apply_filter
        self.robot = pin.RobotWrapper.BuildFromURDF(urdf_filepath, assets_dirpath)
        if Visualization:
            data = self.robot.model.createData()
            q = pin.neutral(self.robot.model)
            pin.forwardKinematics(self.robot.model, data, q)
            pin.updateFramePlacements(self.robot.model, data)
            for i, frame in enumerate(self.robot.model.frames):
                print(f"{i}: {frame.name}")
                print(f"Pose: {data.oMf[i].translation.T}")
                print(f"Rotation: {data.oMf[i].rotation}")
        self.active_joint_names = [
            "l_joint1", 
            "l_joint2", 
            "l_joint3", 
            "l_joint4", 
            "l_joint5", 
            "l_joint6", 
            "l_joint7", 
            "r_joint1", 
            "r_joint2", 
            "r_joint3", 
            "r_joint4", 
            "r_joint5", 
            "r_joint6", 
            "r_joint7",
        ]
        self.mixed_jointsToLockIDs = [
            "platform_joint", 
            "head_joint1", 
            "head_joint2", 
            "joint_left_wheel", 
            "joint_right_wheel", 
            "joint_swivel_wheel_1_1", 
            "joint_swivel_wheel_1_2", 
            "joint_swivel_wheel_2_1", 
            "joint_swivel_wheel_2_2",
            "joint_swivel_wheel_3_1", 
            "joint_swivel_wheel_3_2",
            "joint_swivel_wheel_4_1", 
            "joint_swivel_wheel_4_2",
        ]
        self.reduced_robot = self.robot.buildReducedRobot(
            list_of_joints_to_lock=self.mixed_jointsToLockIDs,
            reference_configuration=np.zeros(self.robot.model.nq),
        )
        # 添加末端执行器帧
        self.reduced_robot.model.addFrame(
            pin.Frame("L_ee",
                      self.reduced_robot.model.getJointId("l_joint7"),
                      pin.SE3(pin.rpy.rpyToMatrix(0, 0, 0),
                              np.array([0, 0, -self.DIST_WRIST_COMPENSATION]).T),
                      pin.FrameType.OP_FRAME)
        )
        self.reduced_robot.model.addFrame(
            pin.Frame("R_ee",
                      self.reduced_robot.model.getJointId("r_joint7"),
                      pin.SE3(pin.rpy.rpyToMatrix(0, 0, 0),
                              np.array([0, 0, -self.DIST_WRIST_COMPENSATION]).T),
                      pin.FrameType.OP_FRAME)
        )
        # Casadi 模型
        self.cmodel = cpin.Model(self.reduced_robot.model)
        self.cdata = self.cmodel.createData()
        self.diff_ik_data = self.reduced_robot.model.createData()
        # 符号变量
        self.cq = casadi.SX.sym("q", self.reduced_robot.model.nq, 1)
        self.cTf_l = casadi.SX.sym("tf_l", 4, 4)
        self.cTf_r = casadi.SX.sym("tf_r", 4, 4)
        cpin.framesForwardKinematics(self.cmodel, self.cdata, self.cq)
        self.L_hand_id = self.reduced_robot.model.getFrameId("L_ee")
        self.R_hand_id = self.reduced_robot.model.getFrameId("R_ee")
        self.translational_error = casadi.Function("translational_error",
                                                    [self.cq, self.cTf_l, self.cTf_r],
                                                    [casadi.vertcat(
                                                        self.cdata.oMf[self.L_hand_id].translation - self.cTf_l[:3, 3],
                                                        self.cdata.oMf[self.R_hand_id].translation - self.cTf_r[:3, 3]
                                                    )])
        self.rotational_error = casadi.Function("rotational_error",
                                                 [self.cq, self.cTf_l, self.cTf_r],
                                                 [casadi.vertcat(
                                                     cpin.log3(self.cdata.oMf[self.L_hand_id].rotation @ self.cTf_l[:3, :3].T),
                                                     cpin.log3(self.cdata.oMf[self.R_hand_id].rotation @ self.cTf_r[:3, :3].T)
                                                 )])
        # 构造优化问题
        self.opti = casadi.Opti()
        self.var_q = self.opti.variable(self.reduced_robot.model.nq)
        self.var_q_last = self.opti.parameter(self.reduced_robot.model.nq)
        self.param_tf_l = self.opti.parameter(4, 4)
        self.param_tf_r = self.opti.parameter(4, 4)
        self.translational_cost = casadi.sumsqr(self.translational_error(self.var_q, self.param_tf_l, self.param_tf_r))
        self.rotation_cost = casadi.sumsqr(self.rotational_error(self.var_q, self.param_tf_l, self.param_tf_r))
        self.regularization_cost = casadi.sumsqr(self.var_q)
        self.smooth_cost = casadi.sumsqr(self.var_q - self.var_q_last)
        self.opti.subject_to(
            self.opti.bounded(self.reduced_robot.model.lowerPositionLimit,
                              self.var_q,
                              self.reduced_robot.model.upperPositionLimit)
        )
        self.opti.minimize(
            50 * self.translational_cost +
            self.rotation_cost +
            0.02 * self.regularization_cost +
            0.1 * self.smooth_cost
        )
        opts = {
            "ipopt": {"print_level": 0, "max_iter": 50, "tol": 1e-3},
            "print_time": False,
            "calc_lam_p": False,
        }
        self.opti.solver("ipopt", opts)
        self.init_data = np.zeros(self.reduced_robot.model.nq)
        self.smooth_filter = WeightedMovingFilter(np.array([0.4, 0.3, 0.2, 0.1]), 14)
        self.vis = None
        if self.Visualization:
            self.vis = MeshcatVisualizer(self.reduced_robot.model,
                                          self.reduced_robot.collision_model,
                                          self.reduced_robot.visual_model)
            self.vis.initViewer(open=True, zmq_url="tcp://127.0.0.1:6000")
            self.vis.loadViewerModel("pinocchio")
            frame_id_2_idx = {frame.name: idx for idx, frame in enumerate(self.reduced_robot.model.frames)}
            frame_ids_to_vis = [frame_id_2_idx[frame] for frame in {"l_joint7", "r_joint7", "L_ee", "R_ee"}]
            self.vis.displayFrames(True, frame_ids=frame_ids_to_vis, axis_length=0.15, axis_width=5)
            self.vis.display(pin.neutral(self.reduced_robot.model))

    def scale_arms(self, human_left_pose, human_right_pose, human_arm_length=0.60, robot_arm_length=0.75):
        scale_factor = robot_arm_length / human_arm_length
        robot_left_pose = human_left_pose.copy()
        robot_right_pose = human_right_pose.copy()
        robot_left_pose[:3, 3] *= scale_factor
        robot_right_pose[:3, 3] *= scale_factor
        return robot_left_pose, robot_right_pose

    def solve_ik(self, left_wrist, right_wrist, current_lr_arm_motor_q=None, current_lr_arm_motor_dq=None) -> Tuple[np.ndarray, np.ndarray]:
        if current_lr_arm_motor_q is not None:
            self.init_data = current_lr_arm_motor_q
        left_wrist, right_wrist = self.scale_arms(left_wrist, right_wrist)
        if self.Visualization:
            self.vis.viewer["L_ee_target"].set_transform(left_wrist)
            self.vis.viewer["R_ee_target"].set_transform(right_wrist)
        try:
            self.opti.set_initial(self.var_q, self.init_data)
            self.opti.set_value(self.param_tf_l, left_wrist)
            self.opti.set_value(self.param_tf_r, right_wrist)
            self.opti.set_value(self.var_q_last, self.init_data)
            sol = self.opti.solve()
            sol_q = self.opti.value(self.var_q)
            if self.apply_filter:
                self.smooth_filter.add_data(sol_q)
                sol_q = self.smooth_filter.filtered_data
            self.init_data = sol_q
            if self.calc_tau:
                if current_lr_arm_motor_dq is not None:
                    v = current_lr_arm_motor_dq * 0.0
                else:
                    v = (sol_q - self.init_data) * 0.0
                sol_tauff = pin.rnea(self.reduced_robot.model,
                                      self.reduced_robot.data,
                                      sol_q,
                                      v,
                                      np.zeros(self.reduced_robot.model.nv))
            else:
                sol_tauff = None
            if self.Visualization:
                self.vis.display(sol_q)
            return sol_q, sol_tauff
        except Exception as e:
            print(f"ERROR in convergence: {e}")
            if hasattr(self, "last_good_solution") and self.last_good_solution is not None:
                sol_q = self.last_good_solution
            else:
                sol_q = self.init_data.copy()
            if self.apply_filter:
                self.smooth_filter.add_data(sol_q)
                sol_q = self.smooth_filter.filtered_data
            self.init_data = sol_q
            if self.calc_tau:
                if current_lr_arm_motor_dq is not None:
                    v = current_lr_arm_motor_dq * 0.0
                else:
                    v = (sol_q - self.init_data) * 0.0
                sol_tauff = pin.rnea(self.reduced_robot.model,
                                      self.reduced_robot.data,
                                      sol_q,
                                      v,
                                      np.zeros(self.reduced_robot.model.nv))
            else:
                sol_tauff = None
            if self.Visualization:
                self.vis.display(sol_q)
            return sol_q, sol_tauff

    def solve_differential_ik(self, left_wrist, right_wrist, current_q):
        if current_q is None:
            current_q = self.init_data
        left_wrist, right_wrist = self.scale_arms(left_wrist, right_wrist)
        if not hasattr(self, "damping"):
            self.damping = 0.1
        pin.forwardKinematics(self.reduced_robot.model, self.diff_ik_data, current_q)
        pin.updateFramePlacements(self.reduced_robot.model, self.diff_ik_data)
        left_pos_error = left_wrist[:3, 3] - self.diff_ik_data.oMf[self.L_hand_id].translation
        right_pos_error = right_wrist[:3, 3] - self.diff_ik_data.oMf[self.R_hand_id].translation
        left_J = pin.computeFrameJacobian(self.reduced_robot.model, self.diff_ik_data, current_q, self.L_hand_id)[:3]
        right_J = pin.computeFrameJacobian(self.reduced_robot.model, self.diff_ik_data, current_q, self.R_hand_id)[:3]
        J = np.vstack([left_J, right_J])
        error = np.concatenate([left_pos_error, right_pos_error])
        lambda_sq = self.damping**2
        J_pinv = J.T @ np.linalg.inv(J @ J.T + lambda_sq * np.eye(6))
        dq = J_pinv @ error
        step_size = 0.5
        new_q = current_q + step_size * dq
        new_q = np.clip(new_q, self.reduced_robot.model.lowerPositionLimit, self.reduced_robot.model.upperPositionLimit)
        if self.Visualization:
            self.vis.display(new_q)
        self.init_data = new_q
        return new_q, None

T_to_unitree_left_wrist = np.array([[0, 0, 1, 0],
                                    [0, 1, 0, 0],
                                    [-1, 0, 0, 0],
                                    [0, 0, 0, 1]])
T_to_unitree_right_wrist = np.array([[0, 0, 1, 0],
                                     [0, 1, 0, 0],
                                     [-1, 0, 0, 0],
                                     [0, 0, 0, 1]])
T_RealmanHead = np.array([[0, 1, 0, 0],
                          [-1, 0, 0, -0.23843],
                          [0, 0, 1, 1.441],
                          [1, 0, 0, 1]])
T_to_unitree_hand = np.array([[0, 0, 1, 0],
                              [-1, 0, 0, 0],
                              [0, -1, 0, 0],
                              [0, 0, 0, 1]])
T_robot_openxr = np.array([[0, 0, -1, 0],
                           [-1, 0, 0, 0],
                           [0, 1, 0, 0],
                           [0, 0, 0, 1]])
const_head_vuer_mat = np.array([[1, 0, 0, 0],
                                [0, 1, 0, 1.5],
                                [0, 0, 1, -0.2],
                                [0, 0, 0, 1]])
const_right_wrist_vuer_mat = np.array([[1, 0, 0, 0.15],
                                       [0, 1, 0, 1.13],
                                       [0, 0, 1, -0.3],
                                       [0, 0, 0, 1]])
const_left_wrist_vuer_mat = np.array([[1, 0, 0, -0.15],
                                      [0, 1, 0, 1.13],
                                      [0, 0, 1, -0.3],
                                      [0, 0, 0, 1]])

class TransWrapper:
    def __init__(self):
        pass
    def calc(self, head_vuer_mat: np.ndarray, left_wrist_vuer_mat: np.ndarray, right_wrist_vuer_mat: np.ndarray):

        head_vuer_mat, head_flag = mat_update(const_head_vuer_mat, head_vuer_mat.copy())
        left_wrist_vuer_mat, left_wrist_flag  = mat_update(const_left_wrist_vuer_mat,left_wrist_vuer_mat.copy())
        right_wrist_vuer_mat, right_wrist_flag = mat_update(const_right_wrist_vuer_mat, right_wrist_vuer_mat.copy())

        
        head_mat = T_robot_openxr @ head_vuer_mat @ fast_mat_inv(T_robot_openxr)
        left_wrist_mat  = T_robot_openxr @ left_wrist_vuer_mat @ fast_mat_inv(T_robot_openxr)
        right_wrist_mat = T_robot_openxr @ right_wrist_vuer_mat @ fast_mat_inv(T_robot_openxr)

        unitree_left_wrist = left_wrist_mat @ (T_to_unitree_left_wrist if left_wrist_flag else np.eye(4))
        unitree_right_wrist = right_wrist_mat @ (T_to_unitree_right_wrist if right_wrist_flag else np.eye(4))

        unitree_left_wrist[0:3, 3]  = unitree_left_wrist[0:3, 3] - head_mat[0:3, 3]
        unitree_right_wrist[0:3, 3] = unitree_right_wrist[0:3, 3] - head_mat[0:3, 3]


        head_rmat = head_mat[:3, :3]
        unitree_left_wrist_in_realman = T_RealmanHead@unitree_left_wrist
        unitree_right_wrist_in_realman = T_RealmanHead@unitree_right_wrist
        return head_rmat, head_mat[2,3] ,unitree_left_wrist_in_realman , unitree_right_wrist_in_realman