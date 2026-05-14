import os
import random
import time
from datetime import datetime

import cv2
import face_recognition

from db import DB
from export import (
    export_alerts_csv,
    export_events_csv,
    export_excel_from_csv,
    export_html_report,
    export_unknowns_csv,
)
from liveness import (
    LivenessState,
    blink_once,
    has_directional_movement,
    is_mask_or_occluded,
)
from recognizer import best_match, load_known_faces
from utils import gentle_beep


PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
KNOWN_DIR = os.path.join(PROJECT_DIR, "known_faces")
UNKNOWN_DIR = os.path.join(PROJECT_DIR, "unknown_faces")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
DB_PATH = os.path.join(LOGS_DIR, "attendance.db")

os.makedirs(UNKNOWN_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

TOLERANCE = 0.58
UNKNOWN_SAVE_DELAY = 2.0
KNOWN_STABLE_DELAY = 1.0
BLINK_TIMEOUT = 5.0
CHALLENGE_TIMEOUT = 5.0
DIRECTION_SHIFT = 18
RECENT_UNKNOWN_TTL = 30.0
RECENT_KNOWN_COOLDOWN = 5.0
MIN_OUT_MINUTES = 10
STABLE_FRAMES_REQUIRED = 4


def save_unknown_frame(frame):
    filename = f"unknown_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    path = os.path.join(UNKNOWN_DIR, filename)
    cv2.imwrite(path, frame)
    return path


def compare_unknown_with_recent(face_encoding, recent_unknown_encodings, ttl_seconds=30.0, tolerance=0.50):
    now = time.time()
    kept = []

    already_exists = False
    for saved_time, saved_encoding in recent_unknown_encodings:
        if now - saved_time <= ttl_seconds:
            kept.append((saved_time, saved_encoding))
            distance = face_recognition.face_distance([saved_encoding], face_encoding)[0]
            if distance <= tolerance:
                already_exists = True

    return already_exists, kept


def draw_label(frame, text, x, y, color=(0, 255, 0), scale=0.7, thickness=2):
    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def main():
    db = DB(DB_PATH)
    session_id = db.start_session()

    try:
        known_encodings, known_names = load_known_faces(KNOWN_DIR)
    except Exception as e:
        print(f"Error loading known faces: {e}")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open camera.")
        return

    blink_state = {}
    liveness_states = {}
    recent_names = {}
    recent_unknown_encodings = []
    recognition_streak = {}
    unknown_since = None
    last_mask_alert_time = 0.0
    status_text = "Live Attendance ready"

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb)
        face_encodings = face_recognition.face_encodings(rgb, face_locations)
        face_landmarks_list = face_recognition.face_landmarks(rgb, face_locations)

        now = time.time()
        active_names = set()

        if face_locations:
            for i, face_location in enumerate(face_locations):
                top, right, bottom, left = face_location
                face_encoding = face_encodings[i]
                landmarks = face_landmarks_list[i] if i < len(face_landmarks_list) else {}

                name, distance = best_match(known_encodings, known_names, face_encoding, tolerance=TOLERANCE)
                confidence = round(max(0.0, 1.0 - distance), 4)

                box_color = (0, 255, 0)
                label = f"{name} ({distance:.3f})"

                if name != "Unknown":
                    active_names.add(name)
                    unknown_since = None
                    recognition_streak[name] = recognition_streak.get(name, 0) + 1

                    if name not in liveness_states:
                        liveness_states[name] = LivenessState()

                    state = liveness_states[name]

                    if recognition_streak[name] < STABLE_FRAMES_REQUIRED:
                        state.reset()
                        blink_state.pop(name, None)
                        label = f"{name} - confirming {recognition_streak[name]}/{STABLE_FRAMES_REQUIRED}"
                        box_color = (255, 255, 0)

                    elif is_mask_or_occluded(landmarks):
                        if now - last_mask_alert_time > 5.0:
                            db.add_alert(session_id, "MASK", "Mask or occlusion detected")
                            last_mask_alert_time = now
                        state.reset()
                        blink_state.pop(name, None)
                        label = f"{name} - remove mask/occlusion"
                        box_color = (0, 165, 255)

                    else:
                        if state.stage == 0:
                            if state.stable_since == 0.0:
                                state.stable_since = now
                                state.first_box = face_location
                                label = f"{name} - hold still"
                            elif now - state.stable_since >= KNOWN_STABLE_DELAY:
                                state.stage = 1
                                state.first_box = face_location
                                state.challenge = random.choice(["left", "right"])
                                state.challenge_deadline = now + CHALLENGE_TIMEOUT
                                label = f"{name} - move {state.challenge}"
                            else:
                                label = f"{name} - hold still"

                        elif state.stage == 1:
                            if has_directional_movement(state.first_box, face_location, direction=state.challenge, min_shift=DIRECTION_SHIFT):
                                state.stage = 2
                                state.blink_deadline = now + BLINK_TIMEOUT
                                label = f"{name} - blink once"
                            elif now > state.challenge_deadline:
                                state.reset()
                                blink_state.pop(name, None)
                                state.stable_since = now
                                label = f"{name} - try again"
                            else:
                                label = f"{name} - move {state.challenge}"

                        elif state.stage == 2:
                            if blink_once(blink_state, name, landmarks, threshold=0.23, min_frames=1):
                                state.stage = 3
                            elif now > state.blink_deadline:
                                state.reset()
                                blink_state.pop(name, None)
                                state.stable_since = now
                                label = f"{name} - try again"
                            else:
                                label = f"{name} - blink once"

                        if state.stage == 3:
                            last_event = db.get_last_event(session_id, name)
                            last_event_type = last_event.get("event_type") if last_event else None

                            event_type = None

                            if last_event_type is None:
                                event_type = "IN"

                            elif last_event_type == "IN":
                                if db.can_mark_out(session_id, name, min_minutes=MIN_OUT_MINUTES):
                                    event_type = "OUT"
                                else:
                                    event_type = None
                                    status_text = f"{name} already IN - OUT allowed after 10 min"

                            elif last_event_type == "OUT":
                                event_type = "IN"

                            if event_type is not None:
                                if name not in recent_names or now - recent_names[name] > RECENT_KNOWN_COOLDOWN:
                                    db.add_event(
                                        session_id=session_id,
                                        person_name=name,
                                        event_type=event_type,
                                        confidence=confidence,
                                        liveness_passed=True,
                                    )
                                    recent_names[name] = now
                                    gentle_beep()
                                    status_text = f"{name} marked {event_type}"
                                else:
                                    status_text = f"{name} recently marked"

                            state.reset()
                            blink_state.pop(name, None)
                            state.stable_since = now

                else:
                    box_color = (0, 0, 255)
                    label = f"Unknown ({distance:.3f})"

                    if unknown_since is None:
                        unknown_since = now

                    if now - unknown_since >= UNKNOWN_SAVE_DELAY:
                        already_exists, recent_unknown_encodings = compare_unknown_with_recent(
                            face_encoding,
                            recent_unknown_encodings,
                            ttl_seconds=RECENT_UNKNOWN_TTL,
                            tolerance=0.50,
                        )

                        if not already_exists:
                            image_path = save_unknown_frame(frame)
                            db.add_unknown_event(session_id, image_path)
                            recent_unknown_encodings.append((now, face_encoding))
                            status_text = "Unknown face saved"
                        else:
                            status_text = "Unknown already saved"

                cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
                draw_label(frame, label, left, max(top - 10, 20), color=box_color)

        else:
            unknown_since = None

        stale_names = []
        for name, state in liveness_states.items():
            if name not in active_names:
                if state.stable_since and now - state.stable_since > 3.0:
                    stale_names.append(name)

        for name in stale_names:
            liveness_states[name].reset()
            blink_state.pop(name, None)
            recognition_streak.pop(name, None)

        draw_label(frame, status_text, 20, 30, color=(255, 255, 0), scale=0.8, thickness=2)
        draw_label(frame, "Press Q to quit", 20, 60, color=(200, 200, 200), scale=0.6, thickness=1)

        cv2.imshow("Live Attendance", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    db.end_session(session_id)

    events = db.fetch_events(session_id)
    unknowns = db.fetch_unknown_events(session_id)
    alerts = db.fetch_alerts(session_id)

    events_csv = os.path.join(LOGS_DIR, "events.csv")
    unknowns_csv = os.path.join(LOGS_DIR, "unknowns.csv")
    alerts_csv = os.path.join(LOGS_DIR, "alerts.csv")
    events_xlsx = os.path.join(LOGS_DIR, "events.xlsx")
    report_html = os.path.join(LOGS_DIR, "report.html")

    export_events_csv(events, events_csv)
    export_unknowns_csv(unknowns, unknowns_csv)
    export_alerts_csv(alerts, alerts_csv)
    export_excel_from_csv(events_csv, events_xlsx)
    export_html_report(events, unknowns, alerts, report_html)

    db.close()


if __name__ == "__main__":
    main()