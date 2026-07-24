# Checks whether pygrabber can pull a real frame off the webcam, since OpenCV's
# own VideoCapture cannot open it on this machine.
import os
import threading
import cv2
from pygrabber.dshow_graph import FilterGraph

os.makedirs('debugOutput', exist_ok=True)

got = threading.Event()
captured = {}


def onFrame(frame):
    captured['frame'] = frame
    got.set()


graph = FilterGraph()
print('devices:', graph.get_input_devices())

graph.add_video_input_device(0)
print('resolution:', graph.get_input_device().get_current_format())

graph.add_sample_grabber(onFrame)
graph.add_null_render()
graph.prepare_preview_graph()
graph.run()
graph.grab_frame()

if got.wait(timeout=10):
    frame = captured['frame']
    h, w = frame.shape[:2]
    # pygrabber hands back RGB; the rest of this project works in BGR
    cv2.imwrite(os.path.join('debugOutput', 'grab_test.jpg'), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    print(f'CAPTURED {w}x{h} -> debugOutput/grab_test.jpg')
else:
    print('TIMED OUT waiting for a frame')

graph.stop()
