import time
import rospy
import asyncio
import logging
import numpy as np
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from aiortc import VideoStreamTrack

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("track.py/ROSVideoTrack")


class ROSVideoTrack(VideoStreamTrack):
    def __init__(self, bridge: CvBridge, topic_name: str):
        super().__init__()  
        self.bridge = bridge
        self.latest = None
        
        self._last = time.time()
        self.sub = rospy.Subscriber(topic_name, Image, self._cb)

    def _cb(self, msg: Image):
        try:
            self.latest = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            logger.error(f"bridge 转换失败，原因: {e}")


    async def recv(self):
        while self.latest is None:
            await asyncio.sleep(0.1)
        img = self.latest if self.latest is not None else np.zeros((480,640,3), np.uint8)
        import av, cv2
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        pts, tb = await self.next_timestamp()
        frame.pts, frame.time_base = pts, tb
        logger.debug(f"返回一次视频帧")
        return frame
