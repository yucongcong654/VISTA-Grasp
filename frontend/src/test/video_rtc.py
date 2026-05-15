import asyncio
import cv2
import numpy as np
import json
import time
import threading
from multiprocessing import shared_memory
from dataclasses import dataclass
import logging
from typing import Dict, Optional, Tuple, List, Any
import queue
import uuid
import fractions

# aiortc imports
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("video_rtc")

@dataclass
class RTCVideoConfig:
    width: int = 640
    height: int = 480
    fps: int = 30
    format: str = "bgr24"  # Format of the video frame
    bitrate: int = 2000000  # 2 Mbps
    stream_id: str = "camera0"

class VideoFrameBuffer:
    """Manages a shared memory buffer for video frames"""
    
    def __init__(self, width: int, height: int, format: str = "bgr24"):
        self.width = width
        self.height = height
        self.format = format
        
        # Calculate buffer size based on format
        if format == "bgr24":
            # 3 bytes per pixel (Blue, Green, Red)
            self.bytes_per_pixel = 3
        elif format == "rgba":
            # 4 bytes per pixel (Red, Green, Blue, Alpha)
            self.bytes_per_pixel = 4
        elif format == "gray8":
            # 1 byte per pixel (grayscale)
            self.bytes_per_pixel = 1
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        self.buffer_size = width * height * self.bytes_per_pixel
        
        # Create shared memory
        self.shm = shared_memory.SharedMemory(create=True, size=self.buffer_size)
        self.buffer = np.ndarray((height, width, self.bytes_per_pixel), 
                                 dtype=np.uint8, buffer=self.shm.buf)
        
        # Frame metadata
        self.frame_count = 0
        self.last_update_time = time.time()
        
        logger.info(f"Created shared memory buffer: {width}x{height}, format={format}, size={self.buffer_size} bytes")
    
    def update_frame(self, frame: np.ndarray) -> None:
        """Update the buffer with a new frame"""
        if frame.shape[:2] != (self.height, self.width):
            # Resize if dimensions don't match
            frame = cv2.resize(frame, (self.width, self.height))
        
        # Ensure format matches
        if self.format == "bgr24" and frame.shape[2] == 3:
            pass  # Already in BGR format
        elif self.format == "rgba" and frame.shape[2] == 3:
            # Convert BGR to RGBA
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        elif self.format == "gray8" and frame.shape[2] == 3:
            # Convert BGR to grayscale
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame = frame.reshape(self.height, self.width, 1)
        
        # Copy frame to shared memory
        np.copyto(self.buffer, frame)
        
        self.frame_count += 1
        self.last_update_time = time.time()
    
    def get_frame(self) -> np.ndarray:
        """Get the current frame from the buffer"""
        return self.buffer.copy()
    
    def close(self) -> None:
        """Close and clean up the shared memory"""
        self.shm.close()
        self.shm.unlink()
        logger.info(f"Closed shared memory buffer after {self.frame_count} frames")


class BufferVideoStreamTrack(VideoStreamTrack):
    """
    A video stream track that reads from a VideoFrameBuffer.
    """
    
    def __init__(self, buffer: VideoFrameBuffer, fps: int):
        super().__init__()
        self.buffer = buffer
        self.fps = fps
        self.frame_time = fractions.Fraction(1, fps)
        self.pts = 0
        self.frame_count = 0
        
        # Convert format for PyAV
        if buffer.format == "bgr24":
            self.format = "bgr24"
        elif buffer.format == "rgba":
            self.format = "rgba"
        elif buffer.format == "gray8":
            self.format = "gray"
        else:
            raise ValueError(f"Unsupported format for VideoStreamTrack: {buffer.format}")
    
    async def recv(self) -> VideoFrame:
        """
        Return a frame from the buffer.
        """
        # Calculate the time to wait until the next frame should be sent
        frame_duration = 1 / self.fps
        elapsed = time.time() - self.buffer.last_update_time
        if elapsed < frame_duration:
            await asyncio.sleep(frame_duration - elapsed)
        
        # Get the current frame from the buffer
        frame_data = self.buffer.get_frame()
        
        # Create a VideoFrame
        frame = VideoFrame(
            width=self.buffer.width,
            height=self.buffer.height,
            format=self.format
        )
        
        # Copy the frame data
        frame.planes[0].update(frame_data.tobytes())
        
        # Set the frame timestamp
        frame.pts = self.pts
        frame.time_base = fractions.Fraction(1, 1000000)  # microseconds
        
        # Update for next frame
        self.pts += int(self.frame_time * 1000000)
        self.frame_count += 1
        
        return frame


