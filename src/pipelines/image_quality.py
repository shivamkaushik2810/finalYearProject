import cv2
import numpy as np


def check_image_quality(image_np):
    """
    Check if image is good enough for face recognition.
    Returns (is_good, warnings_list)
    """
    warnings = []

    # Convert to grayscale
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

    # 1. BLUR DETECTION — Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 80:
        warnings.append(f"⚠️ Image is too blurry (score: {laplacian_var:.1f}). Please upload a clearer photo.")

    # 2. BRIGHTNESS DETECTION
    brightness = np.mean(gray)
    if brightness < 50:
        warnings.append(f"⚠️ Image is too dark (brightness: {brightness:.1f}). Please use better lighting.")
    elif brightness > 220:
        warnings.append(f"⚠️ Image is overexposed (brightness: {brightness:.1f}). Avoid direct light on face.")

    # 3. CONTRAST DETECTION
    contrast = gray.std()
    if contrast < 20:
        warnings.append(f"⚠️ Image has very low contrast (score: {contrast:.1f}). Photo may not work well.")

    # 4. RESOLUTION CHECK
    h, w = image_np.shape[:2]
    if h < 200 or w < 200:
        warnings.append(f"⚠️ Image resolution is too low ({w}x{h}). Use a higher quality camera.")

    is_good = len(warnings) == 0
    return is_good, warnings


def count_faces_in_image(image_np):
    """
    Count total number of faces in image using OpenCV Haar Cascade.
    Returns face_count
    """
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return len(faces)


def get_image_quality_score(image_np):
    """
    Returns a quality score 0-100
    """
    gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
    blur_score    = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 5, 40)
    bright_score  = 30 - abs(np.mean(gray) - 128) / 4.3
    contrast_score = min(gray.std() / 1.28, 30)
    total = max(0, min(100, blur_score + bright_score + contrast_score))
    return round(total)
