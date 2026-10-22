import numpy as np
import cv2
import requests
from imgyaso.adathres import adathres
import random

def draw_match(bg, sld, loc):
    h, w = sld.shape[:2]
    bg = bg.copy()
    cv2.rectangle(bg, loc, (loc[0] + w, loc[1] + h), (0, 255, 0))
    open('bg_mark.png', 'wb').write(
        bytes(cv2.imencode('.png', bg)[1])
    )
    return bg

def generate_track(distance):
    track = []
    current = 0
    mid = distance * 0.7
    while current < distance:
        if current < mid:
            step = random.uniform(2, 5)   # 加速段
        else:
            step = random.uniform(0.5, 2)  # 减速段
        current = min(current + step, distance)
        track.append(round(current, 2))
    return track

def solve_captcha():
    slider_url = 'https://static-captcha-sgp.aliyuncs.com/qst/PUZZLE/online/897/21c372d1-43c3-4a62-93cc-d74daae3c9bb/shadow.png'
    bg_url = 'https://static-captcha-sgp.aliyuncs.com/qst/PUZZLE/online/897/21c372d1-43c3-4a62-93cc-d74daae3c9bb/back.png'
    slider = cv2.imdecode(
        np.frombuffer(requests.get(slider_url).content, np.uint8),
        cv2.IMREAD_COLOR,
    )
    bg = cv2.imdecode(
        np.frombuffer(requests.get(bg_url).content, np.uint8),
        cv2.IMREAD_COLOR,
    )
    slider2v = 255 - cv2.inRange(
        slider, 
        np.asarray([100, 100, 100]), 
        np.asarray([150, 150, 150])
    )
    # 把滑块上下方空白去掉
    row_mask = (255 - slider2v).mean(1) != 0
    ys = np.where(row_mask)[0]
    ymin, ymax = np.min(ys), np.max(ys)
    slider2v = slider2v[ymin:ymax+1]
    bg2v = adathres(bg).astype(np.uint8)
    open('bg2v.png', 'wb').write(
        bytes(cv2.imencode('.png', bg2v)[1])
    )
    open('slider2v.png', 'wb').write(
        bytes(cv2.imencode('.png', slider2v)[1])
    )
    match = cv2.matchTemplate(bg2v, slider2v, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(match)
    print(f'sc: {max_val}, loc: {max_loc}')
    # draw_match(bg, slider2v, max_loc)
    track = generate_track(max_loc[0])
    print(f'track: {track}')


    

solve_captcha()