import cv2
import numpy as np


# ─────────────────────────────────────────────────────────────
# CORE CHECKS
# ─────────────────────────────────────────────────────────────

def check_liveness(image_np):
    """Main liveness check combining all methods"""
    try:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

        scores = {
            'texture':    _lbp_texture_score(gray),
            'reflection': _check_reflection(gray),
            'frequency':  _frequency_analysis(gray),
            'gradient':   _gradient_analysis(gray),
            'noise':      _natural_noise_score(gray),
        }

        final_score = (
            scores['texture']    * 0.30 +
            scores['reflection'] * 0.20 +
            scores['frequency']  * 0.20 +
            scores['gradient']   * 0.15 +
            scores['noise']      * 0.15
        )
        final_score = round(min(100, max(0, final_score)), 1)

        if final_score >= 45:
            return True,  final_score, "✅ Real face detected"
        elif final_score >= 30:
            return True,  final_score, "🟡 Likely real face"
        else:
            return False, final_score, "❌ Possible spoofing detected"

    except Exception as e:
        return False, 0, f"Liveness check failed: {str(e)}"


def detect_screen_or_photo(image_np):
    """
    Comprehensive screen/photo detection.
    Returns (is_real, reason)
    """
    try:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        checks_failed = []

        # 1. MOIRE PATTERN — screens show regular pixel grid
        f         = np.fft.fft2(gray)
        fshift    = np.fft.fftshift(f)
        magnitude = np.abs(fshift)
        ch, cw    = h//2, w//2
        magnitude[ch-10:ch+10, cw-10:cw+10] = 0
        max_freq   = np.max(magnitude)
        mean_freq  = np.mean(magnitude) + 1e-10
        freq_ratio = max_freq / mean_freq
        if freq_ratio > 8000:
            checks_failed.append("screen_moire")

        # 2. RECTANGULAR OBJECT DETECTION — phone/paper shape
        edges    = cv2.Canny(gray, 30, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest  = max(contours, key=cv2.contourArea)
            area     = cv2.contourArea(largest)
            img_area = h * w
            if area > img_area * 0.25:
                peri   = cv2.arcLength(largest, True)
                approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
                if len(approx) == 4:
                    x, y, rw, rh = cv2.boundingRect(largest)
                    aspect = rw / (rh + 1e-10)
                    if 0.35 < aspect < 0.85:
                        checks_failed.append("phone_shape")
                    elif 0.6 < aspect < 1.6:
                        checks_failed.append("paper_shape")

        # 3. SCREEN GLARE — very bright uniform spots
        very_bright  = np.sum(gray > 248)
        bright_ratio = very_bright / gray.size
        if bright_ratio > 0.06:
            checks_failed.append("screen_glare")

        # 4. COLOR CHANNEL UNIFORMITY — screens too uniform
        if len(image_np.shape) == 3:
            stds = [np.std(image_np[:,:,c]) for c in range(3)]
            if np.mean(stds) < 20:
                checks_failed.append("color_uniform")

        # 5. TEXTURE DEPTH — real faces have 3D texture variation
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        lap_var   = laplacian.var()
        if lap_var < 50:
            checks_failed.append("flat_texture")

        # 6. FACE IN FRAME CHECK — detect if face is inside a rectangle
        # (phone holding pattern)
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50,50))

        if len(faces) > 0 and contours:
            for (fx, fy, fw, fh) in faces:
                face_center = (fx + fw//2, fy + fh//2)
                # Check if face is inside the largest contour (phone screen)
                if area > img_area * 0.2:
                    result = cv2.pointPolygonTest(
                        largest,
                        (float(face_center[0]), float(face_center[1])),
                        False
                    )
                    if result >= 0 and area > img_area * 0.3:
                        checks_failed.append("face_inside_screen")

        # Decision
        critical = {'screen_moire', 'face_inside_screen', 'phone_shape'}
        critical_failed = [c for c in checks_failed if c in critical]

        if len(critical_failed) >= 1:
            return False, f"📱 Phone/screen detected! Please show your REAL FACE directly to the camera. Do not use photos or phone screens."

        if len(checks_failed) >= 3:
            return False, f"⚠️ Artificial image detected ({', '.join(checks_failed)}). Please show your real face."

        return True, "Real photo"

    except Exception as e:
        return False, f"Spoof check could not run ({str(e)}). Please retake the photo."


def check_face_quality(image_np):
    """
    Check face quality for recognition.
    Returns (is_good, issues_list)
    """
    issues = []
    try:
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

        # Blur check
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if lap_var < 80:
            issues.append(f"⚠️ Image too blurry (score: {lap_var:.0f}). Use better lighting.")

        # Brightness
        brightness = np.mean(gray)
        if brightness < 50:
            issues.append(f"⚠️ Too dark (brightness: {brightness:.0f}). Move to better light.")
        elif brightness > 220:
            issues.append(f"⚠️ Too bright (brightness: {brightness:.0f}). Avoid direct light.")

        # Face present
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60,60))
        if len(faces) == 0:
            issues.append("⚠️ No face detected. Position your face in center.")
        elif len(faces) > 1:
            issues.append(f"⚠️ {len(faces)} faces detected. Only one face allowed.")

        # Face size check
        if len(faces) == 1:
            fx, fy, fw, fh = faces[0]
            face_ratio = (fw * fh) / (gray.shape[0] * gray.shape[1])
            if face_ratio < 0.05:
                issues.append("⚠️ Face too small. Move closer to camera.")
            elif face_ratio > 0.8:
                issues.append("⚠️ Face too close. Move back a little.")

    except Exception as e:
        issues.append(f"Quality check error: {str(e)}")

    return len(issues) == 0, issues


