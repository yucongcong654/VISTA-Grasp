// ../store/useWebRTCVideoPlayer.ts
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

export function useWebRTCVideoTexture(streamId: string, signallingServerUrl: string): { 
  videoTexture: THREE.VideoTexture | null, 
  isReady: boolean,
  latencyMs: number | null;
} {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const textureRef = useRef<THREE.VideoTexture | null>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const offerIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  useEffect(() => {
    // 创建 video 元素
    const video = document.createElement('video');
    video.playsInline = true;
    video.autoplay = true;
    video.muted = true;
    video.style.display = 'none';
    document.body.appendChild(video);
    videoRef.current = video;

    // 创建视频纹理
    const texture = new THREE.VideoTexture(video);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.format = THREE.RGBAFormat;
    textureRef.current = texture;

    // 视频播放成功，则置 ready 状态
    video.onloadedmetadata = () => {
      video.play()
        .then(() => {
          setIsReady(true);
        })
        .catch((error) => {
          console.error('播放视频错误:', error);
        });
    };

    // 建立 WebSocket 和 RTCPeerConnection
    const ws = new WebSocket(signallingServerUrl);
    websocketRef.current = ws;

    const pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.miwifi.com:3478' }],
    });
    peerConnectionRef.current = pc;

    // 保留 ICE candidate 的详细发送逻辑
    pc.onicecandidate = (event) => {
      if (event.candidate && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'webrtc',
          action: 'ice_candidate',
          streamId,
          candidate: {
            component: event.candidate.component === 'rtp' ? 1 : 2,
            foundation: event.candidate.foundation,
            ip: event.candidate.address,
            port: event.candidate.port,
            priority: event.candidate.priority,
            protocol: event.candidate.protocol,
            type: event.candidate.type,
            relatedAddress: event.candidate.relatedAddress,
            relatedPort: event.candidate.relatedPort,
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            tcpType: event.candidate.tcpType,
          }
        }));
      }
    };

    // 绑定视频 track
    pc.ontrack = (event) => {
      if (videoRef.current && event.streams && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0];
      }
    };

    // 创建并发送 offer 的函数
    const createAndSendOffer = async () => {
      if (peerConnectionRef.current && websocketRef.current?.readyState === WebSocket.OPEN) {
        try {
          const offer = await peerConnectionRef.current.createOffer({ offerToReceiveVideo: true });
          await peerConnectionRef.current.setLocalDescription(offer);
          websocketRef.current.send(JSON.stringify({
            type: 'webrtc',
            action: 'offer',
            streamId,
            sdp: peerConnectionRef.current.localDescription
          }));
        } catch (error) {
          console.error('创建WebRTC Offer错误:', error);
        }
      }
    };

    ws.onopen = () => {
      // 发送一个 offer
      createAndSendOffer();
    };

    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.action === 'answer' && message.streamId === streamId) {
          // 收到 answer 后停止发送 offer
          if (offerIntervalRef.current) {
            clearInterval(offerIntervalRef.current);
            offerIntervalRef.current = null;
          }
          await pc.setRemoteDescription(new RTCSessionDescription(message.sdp));
        }
      } catch (error) {
        console.error('处理WebRTC信息错误:', error);
      }
    };

    // WebRTC 延迟
    const statsTimer = setInterval(async () => {
      const pc = peerConnectionRef.current;
      if (!pc) return;
      try {
        const stats = await pc.getStats();
        for (const report of stats.values()) {
          if (report.type === 'candidate-pair' && report.state === 'succeeded') {
            // 当进入这里的时候，说明已经建立了连接
            const rtt = report.currentRoundTripTime * 1000; // ms
            setLatencyMs(rtt / 2);  // 近似单向延迟
          }
        }
      } catch (e) {
        console.warn('getStats 错误', e);
      }
    }, 1000);

    return () => {
      clearInterval(statsTimer);
      if (offerIntervalRef.current) {
        clearInterval(offerIntervalRef.current);
      }
      if (videoRef.current) {
        document.body.removeChild(videoRef.current);
      }
      textureRef.current?.dispose();
      peerConnectionRef.current?.close();
      websocketRef.current?.close();
    };
  }, [streamId, signallingServerUrl]);

  return { 
    videoTexture: textureRef.current, 
    isReady,
    latencyMs
  };
}
