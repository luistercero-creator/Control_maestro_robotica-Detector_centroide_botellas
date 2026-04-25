import cv2
import numpy as np
from keras_facenet import FaceNet
import os
import time

# ===== CONFIG =====
AUTHORIZED_PATH = r"C:\Users\VICTUS\Documents\A_Probando_Robotica\Foto_Autorizado"
THRESHOLD = 10  # Ajustable
UPDATE_INTERVAL = 2  # segundos para enviar 0/1

# ===== INICIALIZACIÓN =====
embedder = FaceNet()

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

# ===== CARGAR PERSONA AUTORIZADA =====
def load_authorized_face(path):
    embeddings = []

    if not os.path.exists(path):
        raise Exception("La ruta NO existe: " + path)

    files = os.listdir(path)
    if len(files) == 0:
        raise Exception("La carpeta está vacía")

    for file in files:
        if file.lower().endswith((".jpg", ".png", ".jpeg")):
            img_path = os.path.join(path, file)
            print("Cargando:", img_path)
            img = cv2.imread(img_path)
            if img is None:
                print("❌ ERROR cargando imagen:", img_path)
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) == 0:
                print("⚠ No se detectó rostro en:", file)
                continue
            for (x, y, w, h) in faces:
                face = img[y:y+h, x:x+w]
                face = cv2.resize(face, (160,160))
                face = np.expand_dims(face, axis=0)
                emb = embedder.embeddings(face)
                embeddings.append(emb)
                print("✔ Rostro detectado en:", file)

    if len(embeddings) == 0:
        raise Exception("No se detectaron rostros válidos en la carpeta.")

    return np.mean(embeddings, axis=0)

authorized_embedding = load_authorized_face(AUTHORIZED_PATH)
print("✔ Persona autorizada cargada correctamente")

# ===== WEBCAM =====
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise Exception("No se pudo abrir la cámara")

last_time = 0  # Para controlar intervalos

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error leyendo cámara")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)

    output = 0  # STOP por defecto

    for (x, y, w, h) in faces:
        # Recortar cara y procesar
        face = frame[y:y+h, x:x+w]
        face = cv2.resize(face, (160,160))
        face = np.expand_dims(face, axis=0)

        emb = embedder.embeddings(face)
        dist = np.linalg.norm(authorized_embedding - emb)

        if dist < THRESHOLD:
            output = 1
            text = "PLAY"
        else:
            output = 0
            text = "STOP"

        # 🔹 DIBUJAR CUADRO VERDE Y TEXTO
        color = (0, 255, 0) if output == 1 else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        cv2.putText(frame, text, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # 🔹 SALIDA CADA 2 SEGUNDOS
    if time.time() - last_time > UPDATE_INTERVAL:
        print("Salida:", output)
        last_time = time.time()

    # 🔹 MOSTRAR VENTANA DE CAMARA
    cv2.imshow("Reconocimiento Facial", frame)

    if cv2.waitKey(1) & 0xFF == 27:  # ESC para salir
        break

cap.release()
cv2.destroyAllWindows()