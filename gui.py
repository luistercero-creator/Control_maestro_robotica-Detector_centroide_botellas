import customtkinter as ctk
import cv2
from PIL import Image

from vision_servicio import CameraService
from config import CONFIG
from control_logica import ControlLogic
from registrador import AppLogger
from robot_controlador import RobotController
from vision_procesamiento import VisionProcessor


class RobotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Consola ABB + Visión IA")
        self.geometry("1250x850")
        self.minsize(1150, 780)

        self.auto_mode = False
        self.running = True
        self.current_image = None

        self.logger = AppLogger(self._append_log_safe)
        self.robot = RobotController(CONFIG, self.logger, on_state_change=self._on_robot_state_change)
        self.vision = VisionProcessor(CONFIG, self.logger)
        self.control = ControlLogic(CONFIG)
        self.camera = CameraService(
            CONFIG,
            self.vision,
            self.control,
            self.robot,
            self.logger,
            on_frame=self._on_frame_ready,
        )

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if not self.vision.load_model():
            self._append_log("No se pudo cargar el modelo IA.")

        self._update_robot_state(self.robot.get_state())
        self.camera.start()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(self, corner_radius=18, width=330)
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=16, pady=16)
        self.left_panel.grid_propagate(False)

        self.right_panel = ctk.CTkFrame(self, corner_radius=18)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.left_panel, text="Consola ABB", font=ctk.CTkFont(size=24, weight="bold")).pack(
            anchor="w", padx=16, pady=(16, 4)
        )
        ctk.CTkLabel(self.left_panel, text="Control, visión y seguimiento", text_color="#A0A0A0").pack(
            anchor="w", padx=16, pady=(0, 12)
        )

        self.status_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        self.status_card.pack(fill="x", padx=16, pady=(0, 12))

        self.lbl_connection = ctk.CTkLabel(self.status_card, text="Desconectado", font=ctk.CTkFont(weight="bold"))
        self.lbl_connection.pack(anchor="w", padx=14, pady=(12, 4))

        self.lbl_busy = ctk.CTkLabel(self.status_card, text="Robot libre", text_color="#A0A0A0")
        self.lbl_busy.pack(anchor="w", padx=14, pady=(0, 12))

        coords_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        coords_card.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(coords_card, text="Coordenadas actuales (mm)", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.lbl_x = ctk.CTkLabel(coords_card, text="X: 0.00", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_x.pack(anchor="w", padx=14, pady=2)
        self.lbl_y = ctk.CTkLabel(coords_card, text="Y: 0.00", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_y.pack(anchor="w", padx=14, pady=2)
        self.lbl_z = ctk.CTkLabel(coords_card, text="Z: 0.00", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_z.pack(anchor="w", padx=14, pady=(2, 12))

        conn_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        conn_card.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(conn_card, text="Conexión", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.btn_connect = ctk.CTkButton(conn_card, text="Conectar", command=self.connect_robot)
        self.btn_connect.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_disconnect = ctk.CTkButton(
            conn_card,
            text="Desconectar",
            command=self.disconnect_robot,
            fg_color="#C62828",
            hover_color="#A61E1E",
        )
        self.btn_disconnect.pack(fill="x", padx=14, pady=(0, 12))

        cmd_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        cmd_card.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(cmd_card, text="Comando manual", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        ctk.CTkLabel(cmd_card, text="Ej. X,50 | HOME", text_color="#A0A0A0").pack(anchor="w", padx=14)

        self.entry_cmd = ctk.CTkEntry(cmd_card, placeholder_text="Escribe el comando")
        self.entry_cmd.pack(fill="x", padx=14, pady=(8, 8))
        self.entry_cmd.bind("<Return>", lambda event: self.send_manual_command())

        self.btn_send = ctk.CTkButton(cmd_card, text="Enviar comando", command=self.send_manual_command)
        self.btn_send.pack(fill="x", padx=14, pady=(0, 12))

        ia_card = ctk.CTkFrame(self.left_panel, corner_radius=14)
        ia_card.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(ia_card, text="Control IA", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.btn_auto = ctk.CTkButton(
            ia_card,
            text="Iniciar autoalineación",
            command=self.toggle_auto_alignment,
            fg_color="#7B1FA2",
            hover_color="#6A1B9A",
        )
        self.btn_auto.pack(fill="x", padx=14, pady=(0, 8))

        self.btn_stop = ctk.CTkButton(
            ia_card,
            text="Paro de emergencia",
            command=self.emergency_stop,
            fg_color="#B71C1C",
            hover_color="#8E1515",
        )
        self.btn_stop.pack(fill="x", padx=14, pady=(0, 12))

        vision_info = ctk.CTkFrame(self.left_panel, corner_radius=14)
        vision_info.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(vision_info, text="Estado visión", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 8)
        )
        self.lbl_vision_status = ctk.CTkLabel(vision_info, text="Esperando cámara...")
        self.lbl_vision_status.pack(anchor="w", padx=14, pady=2)
        self.lbl_confidence = ctk.CTkLabel(vision_info, text="Confianza IA: 0%")
        self.lbl_confidence.pack(anchor="w", padx=14, pady=(0, 12))

        self.video_title = ctk.CTkLabel(self.right_panel, text="Cámara en vivo", font=ctk.CTkFont(size=22, weight="bold"))
        self.video_title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self.video_label = ctk.CTkLabel(self.right_panel, text="Sin imagen todavía", anchor="center")
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        log_title = ctk.CTkLabel(self.right_panel, text="Consola", font=ctk.CTkFont(size=18, weight="bold"))
        log_title.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 6))

        self.log_box = ctk.CTkTextbox(self.right_panel, height=180, corner_radius=14)
        self.log_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

        self._set_connected_ui(False)

    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _append_log_safe(self, message: str) -> None:
        self.after(0, self._append_log, message)

    def _set_connected_ui(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        self.btn_disconnect.configure(state=state)
        self.btn_send.configure(state=state)
        self.btn_auto.configure(state=state)
        self.btn_stop.configure(state=state)

        if connected:
            self.lbl_connection.configure(text=f"Conectado a {CONFIG.robot_ip}", text_color="#81C784")
        else:
            self.lbl_connection.configure(text="Desconectado", text_color="#FF8A80")

    def _update_robot_state(self, state) -> None:
        self.lbl_x.configure(text=f"X: {state.pos_x:.2f}")
        self.lbl_y.configure(text=f"Y: {state.pos_y:.2f}")
        self.lbl_z.configure(text=f"Z: {state.pos_z:.2f}")

        if state.busy:
            self.lbl_busy.configure(text="Robot ocupado", text_color="#FFD54F")
        else:
            self.lbl_busy.configure(text="Robot libre", text_color="#A0A0A0")

        self._set_connected_ui(state.connected)

    def _on_robot_state_change(self, state) -> None:
        self.after(0, self._update_robot_state, state)

    def _on_frame_ready(self, frame, analysis) -> None:
        self.after(0, self._render_frame, frame, analysis)

    def _render_frame(self, frame, analysis) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img = img.resize((820, 615))

        self.current_image = ctk.CTkImage(light_image=img, dark_image=img, size=(820, 615))
        self.video_label.configure(image=self.current_image, text="")

        self.lbl_vision_status.configure(text=analysis.status_text)
        self.lbl_confidence.configure(text=f"Confianza IA: {analysis.confidence * 100:.0f}%")

    def connect_robot(self):
        if self.robot.connect():
            self._append_log("Conectado al robot.")
        else:
            self._append_log("No se pudo conectar con el robot.")

    def disconnect_robot(self):
        self.auto_mode = False
        self._update_auto_button()
        self.robot.disconnect()
        self._append_log("Robot desconectado.")

    def send_manual_command(self):
        cmd = self.entry_cmd.get().strip().upper()
        if not cmd:
            return

        if self.robot.send_command(cmd):
            self._append_log(f"Comando manual enviado: {cmd}")
            self.entry_cmd.delete(0, "end")

    def toggle_auto_alignment(self):
        self.auto_mode = not self.auto_mode
        self._update_auto_button()
        self._append_log("Autoalineación activada." if self.auto_mode else "Autoalineación detenida.")

    def _update_auto_button(self):
        if self.auto_mode:
            self.btn_auto.configure(
                text="Detener autoalineación",
                fg_color="#D84315",
                hover_color="#BF360C",
            )
        else:
            self.btn_auto.configure(
                text="Iniciar autoalineación",
                fg_color="#7B1FA2",
                hover_color="#6A1B9A",
            )

    def emergency_stop(self):
        self.auto_mode = False
        self._update_auto_button()
        self.robot.disconnect()
        self._append_log("Paro de emergencia activado.")

    def on_close(self):
        self.camera.stop()
        self.robot.disconnect()
        self.destroy()