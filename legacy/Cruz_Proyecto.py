import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
import cv2
import numpy as np
import os
from keras.models import load_model

# === CONFIGURACIONES DE RED Y RUTAS ===
ROBOT_IP = "192.168.1.21"
ROBOT_PORT = 8000
RUTA_PROYECTO = "converted_keras"

# === PARÁMETROS DE VISIÓN ARTIFICIAL ===
UMBRAL_CONFIANZA = 0.90 
TOLERANCIA_CENTRO = 30
FACTOR_SUAVIZADO = 0.2 
FACTOR_MM_PX = 0.05  # Milímetros por cada pixel de error.

# === CALIBRACIÓN FÍSICA DE LA CÁMARA (NUEVO) ===
CAMARA_ROTADA_90 = True  # True: Cruza los ejes (X de cámara = Y de robot)
INVERSOR_ROBOT_X = 1     # Pon -1 si el robot se aleja del centro en X
INVERSOR_ROBOT_Y = 1     # Pon -1 si el robot se aleja del centro en Y

class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Consola ABB + Visión IA (FaceNet)")
        self.root.geometry("550x850") 
        self.root.configure(bg="#2d2d2d")
        
        self.sock = None
        self.conectado = False
        
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0
        self.auto_alineando = False
        self.robot_ocupado = False  
        
        # --- 1. PANEL DE COORDENADAS ---
        frame_coords = tk.Frame(root, bg="#2d2d2d")
        frame_coords.pack(pady=10, fill=tk.X, padx=20)
        tk.Label(frame_coords, text="COORDENADAS ACTUALES (mm)", bg="#2d2d2d", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        
        inner_coords = tk.Frame(frame_coords, bg="#2d2d2d")
        inner_coords.pack()
        self.lbl_x = tk.Label(inner_coords, text="X: 0.00", bg="black", fg="#00FF00", font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_x.pack(side=tk.LEFT, padx=5)
        self.lbl_y = tk.Label(inner_coords, text="Y: 0.00", bg="black", fg="#00FF00", font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_y.pack(side=tk.LEFT, padx=5)
        self.lbl_z = tk.Label(inner_coords, text="Z: 0.00", bg="black", fg="#00FF00", font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_z.pack(side=tk.LEFT, padx=5)

        # --- 2. PANEL DE CONEXIÓN ---
        frame_conn = tk.Frame(root, bg="#2d2d2d")
        frame_conn.pack(pady=5, fill=tk.X, padx=20)
        self.btn_conectar = tk.Button(frame_conn, text="Conectar", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=self.conectar)
        self.btn_conectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.btn_desconectar = tk.Button(frame_conn, text="Desconectar", bg="#f44336", fg="white", font=("Arial", 10, "bold"), command=self.desconectar, state=tk.DISABLED)
        self.btn_desconectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # --- 3. COMANDOS MANUALES ---
        frame_cmd = tk.Frame(root, bg="#2d2d2d")
        frame_cmd.pack(pady=5, fill=tk.X, padx=20)
        tk.Label(frame_cmd, text="Comando Manual (ej. X,50 | HOME):", bg="#2d2d2d", fg="white", font=("Arial", 10)).pack(anchor=tk.W)
        self.entry_cmd = tk.Entry(frame_cmd, font=("Arial", 14))
        self.entry_cmd.pack(fill=tk.X, pady=5)
        self.entry_cmd.bind("<Return>", lambda event: self.enviar_comando())
        self.btn_enviar = tk.Button(frame_cmd, text="Enviar Comando", bg="#2196F3", fg="white", font=("Arial", 10, "bold"), command=self.enviar_comando, state=tk.DISABLED)
        self.btn_enviar.pack(fill=tk.X, pady=5)

        # --- 4. PANEL DE VISIÓN IA ---
        frame_ia = tk.Frame(root, bg="#2d2d2d", bd=2, relief=tk.RIDGE)
        frame_ia.pack(pady=10, fill=tk.X, padx=20)
        tk.Label(frame_ia, text="CONTROL IA", bg="#2d2d2d", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        self.btn_auto = tk.Button(frame_ia, text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0", fg="white", font=("Arial", 12, "bold"), command=self.toggle_auto_alineacion, state=tk.DISABLED)
        self.btn_auto.pack(fill=tk.X, padx=10, pady=5)

        # --- 5. PARO DE EMERGENCIA ---
        self.btn_stop = tk.Button(root, text="⚠ PARO DE EMERGENCIA ⚠", bg="#B71C1C", fg="white", font=("Arial", 16, "bold"), command=self.enviar_stop, state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X, padx=20, pady=10, ipady=15)

        # --- 6. CONSOLA ---
        self.txt_log = scrolledtext.ScrolledText(root, height=8, bg="black", fg="#00FF00", font=("Consolas", 10))
        self.txt_log.pack(padx=20, pady=5, fill=tk.BOTH, expand=True)
        self.log("Sistema GUI iniciado. Cargando modelo IA...")

        threading.Thread(target=self.bucle_camara, daemon=True).start()

    # ==========================================
    # LÓGICA DE INTERFAZ Y SOCKETS
    # ==========================================

    def log(self, mensaje):
        self.txt_log.insert(tk.END, mensaje + "\n")
        self.txt_log.see(tk.END)

    def actualizar_displays(self):
        self.lbl_x.config(text=f"X: {self.pos_x:.2f}")
        self.lbl_y.config(text=f"Y: {self.pos_y:.2f}")
        self.lbl_z.config(text=f"Z: {self.pos_z:.2f}")

    def procesar_respuesta(self, respuesta):
        if "FIN:" in respuesta or "ALERTA:" in respuesta:
            self.robot_ocupado = False

        if "INC:" in respuesta:
            partes = respuesta.split()
            try:
                valor = float(partes[1])
                eje = partes[3] 
                if eje == "X": self.pos_x += valor
                elif eje == "Y": self.pos_y += valor
                elif eje == "Z": self.pos_z += valor
                self.actualizar_displays()
            except: pass
        elif "HOME" in respuesta:
            self.pos_x = self.pos_y = self.pos_z = 0.0
            self.actualizar_displays()
            
        self.log(f"🤖 Robot: {respuesta}")

    def conectar(self):
        try:
            self.sock = socket.socket()
            self.sock.connect((ROBOT_IP, ROBOT_PORT))
            self.conectado = True
            
            self.btn_conectar.config(state=tk.DISABLED)
            self.btn_desconectar.config(state=tk.NORMAL)
            self.btn_enviar.config(state=tk.NORMAL)
            self.btn_auto.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            
            self.log(f"✔ Conectado a {ROBOT_IP}")
            threading.Thread(target=self.escuchar_robot, daemon=True).start()
        except Exception as e: messagebox.showerror("Error", f"Fallo: {e}")

    def desconectar(self):
        self.conectado = False
        self.auto_alineando = False
        self.btn_auto.config(text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
        
        if self.sock: 
            try: self.sock.close() 
            except: pass
            
        self.btn_conectar.config(state=tk.NORMAL)
        self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED)
        self.btn_auto.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.log("❌ Desconectado.")

    def escuchar_robot(self):
        while self.conectado:
            try:
                respuesta = self.sock.recv(1024).decode("latin-1", errors="ignore")
                if respuesta: 
                    self.root.after(0, self.procesar_respuesta, respuesta)
                else: 
                    self.root.after(0, self.desconectar)
                    break
            except: break

    def enviar_texto(self, texto):
        if self.conectado:
            try: 
                self.sock.send(texto.encode("utf-8"))
                self.log(f">> {texto}")
            except: self.desconectar()

    def enviar_comando(self):
        cmd = self.entry_cmd.get().strip().upper()
        if cmd: 
            self.robot_ocupado = True 
            self.enviar_texto(cmd)
            self.entry_cmd.delete(0, tk.END)

    def enviar_stop(self):
        self.log("⚠ PARO SOLICITADO: Cortando conexion...")
        self.auto_alineando = False
        self.btn_auto.config(text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
        self.conectado = False
        self.robot_ocupado = False
        
        if self.sock:
            try: self.sock.close()
            except: pass
            
        self.btn_conectar.config(state=tk.NORMAL)
        self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED)
        self.btn_auto.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.log("Reconectando en 1.5s...")
        self.root.after(1500, self.conectar)

    def toggle_auto_alineacion(self):
        if not self.auto_alineando:
            self.auto_alineando = True
            self.btn_auto.config(text="⏹ DETENER AUTO-ALINEACIÓN", bg="#FF5722")
            self.log("▶ Auto-Alineación ACTIVADA.")
        else:
            self.auto_alineando = False
            self.btn_auto.config(text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
            self.log("⏹ Auto-Alineación DETENIDA.")

    # ==========================================
    # LÓGICA DE VISIÓN ARTIFICIAL Y ROBÓTICA
    # ==========================================

    def bucle_camara(self):
        ruta_modelo = os.path.join(RUTA_PROYECTO, "keras_model.h5")
        ruta_labels = os.path.join(RUTA_PROYECTO, "labels.txt")
        try:
            model = load_model(ruta_modelo, compile=False) 
            class_names = open(ruta_labels, "r").readlines()
            self.log("✔ IA Keras cargada correctamente.")
        except Exception as e:
            self.log(f"❌ Error al cargar IA: {e}")
            return

        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.log("❌ Error de cámara.")
            return

        ancho_camara = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_camara = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        centro_camara_x = ancho_camara // 2
        centro_camara_y = alto_camara // 2
        np.set_printoptions(suppress=True)

        centro_suavizado_x = 0
        centro_suavizado_y = 0
        radio_suavizado = 0

        while True:
            ret, frame = cap.read()
            if not ret: break

            cv2.line(frame, (centro_camara_x, 0), (centro_camara_x, alto_camara), (200, 200, 200), 1)
            cv2.line(frame, (0, centro_camara_y), (ancho_camara, centro_camara_y), (200, 200, 200), 1)
            cv2.circle(frame, (centro_camara_x, centro_camara_y), TOLERANCIA_CENTRO, (255, 255, 0), 1)

            imagen_redimensionada = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
            imagen_array = np.asarray(imagen_redimensionada, dtype=np.float32).reshape(1, 224, 224, 3)
            imagen_normalizada = (imagen_array / 127.5) - 1

            prediccion = model.predict(imagen_normalizada, verbose=0)
            indice_ganador = np.argmax(prediccion) 
            clase_ganadora = class_names[indice_ganador].strip()
            porcentaje_confianza = prediccion[0][indice_ganador]

            if "0" in clase_ganadora and porcentaje_confianza > UMBRAL_CONFIANZA:
                hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                blurred = cv2.medianBlur(hsv_frame, 7) 
                
                lower_cap = np.array([100, 80, 20])
                upper_cap = np.array([130, 255, 255])
                mask_cap = cv2.inRange(blurred, lower_cap, upper_cap)
                
                kernel = np.ones((11, 11), np.uint8)
                mask_cap = cv2.morphologyEx(mask_cap, cv2.MORPH_CLOSE, kernel)

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

                    # 1. Error crudo en píxeles de la cámara
                    error_camara_x = centro_suavizado_x - centro_camara_x
                    error_camara_y = centro_suavizado_y - centro_camara_y
                    
                    cv2.circle(frame, (centro_suavizado_x, centro_suavizado_y), radio_suavizado, (255, 0, 255), 3) 
                    cv2.drawMarker(frame, (centro_suavizado_x, centro_suavizado_y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2) 
                    cv2.line(frame, (centro_camara_x, centro_camara_y), (centro_suavizado_x, centro_suavizado_y), (0, 165, 255), 2) 

                    # 2. Mapeo al sistema de coordenadas del robot
                    if CAMARA_ROTADA_90:
                        error_robot_x = error_camara_y * INVERSOR_ROBOT_X
                        error_robot_y = error_camara_x * INVERSOR_ROBOT_Y
                    else:
                        error_robot_x = error_camara_x * INVERSOR_ROBOT_X
                        error_robot_y = error_camara_y * INVERSOR_ROBOT_Y

                    # --- LÓGICA DE CONTROL DESACOPLADO (X luego Y) ---
                    # Usamos los errores del ROBOT para evaluar el centrado
                    if abs(error_robot_x) <= TOLERANCIA_CENTRO and abs(error_robot_y) <= TOLERANCIA_CENTRO:
                        estado = "¡ALINEADO PERFECTAMENTE!"
                        color_estado = (0, 255, 0)
                        
                        if self.auto_alineando:
                            self.log("🏁 ¡ALINEACIÓN VISUAL COMPLETADA CON ÉXITO!")
                            self.toggle_auto_alineacion()
                    else:
                        estado = f"ROBOT CORRIGE -> X: {-error_robot_x}px | Y: {-error_robot_y}px" 
                        color_estado = (0, 165, 255)
                        
                        # EMISIÓN DE COMANDOS AUTOMÁTICOS AL ROBOT
                        if self.auto_alineando and not self.robot_ocupado:
                            self.robot_ocupado = True # Encendemos el semaforo rojo
                            
                            # Prioridad 1: Corregir el Eje X del ROBOT
                            if abs(error_robot_x) > TOLERANCIA_CENTRO:
                                mm_x = round(error_robot_x * FACTOR_MM_PX, 1)
                                self.log(f"IA: Centrando Eje X. Moviendo {-mm_x} mm...")
                                self.enviar_texto(f"X,{-mm_x}")
                                
                            # Prioridad 2: Si X ya está en el centro, corregir el Eje Y del ROBOT
                            else:
                                mm_y = round(error_robot_y * FACTOR_MM_PX, 1)
                                self.log(f"IA: Centrando Eje Y. Moviendo {-mm_y} mm...")
                                self.enviar_texto(f"Y,{-mm_y}")

                    cv2.putText(frame, estado, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2)
                    cv2.putText(frame, f"Confianza IA: {porcentaje_confianza*100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                else:
                    cv2.putText(frame, "Calculando geometria...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    centro_suavizado_x = 0; centro_suavizado_y = 0
            else:
                centro_suavizado_x = 0; centro_suavizado_y = 0
                cv2.putText(frame, "BUSCANDO BOTELLA...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("Alineacion Visual", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = RobotGUI(root)
    root.mainloop()