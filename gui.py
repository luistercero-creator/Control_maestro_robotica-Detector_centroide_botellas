import time

import customtkinter as ctk
import cv2
from PIL import Image, ImageOps
from tkinter import messagebox

from config import CONFIG
from control_logica import ControlLogic
from registrador import AppLogger
from robot_controlador import RobotController
from vision_procesamiento import VisionProcessor
from vision_servicio import CameraService


class RobotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Consola ABB + Visión IA - ULSA 2026")
        self.geometry("1250x850")
        self.minsize(1150, 780)

        try:
            self.after(100, lambda: self.state("zoomed"))
        except Exception:
            pass

        self.current_image = None
        self._fps = 0.0
        self._last_frame_ts = None

        self.logger = AppLogger(self._append_log_safe)
        self.control = ControlLogic(CONFIG)
        self.robot = RobotController(
            CONFIG,
            self.logger,
            on_state_change=self._on_robot_state_change,
        )
        self.vision = VisionProcessor(CONFIG, self.logger)
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
        self._update_control_buttons()

        if not self.camera.start():
            self._append_log("No se pudo iniciar la cámara. Revisa camera_index en config.py.")

        self.after(100, self._layout_video_area)

    def _build_ui(self):
        BG_COLOR = "#1e1e1e"
        CARD_COLOR = "#2b2b2b"
        ACCENT_BLUE = "#3498db"
        ACCENT_PURPLE = "#9b59b6"
        TEXT_DIM = "#a0a0a0"

        self.grid_columnconfigure(0, weight=0, minsize=360)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(
            self,
            corner_radius=20,
            width=360,
            fg_color=BG_COLOR,
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(15, 20))
        ctk.CTkLabel(header, text="Consola ABB", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text="Control, visión y seguimiento", text_color=TEXT_DIM).pack(anchor="w")

        conn_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        conn_card.pack(fill="x", padx=10, pady=8)
        self.lbl_connection = ctk.CTkLabel(
            conn_card,
            text="● Desconectado",
            text_color="#ef9a9a",
            font=ctk.CTkFont(weight="bold"),
        )
        self.lbl_connection.pack(pady=(15, 2), padx=15, anchor="w")
        self.lbl_busy = ctk.CTkLabel(conn_card, text="Robot libre", text_color=TEXT_DIM)
        self.lbl_busy.pack(pady=(0, 15), padx=15, anchor="w")

        coords_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        coords_card.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(coords_card, text="Coordenadas actuales (mm)", font=ctk.CTkFont(weight="bold")).pack(
            pady=(15, 8),
            padx=15,
            anchor="w",
        )
        self.lbl_x = ctk.CTkLabel(coords_card, text="X: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_x.pack(padx=20, anchor="w")
        self.lbl_y = ctk.CTkLabel(coords_card, text="Y: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_y.pack(padx=20, anchor="w")
        self.lbl_z = ctk.CTkLabel(coords_card, text="Z: 0.00", font=ctk.CTkFont(family="Consolas", size=18))
        self.lbl_z.pack(padx=20, pady=(0, 15), anchor="w")

        btn_conn_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        btn_conn_card.pack(fill="x", padx=10, pady=8)
        self.btn_connect = ctk.CTkButton(
            btn_conn_card,
            text="Conectar",
            fg_color=ACCENT_BLUE,
            height=35,
            command=self.connect_robot,
        )
        self.btn_connect.pack(fill="x", padx=15, pady=(15, 8))
        self.btn_disconnect = ctk.CTkButton(
            btn_conn_card,
            text="Desconectar",
            fg_color="#e74c3c",
            height=35,
            command=self.disconnect_robot,
        )
        self.btn_disconnect.pack(fill="x", padx=15, pady=(0, 15))

        manual_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        manual_card.pack(fill="x", padx=10, pady=8)
        self.entry_cmd = ctk.CTkEntry(manual_card, placeholder_text="Escribe el comando", fg_color="#333333")
        self.entry_cmd.pack(fill="x", padx=15, pady=(15, 8))
        self.entry_cmd.bind("<Return>", lambda event: self.send_manual_command())
        self.btn_send = ctk.CTkButton(
            manual_card,
            text="Enviar comando",
            fg_color=ACCENT_BLUE,
            command=self.send_manual_command,
        )
        self.btn_send.pack(fill="x", padx=15, pady=(0, 15))

        tracking_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        tracking_card.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(tracking_card, text="Seguimiento visual", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w",
            padx=15,
            pady=(15, 8),
        )
        self.btn_auto = ctk.CTkButton(
            tracking_card,
            text="Iniciar autoalineación",
            fg_color=ACCENT_PURPLE,
            height=45,
            font=ctk.CTkFont(weight="bold"),
            command=self.toggle_auto_alignment,
        )
        self.btn_auto.pack(fill="x", padx=15, pady=(0, 10))

        self.switch_centroid = ctk.CTkSwitch(
            tracking_card,
            text="Búsqueda de centroide manual",
            command=self.toggle_centroid_switch,
        )
        self.switch_centroid.pack(anchor="w", padx=15, pady=(0, 12))

        self.btn_stop = ctk.CTkButton(
            tracking_card,
            text="PARO DE EMERGENCIA",
            fg_color="#B71C1C",
            height=45,
            command=self.emergency_stop,
        )
        self.btn_stop.pack(fill="x", padx=15, pady=(0, 15))

        quick_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        quick_card.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(
            quick_card,
            text="Acciones rápidas",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.btn_home = ctk.CTkButton(
            quick_card,
            text="HOME",
            fg_color="#FF9800",
            command=lambda: self.send_quick_command("HOME"),
        )
        self.btn_home.pack(fill="x", padx=15, pady=(0, 8))

        self.btn_inicio = ctk.CTkButton(
            quick_card,
            text="INICIO",
            fg_color="#00BCD4",
            text_color="black",
            command=lambda: self.send_quick_command("INICIO"),
        )
        self.btn_inicio.pack(fill="x", padx=15, pady=(0, 8))

        self.btn_pos_botella = ctk.CTkButton(
            quick_card,
            text="POS_BOTELLA",
            fg_color="#E91E63",
            command=lambda: self.send_quick_command("POS_BOTELLA"),
        )
        self.btn_pos_botella.pack(fill="x", padx=15, pady=(0, 15))

        vis_card = ctk.CTkFrame(self.left_panel, corner_radius=15, fg_color=CARD_COLOR)
        vis_card.pack(fill="x", padx=10, pady=8)
        self.lbl_vision_status = ctk.CTkLabel(vis_card, text="Esperando cámara...")
        self.lbl_vision_status.pack(pady=(10, 2), padx=15, anchor="w")
        self.lbl_confidence = ctk.CTkLabel(vis_card, text="Confianza IA: 0%")
        self.lbl_confidence.pack(pady=(0, 10), padx=15, anchor="w")

        self.right_panel = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_COLOR)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 15), pady=15)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=0)
        self.right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.right_panel,
            text="Cámara en vivo",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(15, 5))

        self.video_stage = ctk.CTkFrame(self.right_panel, corner_radius=15, fg_color="#000000")
        self.video_stage.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)

        self.video_label = ctk.CTkLabel(
            self.video_stage,
            text="Cargando stream...",
            fg_color="#000000",
            corner_radius=15,
        )
        self.video_label.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self.right_panel,
            text="Consola",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(5, 0))

        self.log_box = ctk.CTkTextbox(
            self.right_panel,
            height=120,
            corner_radius=15,
            fg_color=CARD_COLOR,
            border_width=1,
            border_color="#3d3d3d",
        )
        self.log_box.grid(row=3, column=0, sticky="ew", padx=20, pady=(5, 15))
        self.log_box.configure(state="disabled")

    def _layout_video_area(self, event=None):
        self._render_empty_hud()

    def _render_frame(self, frame, analysis) -> None:
        try:
            vw = max(self.video_stage.winfo_width(), 200)
            vh = max(self.video_stage.winfo_height(), 150)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_raw = Image.fromarray(rgb)

            fitted = ImageOps.contain(
                img_raw,
                (vw - 16, vh - 16),
                method=Image.Resampling.LANCZOS,
            )

            self.current_image = ctk.CTkImage(
                light_image=fitted,
                dark_image=fitted,
                size=fitted.size,
            )
            self.video_label.configure(image=self.current_image, text="")
            self.video_label.place(relx=0.5, rely=0.5, anchor="center")

            self.lbl_vision_status.configure(text=analysis.status_text)
            self.lbl_confidence.configure(text=f"Confianza IA: {analysis.confidence * 100:.0f}%")

            self._update_overlay_texts(
                analysis,
                frame.shape[1],
                frame.shape[0],
            )

        except Exception as e:
            self.logger.error(f"Error renderizando video: {e}")

    def _render_empty_hud(self):
        mode = "ON" if self.control.auto_mode else ("MANUAL" if self.control.manual_centroid_mode else "OFF")
        self._update_overlay_texts(None, None, None, mode_override=mode)

    def _update_overlay_texts(self, analysis, frame_w, frame_h, mode_override=None):
        if analysis is None:
            status_text = "Esperando cámara..."
            confidence = 0.0
            error_x = 0.0
            error_y = 0.0
            aligned = False
        else:
            status_text = analysis.status_text
            confidence = analysis.confidence
            error_x = analysis.error_robot_x
            error_y = analysis.error_robot_y
            aligned = analysis.aligned

        mode_text = mode_override if mode_override is not None else (
            "ON" if self.control.auto_mode else ("MANUAL" if self.control.manual_centroid_mode else "OFF")
        )

        self._update_hud_widgets(confidence, status_text, error_x, error_y, mode_text, frame_w, frame_h)

    def _update_hud_widgets(self, confidence, status_text, error_x, error_y, mode_text, frame_w, frame_h):
        if hasattr(self, "lbl_hud_title"):
            self.lbl_hud_title.configure(text=f"Confianza IA: {confidence * 100:.0f}%")

        if hasattr(self, "lbl_hud_status"):
            if status_text == "ALINEADO PERFECTAMENTE":
                color = "#4CAF50"
            elif "CENTROIDE DESACTIVADO" in status_text:
                color = "#9E9E9E"
            elif "CALCULANDO" in status_text:
                color = "#FFB300"
            elif "BUSCANDO" in status_text:
                color = "#FF6E40"
            else:
                color = "#FFB300"
            self.lbl_hud_status.configure(text=f"Estado: {status_text}", text_color=color)

        if hasattr(self, "lbl_hud_errors"):
            self.lbl_hud_errors.configure(
                text=(
                    "Errores (px)\n"
                    f"Robot X: {error_x:.0f}\n"
                    f"Robot Y: {error_y:.0f}"
                )
            )

        if hasattr(self, "lbl_hud_footer"):
            if frame_w and frame_h:
                res_text = f"{frame_w}x{frame_h}"
            else:
                res_text = "--"
            self.lbl_hud_footer.configure(
                text=(
                    f"Cámara: {CONFIG.camera_index}   |   "
                    f"Resolución: {res_text}   |   "
                    f"FPS: {self._fps:.1f}   |   "
                    f"Centroide: {mode_text}"
                )
            )

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
            text_color="#81C784" if state.connected else "#ef9a9a",
        )
        self.lbl_busy.configure(text="Robot ocupado" if state.busy else "Robot libre")
        self._set_button_states(state.connected)

    def _on_frame_ready(self, frame, analysis) -> None:
        now = time.perf_counter()
        if self._last_frame_ts is not None:
            dt = now - self._last_frame_ts
            if dt > 0:
                self._fps = 1.0 / dt
        self._last_frame_ts = now
        self.after(0, self._render_frame, frame, analysis)

    def _set_button_states(self, connected: bool):
        state = "normal" if connected else "disabled"
        self.btn_disconnect.configure(state=state)
        self.btn_send.configure(state=state)
        self.btn_auto.configure(state=state)
        self.btn_stop.configure(state=state)
        self.switch_centroid.configure(state=state)
        self.btn_home.configure(state=state)
        self.btn_inicio.configure(state=state)
        self.btn_pos_botella.configure(state=state)

    def connect_robot(self):
        if self.robot.connect():
            self._append_log("Conectado al robot.")
        else:
            messagebox.showerror("Error", "No se pudo conectar con el robot.")
            self._append_log("No se pudo conectar con el robot.")

    def disconnect_robot(self):
        self.control.reset()
        self.switch_centroid.deselect()
        self._update_control_buttons()
        self.robot.disconnect()
        self._append_log("Robot desconectado.")

    def send_manual_command(self):
        cmd = self.entry_cmd.get().strip().upper()
        if not cmd:
            return

        if self.robot.send_command(cmd):
            self._append_log(f"Comando manual enviado: {cmd}")
            self.entry_cmd.delete(0, "end")

    def send_quick_command(self, command: str):
        if self.robot.send_command(command):
            self._append_log(f"Comando rápido enviado: {command}")

    def toggle_auto_alignment(self):
        self.control.toggle_auto_mode()
        if self.control.auto_mode:
            self.switch_centroid.select()
        self._update_control_buttons()
        self._append_log("Autoalineación activada." if self.control.auto_mode else "Autoalineación detenida.")

    def toggle_centroid_switch(self):
        self.control.set_centroid_mode(bool(self.switch_centroid.get()))
        self._update_control_buttons()
        if self.control.manual_centroid_mode:
            self._append_log("Búsqueda de centroide activada manualmente.")
        else:
            self._append_log("Búsqueda de centroide desactivada.")

    def _update_control_buttons(self):
        if self.control.auto_mode:
            self.btn_auto.configure(
                text="Detener autoalineación",
                fg_color="#D84315",
                hover_color="#BF360C",
            )
        else:
            self.btn_auto.configure(
                text="Iniciar autoalineación",
                fg_color="#9b59b6",
                hover_color="#8e44ad",
            )

        if self.control.manual_centroid_mode:
            self.switch_centroid.select()
        else:
            self.switch_centroid.deselect()

    def emergency_stop(self):
        self.control.reset()
        self.switch_centroid.deselect()
        self._update_control_buttons()
        self.robot.disconnect()
        self._append_log("⚠ PARO DE EMERGENCIA")

    def on_close(self):
        self.camera.stop()
        self.robot.disconnect()
        self.destroy()