class RTCVideoStreamer:
    """Manages WebRTC video streaming using the shared memory buffer"""
    
    def __init__(self):
        self.video_buffers: Dict[str, VideoFrameBuffer] = {}
        self.stream_configs: Dict[str, RTCVideoConfig] = {}
        self.peer_connections: Dict[str, Dict[str, RTCPeerConnection]] = {}  # stream_id -> {client_id -> pc}
        self.video_tracks: Dict[str, BufferVideoStreamTrack] = {}
        self.running = False
    
    def init_stream(self, stream_id: str, config: RTCVideoConfig) -> None:
        """Initialize a video stream with the given configuration"""
        # Create video buffer if it doesn't exist
        if stream_id not in self.video_buffers:
            self.video_buffers[stream_id] = VideoFrameBuffer(
                width=config.width,
                height=config.height,
                format=config.format
            )
            
            # Create video track for this buffer
            self.video_tracks[stream_id] = BufferVideoStreamTrack(
                buffer=self.video_buffers[stream_id],
                fps=config.fps
            )
        
        self.stream_configs[stream_id] = config
        self.peer_connections[stream_id] = {}
        
        logger.info(f"Initialized stream '{stream_id}' with config: {config}")
    
    async def start_streaming(self) -> None:
        """Start streaming all configured video streams"""
        if self.running:
            logger.warning("Streaming is already running")
            return
        
        self.running = True
        logger.info(f"Started video streaming for {len(self.stream_configs)} streams")
    
    async def stop_streaming(self) -> None:
        """Stop all streaming tasks"""
        if not self.running:
            return
        
        self.running = False
        
        # Close all peer connections
        for stream_id, clients in self.peer_connections.items():
            for client_id, pc in clients.items():
                await pc.close()
        
        self.peer_connections.clear()
        
        # Close all video buffers
        for stream_id, buffer in self.video_buffers.items():
            buffer.close()
        
        self.video_buffers.clear()
        self.video_tracks.clear()
        
        logger.info("Stopped all video streaming")
    
    def update_frame(self, stream_id: str, frame: np.ndarray) -> None:
        """Update the frame for a specific stream"""
        if stream_id in self.video_buffers:
            self.video_buffers[stream_id].update_frame(frame)
        else:
            logger.warning(f"Attempted to update frame for non-existent stream '{stream_id}'")
    
    async def create_offer(self, stream_id: str, client_id: str) -> Optional[dict]:
        """
        Create a WebRTC offer for the specified stream and client.
        Returns the offer in a format ready to be sent over WebSocket.
        """
        if stream_id not in self.stream_configs:
            logger.warning(f"Attempted to create offer for non-existent stream '{stream_id}'")
            return None
        
        if stream_id not in self.video_tracks:
            logger.warning(f"No video track available for stream '{stream_id}'")
            return None
        
        # Create a new RTCPeerConnection
        pc = RTCPeerConnection()
        
        # Add the video track
        pc.addTrack(self.video_tracks[stream_id])
        
        # Create an offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Store the peer connection
        if stream_id not in self.peer_connections:
            self.peer_connections[stream_id] = {}
        self.peer_connections[stream_id][client_id] = pc
        
        # Return the offer in the expected format
        return {
            "type": "offer",
            "streamId": stream_id,
            "sdp": {
                "type": offer.type,
                "sdp": offer.sdp
            }
        }
    
    async def process_answer(self, stream_id: str, client_id: str, answer_data: dict) -> None:
        """
        Process an SDP answer received from a client
        """
        if stream_id not in self.peer_connections or client_id not in self.peer_connections[stream_id]:
            logger.warning(f"Received answer for unknown peer connection: stream={stream_id}, client={client_id}")
            return
        
        pc = self.peer_connections[stream_id][client_id]
        
        # Create RTCSessionDescription from the answer data
        sdp_type = answer_data.get("sdp", {}).get("type")
        sdp = answer_data.get("sdp", {}).get("sdp")
        
        if not sdp_type or not sdp:
            logger.warning(f"Invalid SDP answer format: {answer_data}")
            return
        
        answer = RTCSessionDescription(sdp=sdp, type=sdp_type)
        
        # Set the remote description
        await pc.setRemoteDescription(answer)
        
        logger.info(f"Processed answer for stream '{stream_id}' from client '{client_id}'")
    
    async def close_peer_connection(self, stream_id: str, client_id: str) -> None:
        """
        Close a specific peer connection
        """
        if stream_id in self.peer_connections and client_id in self.peer_connections[stream_id]:
            pc = self.peer_connections[stream_id][client_id]
            await pc.close()
            del self.peer_connections[stream_id][client_id]
            logger.info(f"Closed peer connection for stream '{stream_id}', client '{client_id}'")


