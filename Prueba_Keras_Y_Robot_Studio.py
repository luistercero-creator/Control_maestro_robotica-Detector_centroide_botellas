import cv2
import numpy as np
from keras_facenet import FaceNet
import os
import time
import socket

# CONFIG
AUTHORIZED_PATH = r"C:\Users\VICTUS\Documents\A_Probando_Robotica\Foto_Autorizado"
THRESHOLD = 1.0  # Ajustable. Con la nueva corrección matemática, 0.7 es muy seguro.
UPDATE_INTERVAL = 2  # segundos para enviar Start/Stop
ROBOT_IP = "172.18.18.231"
ROBOT_PORT = 8000

# INICIALIZACIÓN 
embedder = FaceNet()
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

#  CARGAR PERSONA AUTORIZADA
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

    # 🔹 CORRECCIÓN MATEMÁTICA: Promediar y normalizar el vector resultante
    avg_emb = np.mean(embeddings, axis=0)
    normalized_avg_emb = avg_emb / np.linalg.norm(avg_emb)
    
    return normalized_avg_emb

authorized_embedding = load_authorized_face(AUTHORIZED_PATH)
print("✔ Persona autorizada cargada y normalizada correctamente")

# CONEXIÓN SOCKET
mi_socket = socket.socket()
try:
    mi_socket.connect((ROBOT_IP, ROBOT_PORT))
    print(f"✔ Conectado a RobotStudio en {ROBOT_IP}:{ROBOT_PORT}")
except Exception as e:
    print("❌ Error conectando a RobotStudio:", e)
    exit(1)

# WEBCAM
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

    # Variable por defecto para cada frame
    persona_detectada = False

    for (x, y, w, h) in faces:
        face = frame[y:y+h, x:x+w]
        face = cv2.resize(face, (160,160))
        face = np.expand_dims(face, axis=0)
        emb = embedder.embeddings(face)
        
        # Calcular la distancia
        dist = np.linalg.norm(authorized_embedding - emb)

        # Evaluar si la distancia es menor al umbral
        if dist < THRESHOLD:
            persona_detectada = True
            color = (0, 255, 0)  # verde
            text = f"PLAY ({dist:.2f})"
        else:
            color = (0, 0, 255)  # rojo
            text = f"STOP ({dist:.2f})"

        # Dibujar cuadro y texto
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        cv2.putText(frame, text, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # 🔹 LÓGICA DE COMANDO FINAL
    if persona_detectada:
        command = "Start"
    else:
        command = "Stop"

    # 🔹 ENVIAR COMANDO CADA UPDATE_INTERVAL
    if time.time() - last_time > UPDATE_INTERVAL:
        try:
            mi_socket.send(command.encode("utf-8"))
            print(f"Comando enviado: {command} | Estado actual: {'Autorizado' if persona_detectada else 'No autorizado'}")
        except Exception as e:
            print("❌ Error enviando comando:", e)
        last_time = time.time()

    cv2.imshow("Reconocimiento Facial", frame)

    if cv2.waitKey(1) & 0xFF == 27:  # ESC para salir
        break

cap.release()
cv2.destroyAllWindows()
mi_socket.close()
print("Conexión cerrada")