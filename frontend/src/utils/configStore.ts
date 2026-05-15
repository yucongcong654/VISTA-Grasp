import { create } from 'zustand';
import {getCurrentWebPort} from './url'

// Define head tracking configuration interface
export interface HeadTrackConfig {
  fps: number;
  positionThreshold?: number;
  rotationThreshold?: number;
}

// Define controller tracking configuration interface
export interface ControllerTrackConfig {
  fps: number;
}
export interface HandTrackConfig {
  fps: number;
}

// Define VideoContainerConfig interface
export interface VideoContainerConfig {
  enabled: boolean;
  streamId?: string;
  streamIds?: string[];
  signallingServer?: string;
  width?: number;
  height?: number;
  distance?: number;
  numSmallVideos?: number,
  position?: [number, number, number];
  rotation?: [number, number, number];
}

export type TeleopMode = 'hand_mode' | 'controller_mode';


// 定义配置类型
export interface TeleopRemoteConfig {
  // remote config naming convention
  head_track_cfg?: HeadTrackConfig;
  controller_track_cfg?: ControllerTrackConfig;
  hand_track_cfg?: HandTrackConfig;
  video_container_cfg?: VideoContainerConfig;
  mode?: TeleopMode ; // Restricted to only 'hand_mode' or 'controller_mode'
  // 添加其他需要的配置选项
}
export interface TeleopLocalConfig {
  websocketPort: number;
  shouldReconnect: boolean;
  reconnectInterval: number;
  reconnectAttempts: number;
}

interface ConfigState {
  configRemote?: TeleopRemoteConfig;
  configLocal: TeleopLocalConfig;
  setRemoteConfig: (config: TeleopRemoteConfig) => void;
  updateLocalConfig: (partialConfig: Partial<TeleopLocalConfig>) => void;
  setWebsocketPort: (port: number) => void;
}

export const useConfigStore = create<ConfigState>((set) => ({
  configLocal: {
    websocketPort: getCurrentWebPort(),
    shouldReconnect: true,
    reconnectInterval: 1000,
    reconnectAttempts: 120
  },
  setRemoteConfig: (config: TeleopRemoteConfig) => set({ configRemote: config }),
  updateLocalConfig: (partialConfig: Partial<TeleopLocalConfig>) => {
    return set((state) => ({ configLocal: { ...state.configLocal, ...partialConfig }, configRemoteSet: true }));
  },
  setWebsocketPort: (port: number) => set((state) => ({
    configLocal: { ...state.configLocal, websocketPort: port }
  }))
}));
