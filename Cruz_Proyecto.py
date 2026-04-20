import cv2
import numpy as np
import time
import os
from keras.models import load_model

# --- CONFIGURACIONES ---
RUTA_PROYECTO = r"C:\Users\VICTUS\Documents\A_Fotos_Botella" 
UMBRAL_CONFIANZA = 0.90 
TOLERANCIA_CENTRO = 30
print("A")

# --- CARGAR EL CEREBRO DE LA IA ---
ruta_modelo = os.path.join(RUTA_PROYECTO, "keras_model.h5")
ruta_labels = os.path.join(RUTA_PROYECTO, "labels.txt")

try:
    print("Cargando modelo de Inteligencia Artificial...")
    model = load_model(ruta_modelo, compile=False) 
    class_names = open(ruta_labels, "r").readlines()
    print("✔ Modelo cargado correctamente.")
except Exception as e:
    print(f"❌ Error al cargar la IA: {e}")
    exit(1)

# --- INICIALIZAR WEBCAM ---
cap = cv2.VideoCapture(2, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("❌ Error: No se pudo abrir la cámara 1. Intenta cambiar el número a 0.")
    exit(1)

ancho_camara = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
alto_camara = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
centro_camara_x = ancho_camara // 2
centro_camara_y = alto_camara // 2

np.set_printoptions(suppress=True)

# --- VARIABLES DE SUAVIZADO ---
centro_suavizado_x = 0
centro_suavizado_y = 0
radio_suavizado = 0
FACTOR_SUAVIZADO = 0.2 

print("\n--- MODO: ALINEACIÓN VISUAL DE BOTELLA (PROXIMIDAD EXTREMA + ANTI-REFLEJO) ---")
print("Presiona ESC en la ventana de video para salir.\n")

while True:
    ret, frame = cap.read()
    if not ret: 
        break

    # 1. DIBUJAR REFERENCIA CENTRAL DE LA CÁMARA
    cv2.line(frame, (centro_camara_x, 0), (centro_camara_x, alto_camara), (200, 200, 200), 1)
    cv2.line(frame, (0, centro_camara_y), (ancho_camara, centro_camara_y), (200, 200, 200), 1)
    cv2.circle(frame, (centro_camara_x, centro_camara_y), TOLERANCIA_CENTRO, (255, 255, 0), 1)

    # 2. PREPARAR IMAGEN PARA LA IA
    imagen_redimensionada = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
    imagen_array = np.asarray(imagen_redimensionada, dtype=np.float32).reshape(1, 224, 224, 3)
    imagen_normalizada = (imagen_array / 127.5) - 1

    # 3. PREDICCIÓN IA
    prediccion = model.predict(imagen_normalizada, verbose=0)
    indice_ganador = np.argmax(prediccion) 
    clase_ganadora = class_names[indice_ganador].strip()
    porcentaje_confianza = prediccion[0][indice_ganador]

    # 4. LÓGICA DE ALINEACIÓN
    if "0" in clase_ganadora and porcentaje_confianza > UMBRAL_CONFIANZA:
        
        # Filtro de color
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        blurred = cv2.medianBlur(hsv_frame, 7) 
        
        # --- AJUSTE 1: Rango de color tolerante al brillo blanco/celeste ---
        lower_cap = np.array([100, 80, 20])
        upper_cap = np.array([130, 255, 255])
        mask_cap = cv2.inRange(blurred, lower_cap, upper_cap)
        
        # --- AJUSTE 2: Kernel gigante (11x11) para rellenar el agujero del reflejo ---
        kernel = np.ones((11, 11), np.uint8)
        mask_cap = cv2.morphologyEx(mask_cap, cv2.MORPH_CLOSE, kernel)

        # --- AJUSTE 3: param2 bajó a 18 para aceptar el círculo aunque el reflejo lo deforme un poco ---
        circulos = cv2.HoughCircles(mask_cap, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                                    param1=50, param2=18, minRadius=15, maxRadius=200)

        if circulos is not None:
            circulos = np.round(circulos[0, :]).astype("int")
            (x_crudo, y_crudo, r_crudo) = circulos[0]

            if centro_suavizado_x == 0:
                centro_suavizado_x = x_crudo
                centro_suavizado_y = y_crudo
                radio_suavizado = r_crudo
            else:
                centro_suavizado_x = int((x_crudo * FACTOR_SUAVIZADO) + (centro_suavizado_x * (1.0 - FACTOR_SUAVIZADO)))
                centro_suavizado_y = int((y_crudo * FACTOR_SUAVIZADO) + (centro_suavizado_y * (1.0 - FACTOR_SUAVIZADO)))
                radio_suavizado = int((r_crudo * FACTOR_SUAVIZADO) + (radio_suavizado * (1.0 - FACTOR_SUAVIZADO)))

            error_x = centro_suavizado_x - centro_camara_x
            error_y = centro_suavizado_y - centro_camara_y
            
            cv2.circle(frame, (centro_suavizado_x, centro_suavizado_y), radio_suavizado, (255, 0, 255), 3) 
            cv2.drawMarker(frame, (centro_suavizado_x, centro_suavizado_y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2) 
            cv2.line(frame, (centro_camara_x, centro_camara_y), (centro_suavizado_x, centro_suavizado_y), (0, 165, 255), 2) 

            if abs(error_x) <= TOLERANCIA_CENTRO and abs(error_y) <= TOLERANCIA_CENTRO:
                estado = "¡ALINEADO PERFECTAMENTE!"
                color_estado = (0, 255, 0)
            else:
                estado = f"CORREGIR -> X: {-error_x}px | Y: {-error_y}px" 
                color_estado = (0, 165, 255)

            cv2.putText(frame, estado, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2)
            cv2.putText(frame, f"Confianza IA: {porcentaje_confianza*100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        else:
            # Si la IA dice que hay botella, pero la cámara pierde la geometría del tapón
            cv2.putText(frame, "Calculando geometria del tapon...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, f"Confianza IA: {porcentaje_confianza*100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            centro_suavizado_x = 0
            centro_suavizado_y = 0

    else:
        # Si la IA no la ve en absoluto
        centro_suavizado_x = 0
        centro_suavizado_y = 0
        cv2.putText(frame, "BUSCANDO BOTELLA...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("Alineacion Visual (Visual Servoing)", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()