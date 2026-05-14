import os
from collections import defaultdict

import face_recognition


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def safe_load_encoding(img_path: str):
    try:
        image = face_recognition.load_image_file(img_path)
        encodings = face_recognition.face_encodings(image)
    except Exception:
        return None

    if not encodings:
        return None
    return encodings[0]


def load_known_faces(known_dir: str):
    if not os.path.isdir(known_dir):
        raise RuntimeError("known_faces folder was not found.")

    encodings = []
    names = []

    for person_name in sorted(os.listdir(known_dir)):
        if person_name.startswith("."):
            continue

        person_dir = os.path.join(known_dir, person_name)
        if not os.path.isdir(person_dir):
            continue

        for filename in sorted(os.listdir(person_dir)):
            if filename.startswith("."):
                continue
            if not filename.lower().endswith(IMAGE_EXTENSIONS):
                continue

            img_path = os.path.join(person_dir, filename)
            encoding = safe_load_encoding(img_path)
            if encoding is None:
                continue

            encodings.append(encoding)
            names.append(person_name)

    if not encodings:
        raise RuntimeError("No valid faces were found in known_faces/<person_name>/")

    return encodings, names


def best_match(known_encodings, known_names, face_encoding, tolerance: float = 0.58):
    if not known_encodings:
        return "Unknown", 1.0

    distances = face_recognition.face_distance(known_encodings, face_encoding)

    per_person = defaultdict(list)
    for i, distance in enumerate(distances):
        per_person[known_names[i]].append(float(distance))

    person_scores = {}
    for name, values in per_person.items():
        values = sorted(values)
        best_two = values[:2] if len(values) >= 2 else values
        person_scores[name] = sum(best_two) / len(best_two)

    best_name = min(person_scores, key=person_scores.get)
    best_distance = person_scores[best_name]

    if best_distance <= tolerance:
        return best_name, best_distance

    return "Unknown", best_distance