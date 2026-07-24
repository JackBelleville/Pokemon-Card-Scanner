# Finds which cv2.VideoCapture indexes actually work on this machine and grabs a
# sample frame from each, so main.readCard() can be pointed at the right one.
import os
import cv2

os.makedirs('debugOutput', exist_ok=True)

# DirectShow is used explicitly: the default MSMF backend on Windows is slow to
# fail on indexes that don't exist, which makes probing hang for tens of seconds.
backends = [('default', None), ('MSMF', cv2.CAP_MSMF), ('DSHOW', cv2.CAP_DSHOW)]

for label, backend in backends:
    print(f'--- backend: {label} ---')
    for idx in range(4):
        cam = cv2.VideoCapture(idx) if backend is None else cv2.VideoCapture(idx, backend)
        if not cam.isOpened():
            print(f'  index {idx}: not available')
            cam.release()
            continue

        check, frame = cam.read()
        if not check or frame is None:
            print(f'  index {idx}: opened but returned no frame')
        else:
            h, w = frame.shape[:2]
            outfile = os.path.join('debugOutput', f'camera_{label}_{idx}.jpg')
            cv2.imwrite(outfile, frame)
            print(f'  index {idx}: WORKS - {w}x{h} ({"landscape" if w > h else "portrait"}) -> {outfile}')
        cam.release()
