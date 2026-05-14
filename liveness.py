import numpy as np


class LivenessState:
    def __init__(self):
        self.stage = 0
        self.stable_since = 0.0
        self.first_box = None
        self.last_box = None
        self.blink_deadline = 0.0
        self.challenge = None
        self.challenge_deadline = 0.0

    def reset(self):
        self.stage = 0
        self.stable_since = 0.0
        self.first_box = None
        self.last_box = None
        self.blink_deadline = 0.0
        self.challenge = None
        self.challenge_deadline = 0.0


def ear(eye_points):
    p1, p2, p3, p4, p5, p6 = eye_points

    def dist(a, b):
        return np.linalg.norm(np.array(a) - np.array(b))

    horizontal = dist(p1, p4)
    if horizontal < 1e-6:
        return 0.0

    return (dist(p2, p6) + dist(p3, p5)) / (2.0 * horizontal)


def blink_once(blink_state, name, landmarks, threshold=0.23, min_frames=1):
    if name not in blink_state:
        blink_state[name] = {"below": 0}

    if not landmarks or "left_eye" not in landmarks or "right_eye" not in landmarks:
        return False

    left_eye = landmarks["left_eye"]
    right_eye = landmarks["right_eye"]

    if len(left_eye) != 6 or len(right_eye) != 6:
        return False

    eye_ratio = (ear(left_eye) + ear(right_eye)) / 2.0

    if eye_ratio < threshold:
        blink_state[name]["below"] += 1
        return False

    if blink_state[name]["below"] >= min_frames:
        blink_state[name]["below"] = 0
        return True

    blink_state[name]["below"] = 0
    return False


def has_directional_movement(first_box, current_box, direction, min_shift=18):
    if first_box is None or current_box is None:
        return False

    top1, right1, bottom1, left1 = first_box
    top2, right2, bottom2, left2 = current_box

    cx1 = (left1 + right1) / 2.0
    cx2 = (left2 + right2) / 2.0

    if direction == "left":
        return (cx1 - cx2) >= min_shift
    if direction == "right":
        return (cx2 - cx1) >= min_shift

    return False


def is_mask_or_occluded(landmarks):
    if not landmarks:
        return True

    has_nose = "nose_tip" in landmarks and len(landmarks["nose_tip"]) > 0
    has_top_lip = "top_lip" in landmarks and len(landmarks["top_lip"]) > 0
    has_bottom_lip = "bottom_lip" in landmarks and len(landmarks["bottom_lip"]) > 0

    return not (has_nose and has_top_lip and has_bottom_lip)