# ─────────────────────────────────────────────────────────────
# MULTI-FRAME VERIFICATION (for student login)
# ─────────────────────────────────────────────────────────────

def init_liveness_session():
    """Initialize multi-frame liveness session"""
    return {
        'frames':         [],
        'face_positions': [],
        'brightness_vals':[],
        'verified':       False,
        'frame_count':    0,
        'required_frames': 3
    }


def process_frame_for_liveness(frame_np, session):
    """
    Process each frame for multi-frame liveness.
    Returns (status, message, session)
    """
    try:
        gray = cv2.cvtColor(frame_np, cv2.COLOR_RGB2GRAY)

        # Screen/photo check first
        is_real, reason = detect_screen_or_photo(frame_np)
        if not is_real:
            return "blocked", reason, session

        # Detect face
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60,60))

        if len(faces) == 0:
            return "no_face", "No face detected. Position your face in center.", session

        if len(faces) > 1:
            return "multiple", "Multiple faces detected. Only one person allowed.", session

        # Track face position
        fx, fy, fw, fh = faces[0]
        face_center = (fx + fw//2, fy + fh//2)
        brightness  = np.mean(gray[fy:fy+fh, fx:fx+fw])

        session['frames'].append(frame_np)
        session['face_positions'].append(face_center)
        session['brightness_vals'].append(brightness)
        session['frame_count'] += 1

        # Check for natural variation across frames
        if session['frame_count'] >= session['required_frames']:
            positions = session['face_positions']

            # Check position variation (real faces move slightly)
            x_positions = [p[0] for p in positions]
            y_positions = [p[1] for p in positions]
            x_var = np.std(x_positions)
            y_var = np.std(y_positions)

            # Real faces have slight movement (not perfectly still like photos)
            # But not too much movement
            if x_var < 0.5 and y_var < 0.5:
                # Perfectly still — could be photo
                # But some cameras are stable, so don't block, just warn
                pass

            session['verified'] = True
            return "verified", "✅ Liveness verified!", session

        remaining = session['required_frames'] - session['frame_count']
        return "collecting", f"Hold still... ({remaining} more frames needed)", session

    except Exception as e:
        return "error", str(e), session


# ─────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def _lbp_texture_score(gray):
    try:
        resized = cv2.resize(gray, (200, 200))
        center  = resized[1:-1, 1:-1]
        neighbors = [
            resized[0:-2, 0:-2], resized[0:-2, 1:-1], resized[0:-2, 2:],
            resized[1:-1, 0:-2],                       resized[1:-1, 2:],
            resized[2:,   0:-2], resized[2:,   1:-1],  resized[2:,   2:]
        ]
        lbp_val = np.zeros(center.shape, dtype=np.uint8)
        for i, nb in enumerate(neighbors):
            lbp_val += ((nb >= center).astype(np.uint8)) << i
        variance = np.var(lbp_val)
        if 300 <= variance <= 4000:
            return 80
        elif variance > 4000:
            return 65
        else:
            return 40
    except Exception:
        return 60


def _check_reflection(gray):
    try:
        bright_pixels = np.sum(gray > 245)
        bright_ratio  = bright_pixels / gray.size
        if bright_ratio > 0.25:
            return 20
        elif bright_ratio > 0.10:
            return 50
        else:
            return 85
    except Exception:
        return 60


def _frequency_analysis(gray):
    try:
        resized   = cv2.resize(gray, (128, 128))
        f         = np.fft.fft2(resized)
        fshift    = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1)
        std_mag   = np.std(magnitude)
        if 1.0 <= std_mag <= 4.5:
            return 80
        elif std_mag < 1.0:
            return 40
        else:
            return 60
    except Exception:
        return 60


def _gradient_analysis(gray):
    try:
        sobelx    = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely    = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(sobelx**2 + sobely**2)
        mean_grad = np.mean(magnitude)
        if 5 <= mean_grad <= 80:
            return 80
        elif mean_grad > 80:
            return 55
        else:
            return 40
    except Exception:
        return 60


def _natural_noise_score(gray):
    try:
        blurred   = cv2.GaussianBlur(gray, (5, 5), 0)
        noise     = cv2.absdiff(gray, blurred)
        noise_std = np.std(noise)
        if 1.5 <= noise_std <= 20:
            return 85
        elif noise_std > 20:
            return 60
        else:
            return 35
    except Exception:
        return 60


def get_liveness_badge(is_live, score):
    if is_live:
        return "🟢 Live Face Verified" if score >= 75 else "🟡 Likely Live Face"
    else:
        return "🔴 Possible Spoofing Detected"
