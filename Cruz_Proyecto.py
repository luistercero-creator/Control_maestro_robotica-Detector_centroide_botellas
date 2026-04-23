import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
import cv2
import numpy as np
import os
import time
from keras.models import load_model

# === CONFIGURACIONES DE RED Y RUTAS ===
ROBOT_IP = "192.168.125.1" 
ROBOT_PORT = 8000
RUTA_PROYECTO = r"C:\Users\VICTUS\Documents\A_Fotos_Botella" 

# === PARÁMETROS DE VISIÓN ARTIFICIAL ===
UMBRAL_CONFIANZA = 0.90 
TOLERANCIA_CENTRO = 30
FACTOR_SUAVIZADO = 0.2 
FACTOR_MM_PX = 0.05  

# === CALIBRACIÓN FÍSICA DE LA CÁMARA ===
CAMARA_ROTADA_90 = True  
INVERSOR_ROBOT_X = 1     
INVERSOR_ROBOT_Y = 1     

# === CONFIGURACIÓN DE SECUENCIA Z (MEDIDAS RELATIVAS EN MM) ===
# Modifica estas variables si la altura de la mesa o la botella cambia.
PASO_Z_BUSQUEDA = -20      # Baja para comenzar la búsqueda visual
PASO_Z_POST_CENTRO_1 = -50 # Baja intermedia tras el primer centrado
PASO_Z_POST_CENTRO_2 = -50 # Baja al terminar el segundo centrado (Z aprox: -120)
PASO_Z_ACERCAMIENTO = -80  # Baja rápido después de poner la rotación en 0 (Z aprox: -200)
PASO_Z_INSERCION = -40     # Inserción final con permiso humano (Z aprox: -240)

