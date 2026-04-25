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
RUTA_PROYECTO = "modelos" 

# === COMPENSACIÓN DE PARALAJE (OPCIONAL) ===
# Si después de la Fase 3 notas que el gripper sigue chocando por un par de milímetros,
# ajusta estos valores para mover la cruz roja ligeramente y engañar a la cámara.
OFFSET_X_PIXELES = 0    
OFFSET_Y_PIXELES = 0   

# === VARIABLES AJUSTABLES DE MOVIMIENTO Z (EN MILÍMETROS) ===
PASO_Z_EVASION = -1        
PASO_Z_BUSQUEDA = -20      
PASO_Z_POST_CENTRO_1 = -50 # Bajada tras Fase 1
PASO_Z_ACERCAMIENTO = -80  # Bajada tras Fase 2 (Acerca la cámara a ras de botella)
PASO_Z_INSERCION = -120    # Inserción final con gripper rotado
PASO_Z_DESCARGA = -300     
PASO_Z_SUBIDA_FINAL = 50   

# === VARIABLES AJUSTABLES DE TIEMPO (EN MILISEGUNDOS) ===
TIEMPO_ESPERA_CENTRO_1 = 2000     
TIEMPO_ESPERA_CENTRO_2 = 1000     
TIEMPO_ESPERA_CENTRO_3 = 1000     
TIEMPO_PRE_GRIPPER_ABRIR = 1000   
TIEMPO_PRE_INSERCION = 2000       
TIEMPO_POST_INSERCION = 1000      
TIEMPO_PRE_TRASLADO = 2000        

# === PARÁMETROS DE VISIÓN ARTIFICIAL ===
UMBRAL_CONFIANZA = 0.90 
TOLERANCIA_CENTRO = 30       # Fase 1: Círculo grande
TOLERANCIA_CENTRO_FINA = 5   # Fase 2: Círculo diminuto
TOLERANCIA_CENTRO_ULTRA = 5  # Fase 3: Círculo microscópico
RAFAGA_NORMAL = 30           # mm a deslizar en fase 1
RAFAGA_FINA = 5              # mm a deslizar en fase 2
RAFAGA_ULTRA = 1             # mm a deslizar en fase 3
FACTOR_SUAVIZADO = 0.2 
FACTOR_MM_PX = 0.05  

# === CALIBRACIÓN FÍSICA DE LA CÁMARA ===
CAMARA_ROTADA_90 = True  
INVERSOR_ROBOT_X = 1     
INVERSOR_ROBOT_Y = 1     

