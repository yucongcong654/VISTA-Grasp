from isaacgym import gymapi
from isaacgym import gymutil
from isaacgym import gymtorch
import numpy as np
import torch
from pathlib import Path
import time, math
from dataclasses import dataclass
from typing import Dict, Optional, List


@dataclass
class AssetInfo:
    actor: "gymapi.Actor" # type: ignore
    actor_idx: int
    dof: int
    active_dof_indices: Optional[np.ndarray]

class Sim:
    def __init__(self,
                 print_freq=False):
        self.print_freq = print_freq
        self.head_rmat = None

        # initialize gym
        self.gym = gymapi.acquire_gym()

        # configure sim
        sim_params = gymapi.SimParams()
        sim_params.dt = 1 / 60
        sim_params.substeps = 2
        sim_params.up_axis = gymapi.UP_AXIS_Z
        sim_params.gravity = gymapi.Vec3(0.0, 0.0, -9.81)
        sim_params.physx.solver_type = 1
        sim_params.physx.num_position_iterations = 4
        sim_params.physx.num_velocity_iterations = 1
        sim_params.physx.max_gpu_contact_pairs = 8388608
        sim_params.physx.contact_offset = 0.002
        sim_params.physx.friction_offset_threshold = 0.001
        sim_params.physx.friction_correlation_distance = 0.0005
        sim_params.physx.rest_offset = 0.0
        sim_params.physx.use_gpu = True
        sim_params.use_gpu_pipeline = False

        self.sim = self.gym.create_sim(0, 0, gymapi.SIM_PHYSX, sim_params)
        if self.sim is None:
            print("*** Failed to create sim")
            quit()

        plane_params = gymapi.PlaneParams()
        plane_params.distance = 0.0
        plane_params.normal = gymapi.Vec3(0.0, 0.0, 1.0)
        self.gym.add_ground(self.sim, plane_params)

        # load table asset
        table_asset_options = gymapi.AssetOptions()
        table_asset_options.disable_gravity = True
        table_asset_options.fix_base_link = True
        table_asset = self.gym.create_box(self.sim, 0.8, 0.8, 0.1, table_asset_options)

        # load cube asset
        cube_asset_options = gymapi.AssetOptions()
        cube_asset_options.density = 10
        cube_asset = self.gym.create_box(self.sim, 0.05, 0.05, 0.05, cube_asset_options)
        dirpath = Path(__file__).resolve().parent
        asset_root = dirpath/"../assets"
        left_asset_path = "inspire_hand/inspire_hand_left.urdf"
        right_asset_path = "inspire_hand/inspire_hand_right.urdf"
        asset_options = gymapi.AssetOptions()
        asset_options.fix_base_link = True
        asset_options.default_dof_drive_mode = gymapi.DOF_MODE_POS
        left_asset = self.gym.load_asset(self.sim, str(asset_root), left_asset_path, asset_options)
        right_asset = self.gym.load_asset(self.sim, str(asset_root), right_asset_path, asset_options)
        self.dof = self.gym.get_asset_dof_count(left_asset)

        # set up the env grid
        num_envs = 1
        num_per_row = int(math.sqrt(num_envs))
        env_spacing = 1.25
        env_lower = gymapi.Vec3(-env_spacing, 0.0, -env_spacing)
        env_upper = gymapi.Vec3(env_spacing, env_spacing, env_spacing)
        np.random.seed(0)
        self.env = self.gym.create_env(self.sim, env_lower, env_upper, num_per_row)

        # table
        # pose = gymapi.Transform()
        # pose.p = gymapi.Vec3(0, 0, 1.2)
        # pose.r = gymapi.Quat(0, 0, 0, 1)
        # table_handle = self.gym.create_actor(self.env, table_asset, pose, 'table', 0)
        # color = gymapi.Vec3(0.5, 0.5, 0.5)
        # self.gym.set_rigid_body_color(self.env, table_handle, 0, gymapi.MESH_VISUAL_AND_COLLISION, color)

        # # cube
        # pose = gymapi.Transform()
        # pose.p = gymapi.Vec3(0, 0, 1.25)
        # pose.r = gymapi.Quat(0, 0, 0, 1)
        # cube_handle = self.gym.create_actor(self.env, cube_asset, pose, 'cube', 0)
        # color = gymapi.Vec3(1, 0.5, 0.5)
        # self.gym.set_rigid_body_color(self.env, cube_handle, 0, gymapi.MESH_VISUAL_AND_COLLISION, color)

        # left_hand
        pose = gymapi.Transform()
        pose.p = gymapi.Vec3(-0.6, 0, 1.6)
        pose.r = gymapi.Quat(0, 0, 0, 1)
        self.left_handle = self.gym.create_actor(self.env, left_asset, pose, 'left', 1, 1)
        self.gym.set_actor_dof_states(self.env, self.left_handle, np.zeros(self.dof, gymapi.DofState.dtype),
                                      gymapi.STATE_ALL)
        self.left_idx = self.gym.get_actor_index(self.env, self.left_handle, gymapi.DOMAIN_SIM)

        # right_hand
        pose = gymapi.Transform()
        pose.p = gymapi.Vec3(-0.6, 0, 1.6)
        pose.r = gymapi.Quat(0, 0, 0, 1)
        self.right_handle = self.gym.create_actor(self.env, right_asset, pose, 'right', 1, 1)
        self.gym.set_actor_dof_states(self.env, self.right_handle, np.zeros(self.dof, gymapi.DofState.dtype),
                                      gymapi.STATE_ALL)
        self.right_idx = self.gym.get_actor_index(self.env, self.right_handle, gymapi.DOMAIN_SIM)


        # create default viewer
        self.viewer = self.gym.create_viewer(self.sim, gymapi.CameraProperties())
        if self.viewer is None:
            print("*** Failed to create viewer")
            quit()
        cam_pos = gymapi.Vec3(1, 1, 2)
        cam_target = gymapi.Vec3(0, 0, 1)
        self.gym.viewer_camera_look_at(self.viewer, None, cam_pos, cam_target)

        self.cam_lookat_offset = np.array([1, 0, 0])
        self.left_cam_offset = np.array([0, 0.033, 0])
        self.right_cam_offset = np.array([0, -0.033, 0])
        self.cam_pos = np.array([-0.6, 0, 1.6])

        # create left 1st preson viewer
        camera_props = gymapi.CameraProperties()
        camera_props.width = 1280
        camera_props.height = 720
        self.left_camera_handle = self.gym.create_camera_sensor(self.env, camera_props)
        self.gym.set_camera_location(self.left_camera_handle,
                                     self.env,
                                     gymapi.Vec3(*(self.cam_pos + self.left_cam_offset)),
                                     gymapi.Vec3(*(self.cam_pos + self.left_cam_offset + self.cam_lookat_offset)))

        # create right 1st preson viewer
        camera_props = gymapi.CameraProperties()
        camera_props.width = 1280
        camera_props.height = 720
        self.right_camera_handle = self.gym.create_camera_sensor(self.env, camera_props)
        self.gym.set_camera_location(self.right_camera_handle,
                                     self.env,
                                     gymapi.Vec3(*(self.cam_pos + self.right_cam_offset)),
                                     gymapi.Vec3(*(self.cam_pos + self.right_cam_offset + self.cam_lookat_offset)))

        self.additional_assets: Dict[str, AssetInfo] = {} # 
        
    def add_actor(self,name:str, init_p: np.ndarray, init_q: np.ndarray, asset_root:str ,asset_path: str, asset_options: gymapi.AssetOptions, joint_names_to_control: Optional[List] = None):
        assert init_p.shape == (3,)
        assert init_q.shape == (4,)
        assert asset_path.endswith(".urdf")
        assert asset_options is not None
        assert name not in self.additional_assets
        asset = self.gym.load_asset(self.sim, asset_root,asset_path, asset_options)
        pose = gymapi.Transform()
        pose.p = gymapi.Vec3(*init_p.tolist())
        pose.r = gymapi.Quat(*init_q.tolist())
        actor = self.gym.create_actor(self.env, asset, pose, name, 1, 1)
        dof = self.gym.get_asset_dof_count(asset)
        active_dof_indices = None # if None then all dofs are active
        if joint_names_to_control is not None:
            dof_props = self.gym.get_actor_dof_properties(self.env, actor)
            # 获取关节数量
            total_dof_count = self.gym.get_asset_dof_count(asset)
            dof_name2_idx = {self.gym.get_asset_dof_name(asset, i):i for i in range(total_dof_count)}
            dof_indices_to_control = [dof_name2_idx[name] for name in joint_names_to_control]
            for i in range(total_dof_count):
                dof_props["driveMode"][i] = gymapi.DOF_MODE_POS if i in dof_indices_to_control else gymapi.DOF_MODE_NONE
            self.gym.set_actor_dof_properties(self.env, actor, dof_props) 
            active_dof_indices = np.array(dof_indices_to_control)

        self.gym.set_actor_dof_states(self.env, self.right_handle, np.zeros(dof, gymapi.DofState.dtype),
                                      gymapi.STATE_ALL)
        actor_idx = self.gym.get_actor_index(self.env, actor, gymapi.DOMAIN_SIM)
        self.additional_assets[name] = AssetInfo(actor, actor_idx, dof, active_dof_indices)
        
    def set_actor_status(self, name: str, pose: Optional[np.ndarray], qpose: np.ndarray):
        assert name in self.additional_assets
        if pose is not None:
            raise NotImplementedError
        actor = self.additional_assets[name].actor
        dof = self.additional_assets[name].dof
        active_dof_indices = self.additional_assets[name].active_dof_indices
        states = np.zeros(dof, dtype=gymapi.DofState.dtype)
        if self.additional_assets[name].active_dof_indices is not None:
            states["pos"][active_dof_indices] = qpose
        else:
            states['pos'] = qpose
        self.gym.set_actor_dof_states(self.env, actor, states, gymapi.STATE_POS)
        
    
    def finish_setup(self):    
        self.root_state_tensor = self.gym.acquire_actor_root_state_tensor(self.sim)
        self.gym.refresh_actor_root_state_tensor(self.sim)
        self.root_states = gymtorch.wrap_tensor(self.root_state_tensor)
        self.left_root_states = self.root_states[self.left_idx]
        self.right_root_states = self.root_states[self.right_idx]

    def set_internal_status(self, head_rmat, left_pose, right_pose, left_qpos, right_qpos):
        self.head_rmat = head_rmat

        self.left_root_states[0:7] = torch.tensor(left_pose, dtype=float)
        self.right_root_states[0:7] = torch.tensor(right_pose, dtype=float)
        self.gym.set_actor_root_state_tensor(self.sim, gymtorch.unwrap_tensor(self.root_states))

        left_states = np.zeros(self.dof, dtype=gymapi.DofState.dtype)
        left_states['pos'] = left_qpos
        self.gym.set_actor_dof_states(self.env, self.left_handle, left_states, gymapi.STATE_POS)

        right_states = np.zeros(self.dof, dtype=gymapi.DofState.dtype)
        right_states['pos'] = right_qpos
        self.gym.set_actor_dof_states(self.env, self.right_handle, right_states, gymapi.STATE_POS)
    
    def step(self):
        if self.print_freq:
            start = time.time()
        assert self.head_rmat is not None
        # step the physics
        self.gym.simulate(self.sim)
        self.gym.fetch_results(self.sim, True)
        self.gym.step_graphics(self.sim)
        self.gym.render_all_camera_sensors(self.sim)
        self.gym.refresh_actor_root_state_tensor(self.sim)

        curr_lookat_offset = self.cam_lookat_offset @ self.head_rmat.T
        curr_left_offset = self.left_cam_offset @ self.head_rmat.T
        curr_right_offset = self.right_cam_offset @ self.head_rmat.T

        self.gym.set_camera_location(self.left_camera_handle,
                                     self.env,
                                     gymapi.Vec3(*(self.cam_pos + curr_left_offset)),
                                     gymapi.Vec3(*(self.cam_pos + curr_left_offset + curr_lookat_offset)))
        self.gym.set_camera_location(self.right_camera_handle,
                                     self.env,
                                     gymapi.Vec3(*(self.cam_pos + curr_right_offset)),
                                     gymapi.Vec3(*(self.cam_pos + curr_right_offset + curr_lookat_offset)))
        left_image = self.gym.get_camera_image(self.sim, self.env, self.left_camera_handle, gymapi.IMAGE_COLOR)
        right_image = self.gym.get_camera_image(self.sim, self.env, self.right_camera_handle, gymapi.IMAGE_COLOR)
        left_image = left_image.reshape(left_image.shape[0], -1, 4)[..., :3]
        right_image = right_image.reshape(right_image.shape[0], -1, 4)[..., :3]

        self.gym.draw_viewer(self.viewer, self.sim, True)
        self.gym.sync_frame_time(self.sim)
        if self.print_freq:
            end = time.time()
            print('Frequency:', 1 / (end - start))
        return left_image, right_image

    def end(self):
        self.gym.destroy_viewer(self.viewer)
        self.gym.destroy_sim(self.sim)