class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Control IA + Secuencia Automática")
        self.root.geometry("550x950") 
        self.root.configure(bg="#2d2d2d")
        
        self.sock = None
        self.conectado = False
        
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0
        
        self.auto_alineando = False
        self.robot_ocupado = False  
        self.eje_actual_ia = ""
        
        self.estado_secuencia = "IDLE"
        self.botella_detectada = False
        self.tiempo_inicio_busqueda = 0
        
        # --- 1. PANEL DE COORDENADAS ---
        frame_coords = tk.Frame(root, bg="#2d2d2d")
        frame_coords.pack(pady=5, fill=tk.X, padx=20)
        tk.Label(frame_coords, text="COORDENADAS ACTUALES (mm)", bg="#2d2d2d", fg="white", font=("Arial", 10, "bold")).pack(pady=2)
        
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

        # --- 3. PANEL DE SECUENCIA AUTOMÁTICA ---
        frame_seq = tk.Frame(root, bg="#2d2d2d", bd=2, relief=tk.RIDGE)
        frame_seq.pack(pady=10, fill=tk.X, padx=20)
        tk.Label(frame_seq, text="SECUENCIA DE INSERCIÓN BOTELLA", bg="#2d2d2d", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        
        self.btn_mov_auto = tk.Button(frame_seq, text="🚀 INICIAR MOV. AUTO.", bg="#673AB7", fg="white", font=("Arial", 12, "bold"), command=self.iniciar_secuencia, state=tk.DISABLED)
        self.btn_mov_auto.pack(fill=tk.X, padx=10, pady=5)
        
        frame_seq_btns = tk.Frame(frame_seq, bg="#2d2d2d")
        frame_seq_btns.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_continuar = tk.Button(frame_seq_btns, text="✔ Continuar", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=self.continuar_secuencia, state=tk.DISABLED)
        self.btn_continuar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.btn_ajus_manual = tk.Button(frame_seq_btns, text="⚙ Ajus. Manual", bg="#FFC107", fg="black", font=("Arial", 10, "bold"), command=self.activar_ajuste_manual, state=tk.DISABLED)
        self.btn_ajus_manual.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # --- 4. COMANDOS MANUALES Y PRUEBA IA ---
        frame_cmd = tk.Frame(root, bg="#2d2d2d")
        frame_cmd.pack(pady=5, fill=tk.X, padx=20)
        tk.Label(frame_cmd, text="Comando Manual (ej. X,50 | R,90):", bg="#2d2d2d", fg="white", font=("Arial", 10)).pack(anchor=tk.W)
        self.entry_cmd = tk.Entry(frame_cmd, font=("Arial", 14))
        self.entry_cmd.pack(fill=tk.X, pady=5)
        self.entry_cmd.bind("<Return>", lambda event: self.enviar_comando())
        self.btn_enviar = tk.Button(frame_cmd, text="Enviar Comando", bg="#2196F3", fg="white", font=("Arial", 10, "bold"), command=self.enviar_comando, state=tk.DISABLED)
        self.btn_enviar.pack(fill=tk.X, pady=5)
        
        self.btn_auto = tk.Button(root, text="▶ INICIAR AUTO-ALINEACIÓN (Prueba Aislada)", bg="#9C27B0", fg="white", font=("Arial", 9, "bold"), command=self.toggle_auto_alineacion, state=tk.DISABLED)
        self.btn_auto.pack(fill=tk.X, padx=20, pady=5)

        # --- 5. ACCIONES RÁPIDAS Y EMERGENCIA ---
        frame_actions = tk.Frame(root, bg="#2d2d2d")
        frame_actions.pack(pady=5, fill=tk.X, padx=20)
        
        self.btn_home = tk.Button(frame_actions, text="HOME", bg="#FF9800", fg="white", font=("Arial", 9, "bold"), command=lambda: self.enviar_texto("HOME"), state=tk.DISABLED)
        self.btn_home.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.btn_inicio = tk.Button(frame_actions, text="INICIO", bg="#00BCD4", fg="black", font=("Arial", 9, "bold"), command=lambda: self.enviar_texto("INICIO"), state=tk.DISABLED)
        self.btn_inicio.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.btn_pos_botella = tk.Button(frame_actions, text="POS_BOTELLA", bg="#E91E63", fg="white", font=("Arial", 8, "bold"), command=lambda: self.enviar_texto("POS_BOTELLA"), state=tk.DISABLED)
        self.btn_pos_botella.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_stop = tk.Button(root, text="⚠ PARO DE EMERGENCIA ⚠", bg="#B71C1C", fg="white", font=("Arial", 16, "bold"), command=self.enviar_stop, state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X, padx=20, pady=10, ipady=15)

        # --- 6. CONSOLA ---
        self.txt_log = scrolledtext.ScrolledText(root, height=6, bg="black", fg="#00FF00", font=("Consolas", 10))
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
            self.avanzar_secuencia()

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
        elif "INICIO" in respuesta:
            self.pos_x = self.pos_y = 0.0
            self.pos_z = -20.0 
            self.actualizar_displays()
        elif "POS_BOTELLA" in respuesta:
            self.log("🤖 Robot alcanzó el punto absoluto POS_BOTELLA.")
            
        self.log(f"🤖 Robot: {respuesta}")

    # ==========================================
    # MÁQUINA DE ESTADOS (NUEVO CEREBRO)
    # ==========================================
    def iniciar_secuencia(self):
        if not self.conectado: return
        self.log("\n🚀 Iniciando Secuencia Automática...")
        self.estado_secuencia = "ROTATING_INIT"
        self.auto_alineando = False 
        self.btn_continuar.config(state=tk.DISABLED)
        self.btn_ajus_manual.config(state=tk.DISABLED)
        self.enviar_texto("R,-90")

    def avanzar_secuencia(self):
        if self.estado_secuencia == "ROTATING_INIT":
            self.estado_secuencia = "LOWERING_INIT"
            self.enviar_texto(f"Z,{PASO_Z_BUSQUEDA}")
            
        elif self.estado_secuencia == "LOWERING_INIT":
            self.estado_secuencia = "SEARCHING_WAIT"
            self.log("IA: Escaneando área durante 3 segundos...")
            self.tiempo_inicio_busqueda = time.time() 
            
        elif self.estado_secuencia == "SEARCH_PATTERN_1":
            self.estado_secuencia = "SEARCH_PATTERN_2"
            self.enviar_texto("X,100")
            
        elif self.estado_secuencia == "SEARCH_PATTERN_2":
            self.estado_secuencia = "SEARCH_PATTERN_3"
            self.enviar_texto("Y,-200")
            
        elif self.estado_secuencia == "SEARCH_PATTERN_3":
            self.estado_secuencia = "IDLE"
            self.log("❌ Búsqueda fallida. Botella no encontrada.")
            messagebox.showwarning("Error IA", "Botella no encontrada en el área de búsqueda.")
            
        elif self.estado_secuencia == "LOWERING_50_1":
            self.estado_secuencia = "CENTERING_2"
            self.auto_alineando = True
            self.log("Iniciando segundo centrado fino...")
            
        elif self.estado_secuencia == "LOWERING_50_2":
            self.estado_secuencia = "ROTATING_ZERO"
            self.enviar_texto("R,0")
            
        elif self.estado_secuencia == "ROTATING_ZERO":
            self.estado_secuencia = "LOWERING_80"
            self.enviar_texto(f"Z,{PASO_Z_ACERCAMIENTO}")
            
        elif self.estado_secuencia == "LOWERING_80":
            self.estado_secuencia = "WAITING_USER_2"
            self.log(f"⏸ Pausa: Acercamiento listo. Confirme para bajar los últimos {abs(PASO_Z_INSERCION)}mm.")
            self.btn_continuar.config(state=tk.NORMAL)
            self.btn_ajus_manual.config(state=tk.NORMAL)
            
        elif self.estado_secuencia == "LOWERING_FINAL_40":
            # NUEVA PAUSA: Espera confirmación antes de ir a Pos_Botella
            self.estado_secuencia = "WAITING_USER_3"
            self.log("⏸ Pausa: Inserción completada. Confirme para mover a POS_BOTELLA.")
            self.btn_continuar.config(state=tk.NORMAL)
            self.btn_ajus_manual.config(state=tk.NORMAL)
            
        elif self.estado_secuencia == "MOVING_POS_BOTELLA":
            self.estado_secuencia = "IDLE"
            self.log("✅ ¡SECUENCIA DE INSERCIÓN Y TRASLADO COMPLETADA CON ÉXITO!")

    def ejecutar_fase_2(self):
        self.estado_secuencia = "LOWERING_50_1"
        self.log(f"Ejecutando bajada intermedia ({PASO_Z_POST_CENTRO_1}mm en Z)...")
        self.enviar_texto(f"Z,{PASO_Z_POST_CENTRO_1}")

    def continuar_secuencia(self):
        self.btn_continuar.config(state=tk.DISABLED)
        self.btn_ajus_manual.config(state=tk.DISABLED)
        
        if self.estado_secuencia == "WAITING_USER_1":
            self.estado_secuencia = "LOWERING_50_2"
            self.log(f"Continuando: Bajando {PASO_Z_POST_CENTRO_2}mm...")
            self.enviar_texto(f"Z,{PASO_Z_POST_CENTRO_2}")
            
        elif self.estado_secuencia == "WAITING_USER_2":
            self.estado_secuencia = "LOWERING_FINAL_40"
            self.log(f"Continuando: Inserción final ({PASO_Z_INSERCION}mm)...")
            self.enviar_texto(f"Z,{PASO_Z_INSERCION}")
            
        elif self.estado_secuencia == "WAITING_USER_3":
            # NUEVO MOVIMIENTO: Viaje a Pos_Botella tras confirmar inserción
            self.estado_secuencia = "MOVING_POS_BOTELLA"
            self.log("Llevando hacia el punto final POS_BOTELLA...")
            self.enviar_texto("POS_BOTELLA")

    def activar_ajuste_manual(self):
        self.log("⚙ Ajuste Manual activado. Mueva el robot con comandos y presione 'Continuar'.")
        self.btn_ajus_manual.config(state=tk.DISABLED)

    # ==========================================
    # FUNCIONES DE COMUNICACIÓN
    # ==========================================
    def conectar(self):
        try:
            self.sock = socket.socket()
            self.sock.connect((ROBOT_IP, ROBOT_PORT))
            self.conectado = True
            
            self.btn_conectar.config(state=tk.DISABLED)
            self.btn_desconectar.config(state=tk.NORMAL)
            self.btn_enviar.config(state=tk.NORMAL)
            self.btn_auto.config(state=tk.NORMAL)
            self.btn_home.config(state=tk.NORMAL)
            self.btn_inicio.config(state=tk.NORMAL)
            self.btn_pos_botella.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_mov_auto.config(state=tk.NORMAL)
            
            self.log(f"✔ Conectado a {ROBOT_IP}")
            threading.Thread(target=self.escuchar_robot, daemon=True).start()
        except Exception as e: messagebox.showerror("Error", f"Fallo: {e}")

    def desconectar(self):
        self.conectado = False
        self.auto_alineando = False
        self.estado_secuencia = "IDLE"
        self.btn_auto.config(text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
        
        if self.sock: 
            try: self.sock.close() 
            except: pass
            
        self.btn_conectar.config(state=tk.NORMAL)
        self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED)
        self.btn_auto.config(state=tk.DISABLED)
        self.btn_home.config(state=tk.DISABLED)
        self.btn_inicio.config(state=tk.DISABLED)
        self.btn_pos_botella.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_mov_auto.config(state=tk.DISABLED)
        self.btn_continuar.config(state=tk.DISABLED)
        self.btn_ajus_manual.config(state=tk.DISABLED)
        self.log("❌ Desconectado.")

    def escuchar_robot(self):
        while self.conectado:
            try:
                respuesta = self.sock.recv(1024).decode("latin-1", errors="ignore")
                if respuesta: self.root.after(0, self.procesar_respuesta, respuesta)
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
        self.estado_secuencia = "IDLE"
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
        self.btn_home.config(state=tk.DISABLED)
        self.btn_inicio.config(state=tk.DISABLED)
        self.btn_pos_botella.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_mov_auto.config(state=tk.DISABLED)
        self.btn_continuar.config(state=tk.DISABLED)
        self.btn_ajus_manual.config(state=tk.DISABLED)
        self.log("Reconectando en 1.5s...")
        self.root.after(1500, self.conectar)

    def freno_ia(self):
        self.log(f"🎯 Centro cruzado. Freno de emergencia automático activado.")
        self.conectado = False
        if self.sock:
            try: self.sock.close()
            except: pass
        
        self.robot_ocupado = False
        self.btn_conectar.config(state=tk.NORMAL)
        self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED)
        self.btn_home.config(state=tk.DISABLED)
        self.btn_inicio.config(state=tk.DISABLED)
        self.btn_pos_botella.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_mov_auto.config(state=tk.DISABLED)
        
        self.log("Reconectando en 1.5s para evaluar el siguiente eje...")
        self.root.after(1500, self.conectar)

    def toggle_auto_alineacion(self):
        if not self.auto_alineando:
            self.auto_alineando = True
            self.btn_auto.config(text="⏹ DETENER AUTO-ALINEACIÓN", bg="#FF5722")
            self.log("▶ Alineación de Prueba ACTIVADA.")
        else:
            self.auto_alineando = False
            self.btn_auto.config(text="▶ INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
            self.log("⏹ Alineación de Prueba DETENIDA.")

    # ==========================================
    # LÓGICA DE VISIÓN ARTIFICIAL
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

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.log("❌ Error de cámara.")
            return

        ancho_camara = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_camara = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        centro_camara_x = ancho_camara // 2
        centro_camara_y = alto_camara // 2
        np.set_printoptions(suppress=True)

        centro_suavizado_x = 0; centro_suavizado_y = 0; radio_suavizado = 0
        self.centrado_en_curso = False

        while True:
            ret, frame = cap.read()
            if not ret: break

            cv2.line(frame, (centro_camara_x, 0), (centro_camara_x, alto_camara), (200, 200, 200), 1)
            cv2.line(frame, (0, centro_camara_y), (ancho_camara, centro_camara_y), (200, 200, 200), 1)
            cv2.circle(frame, (centro_camara_x, centro_camara_y), TOLERANCIA_CENTRO, (255, 255, 0), 1)

            img_resize = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
            img_norm = (np.asarray(img_resize, dtype=np.float32).reshape(1, 224, 224, 3) / 127.5) - 1

            prediccion = model.predict(img_norm, verbose=0)
            idx = np.argmax(prediccion) 
            clase = class_names[idx].strip()
            confianza = prediccion[0][idx]

            # --- DETECCIÓN CONTINUA ---
            if "0" in clase and confianza > UMBRAL_CONFIANZA:
                self.botella_detectada = True
                
                # INTERRUPTOR DE BÚSQUEDA: Si la ve mientras barrea o espera, aborta y centra
                if self.estado_secuencia in ["SEARCHING_WAIT", "SEARCH_PATTERN_1", "SEARCH_PATTERN_2", "SEARCH_PATTERN_3"]:
                    self.log("👁 ¡Botella detectada! Abortando búsqueda y centrando...")
                    self.estado_secuencia = "CENTERING_1"
                    self.auto_alineando = True
                    if self.robot_ocupado:
                        self.root.after(0, self.freno_ia) 
                
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                blurred = cv2.medianBlur(hsv, 7) 
                mask = cv2.inRange(blurred, np.array([100, 80, 20]), np.array([130, 255, 255]))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
                circulos = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100, param1=50, param2=18, minRadius=15, maxRadius=200)

                if circulos is not None:
                    (x_crudo, y_crudo, r_crudo) = np.round(circulos[0, :]).astype("int")[0]
                    if centro_suavizado_x == 0:
                        centro_suavizado_x, centro_suavizado_y, radio_suavizado = x_crudo, y_crudo, r_crudo
                    else:
                        centro_suavizado_x = int((x_crudo * FACTOR_SUAVIZADO) + (centro_suavizado_x * (1.0 - FACTOR_SUAVIZADO)))
                        centro_suavizado_y = int((y_crudo * FACTOR_SUAVIZADO) + (centro_suavizado_y * (1.0 - FACTOR_SUAVIZADO)))
                        radio_suavizado = int((r_crudo * FACTOR_SUAVIZADO) + (radio_suavizado * (1.0 - FACTOR_SUAVIZADO)))

                    error_camara_x = centro_suavizado_x - centro_camara_x
                    error_camara_y = centro_suavizado_y - centro_camara_y
                    
                    cv2.circle(frame, (centro_suavizado_x, centro_suavizado_y), radio_suavizado, (255, 0, 255), 3) 
                    cv2.drawMarker(frame, (centro_suavizado_x, centro_suavizado_y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2) 
                    cv2.line(frame, (centro_camara_x, centro_camara_y), (centro_suavizado_x, centro_suavizado_y), (0, 165, 255), 2) 

                    if CAMARA_ROTADA_90:
                        error_robot_x = error_camara_y * INVERSOR_ROBOT_X
                        error_robot_y = error_camara_x * INVERSOR_ROBOT_Y
                    else:
                        error_robot_x = error_camara_x * INVERSOR_ROBOT_X
                        error_robot_y = error_camara_y * INVERSOR_ROBOT_Y

                    # --- EVALUACIÓN DE CENTRADO EXITOSO ---
                    if abs(error_robot_x) <= TOLERANCIA_CENTRO and abs(error_robot_y) <= TOLERANCIA_CENTRO:
                        estado, color_estado = "¡ALINEADO PERFECTAMENTE!", (0, 255, 0)
                        
                        if self.auto_alineando and not self.centrado_en_curso:
                            self.centrado_en_curso = True
                            
                            if self.estado_secuencia == "CENTERING_1":
                                self.auto_alineando = False
                                self.estado_secuencia = "WAITING_2S"
                                self.log("🏁 Primer centrado exitoso. Esperando 2s...")
                                self.root.after(2000, self.ejecutar_fase_2)
                                
                            elif self.estado_secuencia == "CENTERING_2":
                                self.auto_alineando = False
                                self.estado_secuencia = "WAITING_USER_1"
                                self.log("⏸ Segundo centrado exitoso. ¿Desea Continuar o Ajustar?")
                                self.root.after(0, lambda: self.btn_continuar.config(state=tk.NORMAL))
                                self.root.after(0, lambda: self.btn_ajus_manual.config(state=tk.NORMAL))
                                
                            elif self.estado_secuencia == "IDLE": 
                                self.log("🏁 ¡ALINEACIÓN PERFECTA (Modo Prueba)!")
                                self.root.after(0, self.toggle_auto_alineacion)

                    else:
                        self.centrado_en_curso = False
                        estado = f"ROBOT CORRIGE -> X: {-error_robot_x}px | Y: {-error_robot_y}px" 
                        color_estado = (0, 165, 255)

                    # --- DESLIZAMIENTO DE CORRECCIÓN ---
                    if self.auto_alineando:
                        if not self.robot_ocupado:
                            if abs(error_robot_x) > TOLERANCIA_CENTRO:
                                self.robot_ocupado = True
                                self.eje_actual_ia = "X"
                                dir_x = -30 if error_robot_x > 0 else 30
                                self.enviar_texto(f"X,{dir_x}")
                            elif abs(error_robot_y) > TOLERANCIA_CENTRO:
                                self.robot_ocupado = True
                                self.eje_actual_ia = "Y"
                                dir_y = -30 if error_robot_y > 0 else 30
                                self.enviar_texto(f"Y,{dir_y}")

                        elif self.robot_ocupado:
                            if hasattr(self, 'eje_actual_ia'):
                                if self.eje_actual_ia == "X" and abs(error_robot_x) <= TOLERANCIA_CENTRO:
                                    self.root.after(0, self.freno_ia)
                                elif self.eje_actual_ia == "Y" and abs(error_robot_y) <= TOLERANCIA_CENTRO:
                                    self.root.after(0, self.freno_ia)

                    cv2.putText(frame, estado, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2)
                    cv2.putText(frame, f"Confianza IA: {confianza*100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                else:
                    cv2.putText(frame, "Calculando geometria...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    centro_suavizado_x, centro_suavizado_y = 0, 0
            else:
                self.botella_detectada = False
                centro_suavizado_x, centro_suavizado_y = 0, 0
                cv2.putText(frame, "BUSCANDO BOTELLA...", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # TEMPORIZADOR DE BÚSQUEDA
                if self.estado_secuencia == "SEARCHING_WAIT":
                    if time.time() - self.tiempo_inicio_busqueda > 3.0:
                        self.estado_secuencia = "SEARCH_PATTERN_1"
                        self.log("IA: Botella no vista. Iniciando patrón de barrido...")
                        self.enviar_texto("Y,100")

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