class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Control IA + Secuencia 100% Automática (3 Fases)")
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
        self.timer_bloqueo = None 
        
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
        tk.Label(frame_seq, text="SECUENCIA AUTÓNOMA CON GRIPPER", bg="#2d2d2d", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
        
        self.btn_mov_auto = tk.Button(frame_seq, text="🚀 INICIAR MOVIMIENTO AUTÓNOMO", bg="#673AB7", fg="white", font=("Arial", 12, "bold"), command=self.iniciar_secuencia, state=tk.DISABLED)
        self.btn_mov_auto.pack(fill=tk.X, padx=10, pady=5)
        
        frame_seq_btns = tk.Frame(frame_seq, bg="#2d2d2d")
        frame_seq_btns.pack(fill=tk.X, padx=10, pady=5)
        
        self.btn_continuar = tk.Button(frame_seq_btns, text="✔ Secuencia 100% Automática", bg="#607D8B", fg="white", font=("Arial", 10, "bold"), state=tk.DISABLED)
        self.btn_continuar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.btn_ajus_manual = tk.Button(frame_seq_btns, text="⚙ Ajus. Manual", bg="#FFC107", fg="black", font=("Arial", 10, "bold"), command=self.activar_ajuste_manual, state=tk.DISABLED)
        self.btn_ajus_manual.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # --- 4. COMANDOS MANUALES Y PRUEBA IA ---
        frame_cmd = tk.Frame(root, bg="#2d2d2d")
        frame_cmd.pack(pady=5, fill=tk.X, padx=20)
        tk.Label(frame_cmd, text="Comando Manual (ej. X,50 | R,90 | G,1 | V,5):", bg="#2d2d2d", fg="white", font=("Arial", 10)).pack(anchor=tk.W)
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
        
        self.btn_home = tk.Button(frame_actions, text="HOME", bg="#FF9800", fg="white", font=("Arial", 9, "bold"), command=lambda: self.enviar_movimiento("HOME"), state=tk.DISABLED)
        self.btn_home.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.btn_inicio = tk.Button(frame_actions, text="INICIO", bg="#00BCD4", fg="black", font=("Arial", 9, "bold"), command=lambda: self.enviar_movimiento("INICIO"), state=tk.DISABLED)
        self.btn_inicio.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.btn_pos_botella = tk.Button(frame_actions, text="POS_BOTELLA", bg="#E91E63", fg="white", font=("Arial", 8, "bold"), command=lambda: self.enviar_movimiento("POS_BOTELLA"), state=tk.DISABLED)
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
        if self.timer_bloqueo:
            self.timer_bloqueo.cancel()

        # BLINDAJE DE RED: Separa mensajes pegados (ej. "YFIN:")
        resp_limpia = respuesta.replace("FIN:", " FIN: ").replace("ALERTA:", " ALERTA: ").replace("INC:", " INC: ")

        if "INC:" in resp_limpia:
            fragmentos = resp_limpia.split("INC:")
            for frag in fragmentos[1:]: 
                partes = frag.split()
                if len(partes) >= 3:
                    try:
                        valor = float(partes[0])
                        eje = partes[2][0] 
                        if eje == "X": self.pos_x += valor
                        elif eje == "Y": self.pos_y += valor
                        elif eje == "Z": self.pos_z += valor
                    except: pass
            self.actualizar_displays()

        if "FIN:" in resp_limpia or "ALERTA:" in resp_limpia:
            self.robot_ocupado = False
            self.avanzar_secuencia()

        elif "HOME" in resp_limpia:
            self.pos_x = self.pos_y = self.pos_z = 0.0
            self.actualizar_displays()
        elif "INICIO" in resp_limpia:
            self.pos_x = self.pos_y = 0.0
            self.pos_z = -20.0 
            self.actualizar_displays()
        elif "POS_BOTELLA" in resp_limpia:
            self.log("🤖 Robot alcanzó el punto absoluto POS_BOTELLA.")
            
        self.log(f"🤖 Robot: {respuesta}")

    # ==========================================
    # MÁQUINA DE ESTADOS (CEREBRO AUTÓNOMO)
    # ==========================================
    def iniciar_secuencia(self):
        if not self.conectado: return
        self.log("\n🚀 Iniciando Secuencia 100% Autónoma...")
        
        self.btn_ajus_manual.config(state=tk.DISABLED)
        self.btn_mov_auto.config(state=tk.DISABLED)
        
        self.estado_secuencia = "EVADING_SINGULARITY"
        self.auto_alineando = False 
        self.log(f"Sacando al robot de la singularidad (Z, {PASO_Z_EVASION})...")
        self.enviar_movimiento(f"Z,{PASO_Z_EVASION}")

    def avanzar_secuencia(self):
        # --- PREPARACIÓN VISUAL ---
        if self.estado_secuencia == "EVADING_SINGULARITY":
            self.estado_secuencia = "ROTATING_INIT"
            self.log("Singularidad evadida. Girando cámara -90°...")
            self.enviar_movimiento("R,-90")
            
        elif self.estado_secuencia == "ROTATING_INIT":
            self.estado_secuencia = "LOWERING_INIT"
            self.enviar_movimiento(f"Z,{PASO_Z_BUSQUEDA}")
            
        elif self.estado_secuencia == "LOWERING_INIT":
            self.estado_secuencia = "SEARCHING_WAIT"
            self.log("IA: Escaneando área durante 3 segundos...")
            self.tiempo_inicio_busqueda = time.time() 
            
        elif self.estado_secuencia == "SEARCH_PATTERN_1":
            self.estado_secuencia = "SEARCH_PATTERN_2"
            self.enviar_movimiento("X,100")
            
        elif self.estado_secuencia == "SEARCH_PATTERN_2":
            self.estado_secuencia = "SEARCH_PATTERN_3"
            self.enviar_movimiento("Y,-200")
            
        elif self.estado_secuencia == "SEARCH_PATTERN_3":
            self.estado_secuencia = "IDLE"
            self.log("❌ Búsqueda fallida. Botella no encontrada.")
            self.btn_mov_auto.config(state=tk.NORMAL)
            messagebox.showwarning("Error IA", "Botella no encontrada en el área.")
            
        # --- FASE 2: TRAS EL PRIMER CENTRADO VISUAL ---
        elif self.estado_secuencia == "LOWERING_50_1":
            self.estado_secuencia = "SPEED_DOWN"
            self.log("Reduciendo velocidad para Fase 2 de alta precisión...")
            self.enviar_movimiento("V,5")
            
        elif self.estado_secuencia == "SPEED_DOWN":
            self.estado_secuencia = "CENTERING_2"
            self.auto_alineando = True
            self.log("Iniciando Fase 2 (Precisión Fina)...")
            
        # --- FASE 3: ACERCAMIENTO Y TERCER CENTRADO VISUAL ---
        elif self.estado_secuencia == "SPEED_UP":
            self.estado_secuencia = "LOWERING_80"
            self.log(f"Velocidad restaurada. Bajando {PASO_Z_ACERCAMIENTO}mm hacia Fase 3...")
            self.enviar_movimiento(f"Z,{PASO_Z_ACERCAMIENTO}")

        elif self.estado_secuencia == "LOWERING_80":
            self.estado_secuencia = "SPEED_DOWN_3"
            self.log("Reduciendo velocidad para Fase 3 (Ultra Precisión final)...")
            self.enviar_movimiento("V,5")

        elif self.estado_secuencia == "SPEED_DOWN_3":
            self.estado_secuencia = "CENTERING_3"
            self.auto_alineando = True
            self.log("Iniciando Fase 3 (Microscópica) para evitar paralaje...")
            
        # --- TRAS FASE 3: ROTAR GRIPPER Y PREPARAR INSERCIÓN ---
        elif self.estado_secuencia == "SPEED_UP_FINAL":
            self.estado_secuencia = "ROTATING_ZERO"
            self.log("Velocidad restaurada. Rotando a 0° para alinear gripper...")
            self.enviar_movimiento("R,0")
            
        elif self.estado_secuencia == "ROTATING_ZERO":
            self.estado_secuencia = "WAITING_AUTO_PRE_GRIPPER"
            self.log(f"⏸ Rotación lista. Esperando {TIEMPO_PRE_GRIPPER_ABRIR/1000}s de seguridad...")
            self.root.after(TIEMPO_PRE_GRIPPER_ABRIR, self.abrir_gripper_pre_insert)

        # --- SECUENCIA DEL GRIPPER E INSERCIÓN ---
        elif self.estado_secuencia == "OPEN_GRIPPER_PRE_INSERT":
            self.estado_secuencia = "WAITING_AUTO_PRE_INSERCION"
            self.log(f"Gripper abierto. Esperando {TIEMPO_PRE_INSERCION/1000}s de estabilización...")
            self.root.after(TIEMPO_PRE_INSERCION, self.ejecutar_insercion)

        elif self.estado_secuencia == "LOWERING_FINAL_INSERT":
            self.estado_secuencia = "WAITING_AUTO_POST_INSERCION"
            self.log(f"Inserción completada. Esperando {TIEMPO_POST_INSERCION/1000}s...")
            self.root.after(TIEMPO_POST_INSERCION, self.cerrar_gripper_post_insert)

        elif self.estado_secuencia == "CLOSE_GRIPPER_POST_INSERT":
            self.estado_secuencia = "WAITING_AUTO_PRE_TRASLADO"
            self.log(f"Gripper cerrado. Esperando {TIEMPO_PRE_TRASLADO/1000}s antes del traslado final...")
            self.root.after(TIEMPO_PRE_TRASLADO, self.ir_a_pos_botella)

        # --- TRASLADO Y DESCARGA FINAL ---
        elif self.estado_secuencia == "MOVING_POS_BOTELLA":
            self.estado_secuencia = "LOWERING_DESCARGA"
            self.log(f"Bajando la botella a la mesa (Z, {PASO_Z_DESCARGA})...")
            self.enviar_movimiento(f"Z,{PASO_Z_DESCARGA}")

        elif self.estado_secuencia == "LOWERING_DESCARGA":
            self.estado_secuencia = "OPEN_GRIPPER_RELEASE"
            self.log("Abriendo gripper para soltar la botella...")
            self.enviar_movimiento("G,1")

        elif self.estado_secuencia == "OPEN_GRIPPER_RELEASE":
            self.estado_secuencia = "RISING_FINAL"
            self.log(f"Subiendo brazo para escapar (Z, {PASO_Z_SUBIDA_FINAL})...")
            self.enviar_movimiento(f"Z,{PASO_Z_SUBIDA_FINAL}")

        elif self.estado_secuencia == "RISING_FINAL":
            self.estado_secuencia = "CLOSE_GRIPPER_FINAL"
            self.log("Cerrando gripper final...")
            self.enviar_movimiento("G,0")

        elif self.estado_secuencia == "CLOSE_GRIPPER_FINAL":
            self.estado_secuencia = "MOVING_TO_HOME"
            self.log("Regresando a HOME...")
            self.enviar_movimiento("HOME")

        elif self.estado_secuencia == "MOVING_TO_HOME":
            self.estado_secuencia = "IDLE"
            self.btn_mov_auto.config(state=tk.NORMAL)
            self.log("✅ ¡SECUENCIA DE INSERCIÓN Y DESCARGA 100% COMPLETADA!")

    # --- FUNCIONES DE TIEMPO Y TRANSICIÓN ---
    def ejecutar_fase_2(self):
        self.estado_secuencia = "LOWERING_50_1"
        self.log(f"Ejecutando bajada intermedia ({PASO_Z_POST_CENTRO_1}mm en Z)...")
        self.enviar_movimiento(f"Z,{PASO_Z_POST_CENTRO_1}")

    def continuar_fase_3(self):
        self.estado_secuencia = "SPEED_UP"
        self.enviar_movimiento("V,20")

    def continuar_fase_4(self):
        self.estado_secuencia = "SPEED_UP_FINAL"
        self.enviar_movimiento("V,20")

    def abrir_gripper_pre_insert(self):
        self.estado_secuencia = "OPEN_GRIPPER_PRE_INSERT"
        self.log("Abriendo gripper antes de insertar...")
        self.enviar_movimiento("G,1")

    def ejecutar_insercion(self):
        self.estado_secuencia = "LOWERING_FINAL_INSERT"
        self.log(f"Ejecutando inserción final ({PASO_Z_INSERCION}mm)...")
        self.enviar_movimiento(f"Z,{PASO_Z_INSERCION}")

    def cerrar_gripper_post_insert(self):
        self.estado_secuencia = "CLOSE_GRIPPER_POST_INSERT"
        self.log("Cerrando gripper para sujetar la botella...")
        self.enviar_movimiento("G,0")

    def ir_a_pos_botella(self):
        self.estado_secuencia = "MOVING_POS_BOTELLA"
        self.log("Llevando hacia el punto de descarga POS_BOTELLA...")
        self.enviar_movimiento("POS_BOTELLA")

    def activar_ajuste_manual(self):
        self.log("⚙ Ajuste Manual activado. Mueva el robot con comandos.")
        self.btn_ajus_manual.config(state=tk.DISABLED)

    # ==========================================
    # FUNCIONES DE COMUNICACIÓN Y CONTROL
    # ==========================================
    def liberar_bloqueo_timeout(self):
        if self.robot_ocupado:
            self.robot_ocupado = False
            self.log("🔓 TIMEOUT: El robot tardó demasiado en responder. Sistema desbloqueado.")
            if self.estado_secuencia != "IDLE":
                self.btn_mov_auto.config(state=tk.NORMAL)

    def enviar_movimiento(self, comando):
        if self.conectado:
            self.robot_ocupado = True
            if self.timer_bloqueo:
                self.timer_bloqueo.cancel()
            self.timer_bloqueo = threading.Timer(8.0, self.liberar_bloqueo_timeout)
            self.timer_bloqueo.start()
            
            try:
                self.sock.send(comando.encode("utf-8"))
                self.log(f">> {comando}")
            except:
                self.desconectar()

    def enviar_comando(self):
        cmd = self.entry_cmd.get().strip().upper()
        if cmd: 
            self.enviar_movimiento(cmd)
            self.entry_cmd.delete(0, tk.END)

    def conectar(self):
        try:
            self.sock = socket.socket()
            self.sock.connect((ROBOT_IP, ROBOT_PORT))
            self.conectado = True
            self.robot_ocupado = False
            
            self.btn_conectar.config(state=tk.DISABLED)
            self.btn_desconectar.config(state=tk.NORMAL)
            self.btn_enviar.config(state=tk.NORMAL)
            self.btn_auto.config(state=tk.NORMAL)
            self.btn_home.config(state=tk.NORMAL)
            self.btn_inicio.config(state=tk.NORMAL)
            self.btn_pos_botella.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_mov_auto.config(state=tk.NORMAL)
            self.btn_ajus_manual.config(state=tk.NORMAL)
            
            self.log(f"✔ Conectado a {ROBOT_IP}")
            threading.Thread(target=self.escuchar_robot, daemon=True).start()
        except Exception as e: messagebox.showerror("Error", f"Fallo: {e}")

    def desconectar(self):
        self.conectado = False
        self.auto_alineando = False
        self.estado_secuencia = "IDLE"
        self.robot_ocupado = False
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
            self.robot_ocupado = False
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
        np.set_printoptions(suppress=True)

        centro_suavizado_x = 0; centro_suavizado_y = 0; radio_suavizado = 0
        self.centrado_en_curso = False

        while True:
            ret, frame = cap.read()
            if not ret: break

            # APLICAMOS EL OFFSET DE PARALAJE AL CENTRO DE LA CÁMARA
            centro_camara_x = (ancho_camara // 2) + OFFSET_X_PIXELES
            centro_camara_y = (alto_camara // 2) + OFFSET_Y_PIXELES

            # --- DINAMISMO DE PRECISIÓN (3 NIVELES) ---
            tolerancia_actual = TOLERANCIA_CENTRO
            rafaga_actual = RAFAGA_NORMAL

            if self.estado_secuencia == "CENTERING_2":
                tolerancia_actual = TOLERANCIA_CENTRO_FINA
                rafaga_actual = RAFAGA_FINA
            elif self.estado_secuencia == "CENTERING_3":
                tolerancia_actual = TOLERANCIA_CENTRO_ULTRA
                rafaga_actual = RAFAGA_ULTRA

            cv2.line(frame, (centro_camara_x, 0), (centro_camara_x, alto_camara), (200, 200, 200), 1)
            cv2.line(frame, (0, centro_camara_y), (ancho_camara, centro_camara_y), (200, 200, 200), 1)
            cv2.circle(frame, (centro_camara_x, centro_camara_y), tolerancia_actual, (255, 255, 0), 1)

            img_resize = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
            img_norm = (np.asarray(img_resize, dtype=np.float32).reshape(1, 224, 224, 3) / 127.5) - 1

            prediccion = model.predict(img_norm, verbose=0)
            idx = np.argmax(prediccion) 
            clase = class_names[idx].strip()
            confianza = prediccion[0][idx]

            # --- DETECCIÓN CONTINUA ---
            if "0" in clase and confianza > UMBRAL_CONFIANZA:
                self.botella_detectada = True
                
                # INTERRUPTOR DE BÚSQUEDA
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
                    if abs(error_robot_x) <= tolerancia_actual and abs(error_robot_y) <= tolerancia_actual:
                        estado, color_estado = "¡ALINEADO PERFECTAMENTE!", (0, 255, 0)
                        
                        # EL CANDADO MAESTRO DE RED
                        if self.auto_alineando and not self.centrado_en_curso and not self.robot_ocupado and self.conectado:
                            self.centrado_en_curso = True
                            
                            if self.estado_secuencia == "CENTERING_1":
                                self.auto_alineando = False
                                self.estado_secuencia = "WAITING_AUTO_CENTRO_1"
                                self.log(f"🏁 Fase 1 de centrado exitosa. Esperando {TIEMPO_ESPERA_CENTRO_1/1000}s...")
                                self.root.after(TIEMPO_ESPERA_CENTRO_1, self.ejecutar_fase_2)
                                
                            elif self.estado_secuencia == "CENTERING_2":
                                self.auto_alineando = False
                                self.estado_secuencia = "WAITING_AUTO_CENTRO_2"
                                self.log(f"⏸ Fase 2 de centrado exitosa. Esperando {TIEMPO_ESPERA_CENTRO_2/1000}s...")
                                self.root.after(TIEMPO_ESPERA_CENTRO_2, self.continuar_fase_3)

                            elif self.estado_secuencia == "CENTERING_3":
                                self.auto_alineando = False
                                self.estado_secuencia = "WAITING_AUTO_CENTRO_3"
                                self.log(f"⏸ Fase 3 (Ultra Precisión) exitosa. Esperando {TIEMPO_ESPERA_CENTRO_3/1000}s...")
                                self.root.after(TIEMPO_ESPERA_CENTRO_3, self.continuar_fase_4)
                                
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
                            if abs(error_robot_x) > tolerancia_actual:
                                self.eje_actual_ia = "X"
                                dir_x = -rafaga_actual if error_robot_x > 0 else rafaga_actual
                                self.enviar_movimiento(f"X,{dir_x}")
                            elif abs(error_robot_y) > tolerancia_actual:
                                self.eje_actual_ia = "Y"
                                dir_y = -rafaga_actual if error_robot_y > 0 else rafaga_actual
                                self.enviar_movimiento(f"Y,{dir_y}")

                        elif self.robot_ocupado:
                            if hasattr(self, 'eje_actual_ia'):
                                if self.eje_actual_ia == "X" and abs(error_robot_x) <= tolerancia_actual:
                                    self.root.after(0, self.freno_ia)
                                elif self.eje_actual_ia == "Y" and abs(error_robot_y) <= tolerancia_actual:
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
                        self.enviar_movimiento("Y,100")

            # Marcador fijo para visualización del paralaje
            cv2.drawMarker(frame, (centro_camara_x, centro_camara_y), (0, 0, 255), cv2.MARKER_CROSS, 10, 2)

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