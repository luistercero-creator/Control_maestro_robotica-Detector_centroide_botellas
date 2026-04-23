import customtkinter as ctk
import cv2
from PIL import Image
import os

# Importaciones de tus módulos locales
from vision_servicio import CameraService
from config import CONFIG
from control_logica import ControlLogic
from registrador import AppLogger
from robot_controlador import RobotController
from vision_procesamiento import VisionProcessor

class RobotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- CONFIGURACIÓN DE VENTANA ---
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Consola ABB + Visión IA - ULSA 2026")
        self.geometry("1250x850")
        
        # Esto hace que la app inicie maximizada correctamente
        self.after(100, lambda: self.state('zoomed'))

        # --- ESTADO INICIAL ---
        self.auto_mode = False
        self.running = True
        self.current_image = None

        # --- INICIALIZACIÓN DE SERVICIOS ---
        self.logger = AppLogger(self._append_log_safe)
        self.robot = RobotController(CONFIG, self.logger, on_state_change=self._on_robot_state_change)
        self.vision = VisionProcessor(CONFIG, self.logger)
        self.control = ControlLogic(CONFIG)
        
        # Servicio de cámara (Mantiene el flujo de video)
        self.camera = CameraService(
            CONFIG,
            self.vision,
            self.control,
            self.robot,
            self.logger,
            on_frame=self._on_frame_ready,
        )

        # --- CONSTRUCCIÓN DE INTERFAZ ---
        self._build_ui()
        
        # Manejo de cierre de ventana
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- CARGA DE MODELO Y ARRANQUE ---
        if not self.vision.load_model():
            self._append_log("❌ ERROR: No se pudo cargar el modelo IA. Revisa las versiones de Keras/Python.")

        self._update_robot_state(self.robot.get_state())
        self.camera.start()

    def _build_ui(self):
        # Configuración de pesos de la cuadrícula principal
        self.grid_columnconfigure(0, weight=0) # Panel fijo
        self.grid_columnconfigure(1, weight=1) # Video expandible
        self.grid_rowconfigure(0, weight=1)

        # --- PANEL IZQUIERDO (CON SCROLL PARA EVITAR QUE SE CORTEN BOTONES) ---
        self.left_panel = ctk.CTkScrollableFrame(self, corner_radius=18, width=330)
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=16, pady=16)

        # Títulos
        ctk.CTkLabel(self.left_panel, text="Consola ABB", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(self.left_panel, text="Control y Seguimiento IA", text_color="#A0A0A0").pack(anchor="w", padx=16, pady=(0, 12))

        # Tarjeta de Estado de Conexión
        self.status_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        self.status_card.pack(fill="x", padx=16, pady=(0, 12))
        self.lbl_connection = ctk.CTkLabel(self.status_card, text="Desconectado", font=ctk.CTkFont(weight="bold"))
        self.lbl_connection.pack(anchor="w", padx=14, pady=(12, 4))
        self.lbl_busy = ctk.CTkLabel(self.status_card, text="Robot libre", text_color="#A0A0A0")
        self.lbl_busy.pack(anchor="w", padx=14, pady=(0, 12))

        # Coordenadas
        coords_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        coords_card.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(coords_card, text="Coordenadas (mm)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 8))
        self.lbl_x = ctk.CTkLabel(coords_card, text="X: 0.00", font=ctk.CTkFont(size=18, weight="bold")); self.lbl_x.pack(anchor="w", padx=14, pady=2)
        self.lbl_y = ctk.CTkLabel(coords_card, text="Y: 0.00", font=ctk.CTkFont(size=18, weight="bold")); self.lbl_y.pack(anchor="w", padx=14, pady=2)
        self.lbl_z = ctk.CTkLabel(coords_card, text="Z: 0.00", font=ctk.CTkFont(size=18, weight="bold")); self.lbl_z.pack(anchor="w", padx=14, pady=(2, 12))

        # Botones Conexión
        conn_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        conn_card.pack(fill="x", padx=16, pady=(0, 12))
        self.btn_connect = ctk.CTkButton(conn_card, text="Conectar", command=self.connect_robot); self.btn_connect.pack(fill="x", padx=14, pady=(12, 8))
        self.btn_disconnect = ctk.CTkButton(conn_card, text="Desconectar", command=self.disconnect_robot, fg_color="#C62828", hover_color="#A61E1E")
        self.btn_disconnect.pack(fill="x", padx=14, pady=(0, 12))

        # Comandos Manuales
        cmd_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        cmd_card.pack(fill="x", padx=16, pady=(0, 12))
        self.entry_cmd = ctk.CTkEntry(cmd_card, placeholder_text="Ej: X,50 o HOME"); self.entry_cmd.pack(fill="x", padx=14, pady=(12, 8))
        self.btn_send = ctk.CTkButton(cmd_card, text="Enviar", command=self.send_manual_command); self.btn_send.pack(fill="x", padx=14, pady=(0, 12))

        # CONTROL IA (Asegurado que no se corte)
        ia_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        ia_card.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(ia_card, text="Control Inteligente", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=14, pady=(12, 8))
        self.btn_auto = ctk.CTkButton(ia_card, text="Iniciar autoalineación", command=self.toggle_auto_alignment, fg_color="#7B1FA2", hover_color="#6A1B9A")
        self.btn_auto.pack(fill="x", padx=14, pady=(0, 8))
        self.btn_stop = ctk.CTkButton(ia_card, text="PARO DE EMERGENCIA", command=self.emergency_stop, fg_color="#B71C1C", hover_color="#8E1515")
        self.btn_stop.pack(fill="x", padx=14, pady=(0, 12))

        # Estado Visión
        vision_info = ctk.CTkFrame(self.left_panel, corner_radius=14)
        vision_info.pack(fill="x", padx=16, pady=(0, 12))
        self.lbl_vision_status = ctk.CTkLabel(vision_info, text="Esperando cámara..."); self.lbl_vision_status.pack(anchor="w", padx=14, pady=2)
        self.lbl_confidence = ctk.CTkLabel(vision_info, text="Confianza IA: 0%"); self.lbl_confidence.pack(anchor="w", padx=14, pady=(0, 12))

        # --- PANEL DERECHO (CONTENEDOR DE VIDEO) ---
        self.right_panel = ctk.CTkFrame(self, corner_radius=18)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        self.right_panel.grid_rowconfigure(1, weight=1) # El video ocupa todo el centro
        self.right_panel.grid_columnconfigure(0, weight=1)

        self.video_title = ctk.CTkLabel(self.right_panel, text="Cámara en Vivo - Detector de Centroides", font=ctk.CTkFont(size=22, weight="bold"))
        self.video_title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        # El video_label ahora tiene sticky="nsew" para llenar todo el espacio
        self.video_label = ctk.CTkLabel(self.right_panel, text="Iniciando Stream...", anchor="center", fg_color="#1a1a1a", corner_radius=12)
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        self.log_box = ctk.CTkTextbox(self.right_panel, height=150, corner_radius=14)
        self.log_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

        self._set_connected_ui(False)

    def _render_frame(self, frame, analysis) -> None:
        """Renderiza el frame ajustando el tamaño al espacio disponible en pantalla."""
        # 1. Convertir BGR a RGB para PIL
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_raw = Image.fromarray(rgb)
        
        # 2. Obtener dimensiones dinámicas del widget (Pantalla completa ready)
        w = self.video_label.winfo_width()
        h = self.video_label.winfo_height()
        
        # Valores por defecto si la ventana no ha cargado totalmente
        if w < 100 or h < 100: w, h = 820, 615

        # 3. Redimensionar imagen con alta calidad (Sin cortes)
        img_resized = img_raw.resize((w, h), Image.Resampling.LANCZOS)

        # 4. Actualizar el widget de video
        self.current_image = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=(w, h))
        self.video_label.configure(image=self.current_image, text="")

        # 5. Actualizar labels de visión
        self.lbl_vision_status.configure(text=analysis.status_text)
        self.lbl_confidence.configure(text=f"Confianza IA: {analysis.confidence * 100:.0f}%")

    # --- MÉTODOS DE SOPORTE (LOGS Y ROBOT) ---
    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"> {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _append_log_safe(self, message: str) -> None:
        self.after(0, self._append_log, message)

    def _set_connected_ui(self, connected: bool) -> None:
        st = "normal" if connected else "disabled"
        self.btn_disconnect.configure(state=st); self.btn_send.configure(state=st)
        self.btn_auto.configure(state=st); self.btn_stop.configure(state=st)
        if connected:
            self.lbl_connection.configure(text=f"✅ CONECTADO: {CONFIG.robot_ip}", text_color="#81C784")
        else:
            self.lbl_connection.configure(text="❌ DESCONECTADO", text_color="#FF8A80")

    def _update_robot_state(self, state) -> None:
        self.lbl_x.configure(text=f"X: {state.pos_x:.2f}")
        self.lbl_y.configure(text=f"Y: {state.pos_y:.2f}")
        self.lbl_z.configure(text=f"Z: {state.pos_z:.2f}")
        self.lbl_busy.configure(text="Robot ocupado" if state.busy else "Robot libre", 
                                 text_color="#FFD54F" if state.busy else "#A0A0A0")
        self._set_connected_ui(state.connected)

    def _on_robot_state_change(self, state) -> None:
        self.after(0, self._update_robot_state, state)

    def _on_frame_ready(self, frame, analysis) -> None:
        self.after(0, self._render_frame, frame, analysis)

    # --- ACCIONES DE BOTONES ---
    def connect_robot(self):
        if self.robot.connect(): self._append_log("Conectando con ABB IRB 140...")
        else: self._append_log("Fallo de conexión. Revisa IP/Puerto.")

    def disconnect_robot(self):
        self.auto_mode = False
        self._update_auto_button()
        self.robot.disconnect()

    def send_manual_command(self):
        cmd = self.entry_cmd.get().strip().upper()
        if cmd and self.robot.send_command(cmd):
            self._append_log(f"Comando enviado: {cmd}")
            self.entry_cmd.delete(0, "end")

    def toggle_auto_alignment(self):
        self.auto_mode = not self.auto_mode
        self._update_auto_button()
        self._append_log("MODO AUTO: ACTIVADO" if self.auto_mode else "MODO AUTO: DETENIDO")

    def _update_auto_button(self):
        if self.auto_mode:
            self.btn_auto.configure(text="Detener autoalineación", fg_color="#D84315", hover_color="#BF360C")
        else:
            self.btn_auto.configure(text="Iniciar autoalineación", fg_color="#7B1FA2", hover_color="#6A1B9A")

    def emergency_stop(self):
        self.auto_mode = False
        self._update_auto_button()
        self.robot.emergency_stop() # Asumiendo que implementaste este método en el controlador
        self._append_log("⚠️ PARO DE EMERGENCIA EJECUTADO")

    def on_close(self):
        self.camera.stop()
        self.robot.disconnect()
        self.destroy()
