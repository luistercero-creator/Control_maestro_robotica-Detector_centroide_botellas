import customtkinter as ctk
import cv2
from PIL import Image
import os

# Importaciones de tus módulos de lógica
from vision_servicio import CameraService
from config import CONFIG
from control_logica import ControlLogic
from registrador import AppLogger
from robot_controlador import RobotController
from vision_procesamiento import VisionProcessor

class RobotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- 1. CONFIGURACIÓN DE VENTANA ---
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Consola ABB + Visión IA - ULSA 2026")
        self.geometry("1250x850")
        
        # Maximizar automáticamente en Windows
        self.after(100, lambda: self.state('zoomed'))

        # --- 2. ESTADO INICIAL ---
        self.auto_mode = False
        self.running = True
        self.current_image = None

        # --- 3. INICIALIZACIÓN DE COMPONENTES ---
        self.logger = AppLogger(self._append_log_safe)
        self.robot = RobotController(CONFIG, self.logger, on_state_change=self._on_robot_state_change)
        self.vision = VisionProcessor(CONFIG, self.logger)
        self.control = ControlLogic(CONFIG)
        
        # Servicio de cámara
        self.camera = CameraService(
            CONFIG, self.vision, self.control, self.robot, self.logger,
            on_frame=self._on_frame_ready,
        )

        # --- 4. CONSTRUCCIÓN DE INTERFAZ ---
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- 5. ARRANQUE ---
        if not self.vision.load_model():
            self._append_log("❌ ERROR: No se pudo cargar el modelo IA.")

        self._update_robot_state(self.robot.get_state())
        self.camera.start()

    def _build_ui(self):
        # Colores de la paleta Estilo Neumorfismo
        BG_COLOR = "#1e1e1e"        
        CARD_COLOR = "#2b2b2b"      
        ACCENT_BLUE = "#3498db"     
        ACCENT_PURPLE = "#9b59b6"   
        TEXT_DIM = "#a0a0a0"

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # PANEL IZQUIERDO (CON SCROLL Y TARJETAS)
        # ==========================================
        self.left_panel = ctk.CTkScrollableFrame(self, corner_radius=20, width=350, fg_color=BG_COLOR)
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=15, pady=15)

        # Títulos
        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(15, 20))
        ctk.CTkLabel(header, text="Consola ABB", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text="Control, visión y seguimiento", text_color=TEXT_DIM).pack(anchor="w")

        # Tarjeta: Conexión
        conn_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        conn_card.pack(fill="x", padx=10, pady=8)
        self.lbl_connection = ctk.CTkLabel(conn_card, text="● Desconectado", text_color="#ef9a9a", font=ctk.CTkFont(weight="bold"))
        self.lbl_connection.pack(pady=(15, 2), padx=15, anchor="w")
        self.lbl_busy = ctk.CTkLabel(conn_card, text="Robot libre", text_color=TEXT_DIM)
        self.lbl_busy.pack(pady=(0, 15), padx=15, anchor="w")

        # Tarjeta: Coordenadas
        coords_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        coords_card.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(coords_card, text="Coordenadas actuales (mm)", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 8), padx=15, anchor="w")
        self.lbl_x = ctk.CTkLabel(coords_card, text="X: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_x.pack(padx=20, anchor="w")
        self.lbl_y = ctk.CTkLabel(coords_card, text="Y: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_y.pack(padx=20, anchor="w")
        self.lbl_z = ctk.CTkLabel(coords_card, text="Z: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_z.pack(padx=20, pady=(0, 15), anchor="w")

        # Tarjeta: Botones Conexión
        btn_conn_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        btn_conn_card.pack(fill="x", padx=10, pady=8)
        self.btn_connect = ctk.CTkButton(btn_conn_card, text="Conectar", fg_color=ACCENT_BLUE, height=35, command=self.connect_robot)
        self.btn_connect.pack(fill="x", padx=15, pady=(15, 8))
        self.btn_disconnect = ctk.CTkButton(btn_conn_card, text="Desconectar", fg_color="#e74c3c", height=35, command=self.disconnect_robot)
        self.btn_disconnect.pack(fill="x", padx=15, pady=(0, 15))

        # Tarjeta: Manual
        manual_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        manual_card.pack(fill="x", padx=10, pady=8)
        self.entry_cmd = ctk.CTkEntry(manual_card, placeholder_text="Escribe el comando", fg_color="#333333")
        self.entry_cmd.pack(fill="x", padx=15, pady=(15, 8))
        self.btn_send = ctk.CTkButton(manual_card, text="Enviar comando", fg_color=ACCENT_BLUE, command=self.send_manual_command)
        self.btn_send.pack(fill="x", padx=15, pady=(0, 15))

        # Tarjeta: IA
        ia_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        ia_card.pack(fill="x", padx=10, pady=8)
        self.btn_auto = ctk.CTkButton(ia_card, text="Iniciar autoalineación", fg_color=ACCENT_PURPLE, height=45, font=ctk.CTkFont(weight="bold"), command=self.toggle_auto_alignment)
        self.btn_auto.pack(fill="x", padx=15, pady=15)
        self.btn_stop = ctk.CTkButton(ia_card, text="PARO DE EMERGENCIA", fg_color="#B71C1C", height=45, command=self.emergency_stop)
        self.btn_stop.pack(fill="x", padx=15, pady=(0, 15))

        # Tarjeta: Info Visión
        vis_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        vis_card.pack(fill="x", padx=10, pady=8)
        self.lbl_vision_status = ctk.CTkLabel(vis_card, text="Esperando cámara...")
        self.lbl_vision_status.pack(pady=(10, 2), padx=15, anchor="w")
        self.lbl_confidence = ctk.CTkLabel(vis_card, text="Confianza IA: 0%")
        self.lbl_confidence.pack(pady=(0, 10), padx=15, anchor="w")

        # ==========================================
        # PANEL DERECHO (VIDEO PRIORIZADO Y CONSOLA)
        # ==========================================
        self.right_panel = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_COLOR)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 15), pady=15)
        
        # Le decimos a la cuadrícula que TODA la expansión vertical sea para la fila 1 (el video)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.right_panel, text="Cámara en vivo", font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w", padx=20, pady=(15, 5))

        # Etiqueta de video con expansión total asegurada
        self.video_label = ctk.CTkLabel(self.right_panel, text="Cargando stream...", fg_color="#000000", corner_radius=15)
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)

        # Consola reducida a tamaño fijo (sin el ipady que robaba espacio)
        ctk.CTkLabel(self.right_panel, text="Consola", font=ctk.CTkFont(size=16, weight="bold")).grid(row=2, column=0, sticky="w", padx=20, pady=(5, 0))
        self.log_box = ctk.CTkTextbox(self.right_panel, height=120, corner_radius=15, fg_color=CARD_COLOR, border_width=1, border_color="#3d3d3d")
        self.log_box.grid(row=3, column=0, sticky="ew", padx=20, pady=(5, 15))
        self.log_box.configure(state="disabled")

    def _render_frame(self, frame, analysis) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_raw = Image.fromarray(rgb)
        
        # Tamaño dinámico ajustado al espacio disponible real
        w = self.video_label.winfo_width()
        h = self.video_label.winfo_height()
        if w < 100: w, h = 820, 615

        img_resized = img_raw.resize((w, h), Image.Resampling.LANCZOS)
        self.current_image = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=(w, h))
        self.video_label.configure(image=self.current_image, text="")

        self.lbl_vision_status.configure(text=analysis.status_text)
        self.lbl_confidence.configure(text=f"Confianza IA: {analysis.confidence * 100:.0f}%")

    # --- LÓGICA DE APOYO ---
    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"> {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _append_log_safe(self, message: str) -> None:
        self.after(0, self._append_log, message)

    def _on_robot_state_change(self, state) -> None:
        self.after(0, self._update_robot_state, state)

    def _update_robot_state(self, state) -> None:
        self.lbl_x.configure(text=f"X: {state.pos_x:.2f}")
        self.lbl_y.configure(text=f"Y: {state.pos_y:.2f}")
        self.lbl_z.configure(text=f"Z: {state.pos_z:.2f}")
        self.lbl_connection.configure(
            text="● Conectado" if state.connected else "● Desconectado",
            text_color="#81C784" if state.connected else "#ef9a9a"
        )
        self.lbl_busy.configure(text="Robot ocupado" if state.busy else "Robot libre")

    def _on_frame_ready(self, frame, analysis) -> None:
        self.after(0, self._render_frame, frame, analysis)

    def connect_robot(self): self.robot.connect()
    def disconnect_robot(self): self.robot.disconnect()
    def send_manual_command(self):
        cmd = self.entry_cmd.get().strip().upper()
        if cmd and self.robot.send_command(cmd): self.entry_cmd.delete(0, "end")

    def toggle_auto_alignment(self):
        self.auto_mode = not self.auto_mode
        self.btn_auto.configure(
            text="Detener autoalineación" if self.auto_mode else "Iniciar autoalineación",
            fg_color="#D84315" if self.auto_mode else "#9b59b6"
        )

    def emergency_stop(self):
        self.auto_mode = False
        self.robot.disconnect()
        self._append_log("⚠️ PARO DE EMERGENCIA")

    def on_close(self):
        self.camera.stop()
        self.robot.disconnect()
        self.destroy()