class VideoFilePlayer:
    """Plays a video file and sends frames to the RTCVideoStreamer"""
    
    def __init__(self, video_streamer: RTCVideoStreamer, stream_id: str):
        self.video_streamer = video_streamer
        self.stream_id = stream_id
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
    
    def run(self, video_path: str, loop: bool = True):
        """Open a video file and stream its frames to the video buffer"""
        if self.running:
            logger.warning("Video player is already running")
            return
        
        self.running = True
        self.stop_event.clear()
        
        # Start the video player in a separate thread
        self.thread = threading.Thread(
            target=self._play_video,
            args=(video_path, loop),
            daemon=True
        )
        self.thread.start()
        
        logger.info(f"Started video player for '{video_path}' on stream '{self.stream_id}'")
    
    def stop(self):
        """Stop the video player"""
        if not self.running:
            return
        
        self.running = False
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            if self.thread.is_alive():
                logger.warning("Video player thread did not terminate gracefully")
        
        self.thread = None
        logger.info(f"Stopped video player for stream '{self.stream_id}'")
    
    def _play_video(self, video_path: str, loop: bool):
        """Play the video file and send frames to the video buffer"""
        # Check if the stream exists
        if self.stream_id not in self.video_streamer.stream_configs:
            logger.error(f"Stream '{self.stream_id}' not initialized")
            return
        
        config = self.video_streamer.stream_configs[self.stream_id]
        
        # Open the video file
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video file: {video_path}")
            return
        
        # Get video properties
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Use the stream's configured FPS or the video's FPS if higher
        target_fps = max(config.fps, video_fps)
        frame_interval = 1.0 / target_fps
        
        logger.info(f"Playing video '{video_path}' ({total_frames} frames at {video_fps} FPS)")
        logger.info(f"Streaming at {target_fps} FPS to stream '{self.stream_id}'")
        
        frame_count = 0
        
        while not self.stop_event.is_set():
            start_time = time.time()
            
            # Read a frame
            ret, frame = cap.read()
            
            # If we reached the end of the video
            if not ret:
                if loop:
                    # Reset to the beginning
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    logger.info(f"Looping video '{video_path}'")
                    continue
                else:
                    # End playback
                    logger.info(f"Reached end of video '{video_path}'")
                    break
            
            # Update the frame in the video buffer
            self.video_streamer.update_frame(self.stream_id, frame)
            
            frame_count += 1
            
            # Calculate sleep time to maintain FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            
            # Use threading.Event.wait() which allows for interruption
            if self.stop_event.wait(sleep_time):
                break
        
        # Clean up
        cap.release()
        logger.info(f"Video player finished after {frame_count} frames")


# Example usage without coroutines for the main function
def example_usage():
    # Create the RTC video streamer
    streamer = RTCVideoStreamer()
    
    # Initialize a stream
    config = RTCVideoConfig(
        width=1280,
        height=720,
        fps=30,
        stream_id="camera0"
    )
    streamer.init_stream("camera0", config)
    
    # Create and start the asyncio event loop in a separate thread
    loop = asyncio.new_event_loop()
    
    def run_async_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()
    
    loop_thread = threading.Thread(target=run_async_loop, daemon=True)
    loop_thread.start()
    
    # Schedule the start_streaming coroutine
    asyncio.run_coroutine_threadsafe(streamer.start_streaming(), loop)
    
    # Create a video player (non-coroutine based)
    player = VideoFilePlayer(streamer, "camera0")
    
    # Start playing a video file (non-coroutine based)
    player.run("/path/to/video.mp4", loop=True)
    
    # Example of how to create an offer (would be called when a client requests it)
    async def create_and_print_offer():
        client_id = str(uuid.uuid4())
        offer = await streamer.create_offer("camera0", client_id)
        print(f"Created offer for client {client_id}: {json.dumps(offer)}")
        
        # In a real application, you would send this offer to the client
        # and then receive an answer back, which you would process with:
        # await streamer.process_answer("camera0", client_id, answer_data)
    
    # Schedule an example offer creation
    asyncio.run_coroutine_threadsafe(create_and_print_offer(), loop)
    
    try:
        # Run for 60 seconds
        print("Running for 60 seconds...")
        time.sleep(60)
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        # Stop the player (non-coroutine based)
        player.stop()
        
        # Schedule the stop_streaming coroutine
        stop_task = asyncio.run_coroutine_threadsafe(streamer.stop_streaming(), loop)
        stop_task.result(timeout=5)  # Wait for stop to complete
        
        # Stop the event loop
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=5)
        
        print("Cleanup complete")


if __name__ == "__main__":
    # Run the example
    example_usage()