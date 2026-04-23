import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

from config import APP_CONFIG
from registrador import ConsoleLogger
from robot_controlador import RobotController
from vision_controlador import VisionController


class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Consola ABB + Visión IA")
        self.root.geometry("550x850")
        self.root.configure(bg="#2d2d2d")

        self.logger = ConsoleLogger()

        self.robot = RobotController(
            APP_CONFIG,
            logger=self.logger,
            on_state_change=self._on_robot_state_change,
        )
        self.vision = VisionController(
            APP_CONFIG,
            robot_controller=self.robot,
            logger=self.logger,
        )

        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

        self._build_ui()
        self._append_log("Sistema iniciado. Cargando visión artificial...")
        self.vision.start()

    def _build_ui(self):
        frame_coords = tk.Frame(self.root, bg="#2d2d2d")
        frame_coords.pack(pady=10, fill=tk.X, padx=20)

        tk.Label(
            frame_coords,
            text="COORDENADAS ACTUALES (mm)",
            bg="#2d2d2d",
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(pady=5)

        inner_coords = tk.Frame(frame_coords, bg="#2d2d2d")
        inner_coords.pack()

        self.lbl_x = tk.Label(inner_coords, text="X: 0.00", bg="black", fg="#00FF00",
                              font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_x.pack(side=tk.LEFT, padx=5)

        self.lbl_y = tk.Label(inner_coords, text="Y: 0.00", bg="black", fg="#00FF00",
                              font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_y.pack(side=tk.LEFT, padx=5)

        self.lbl_z = tk.Label(inner_coords, text="Z: 0.00", bg="black", fg="#00FF00",
                              font=("Consolas", 14, "bold"), width=10, bd=2, relief=tk.SUNKEN)
        self.lbl_z.pack(side=tk.LEFT, padx=5)

        frame_conn = tk.Frame(self.root, bg="#2d2d2d")
        frame_conn.pack(pady=5, fill=tk.X, padx=20)

        self.btn_conectar = tk.Button(
            frame_conn, text="Conectar", bg="#4CAF50", fg="white",
            font=("Arial", 10, "bold"), command=self.conectar
        )
        self.btn_conectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        self.btn_desconectar = tk.Button(
            frame_conn, text="Desconectar", bg="#f44336", fg="white",
            font=("Arial", 10, "bold"), command=self.desconectar, state=tk.DISABLED
        )
        self.btn_desconectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        frame_cmd = tk.Frame(self.root, bg="#2d2d2d")
        frame_cmd.pack(pady=5, fill=tk.X, padx=20)

        tk.Label(
            frame_cmd,
            text="Comando Manual (ej. X,50 | HOME):",
            bg="#2d2d2d",
            fg="white",
            font=("Arial", 10),
        ).pack(anchor=tk.W)

        self.entry_cmd = tk.Entry(frame_cmd, font=("Arial", 14))
        self.entry_cmd.pack(fill=tk.X, pady=5)
        self.entry_cmd.bind("<Return>", lambda event: self.enviar_comando())

        self.btn_enviar = tk.Button(
            frame_cmd, text="Enviar Comando", bg="#2196F3", fg="white",
            font=("Arial", 10, "bold"), command=self.enviar_comando, state=tk.DISABLED
        )
        self.btn_enviar.pack(fill=tk.X, pady=5)

        frame_ia = tk.Frame(self.root, bg="#2d2d2d", bd=2, relief=tk.RIDGE)
        frame_ia.pack(pady=10, fill=tk.X, padx=20)

        tk.Label(
            frame_ia,
            text="CONTROL IA",
            bg="#2d2d2d",
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(pady=5)

        self.btn_auto = tk.Button(
            frame_ia,
            text="INICIAR AUTO-ALINEACIÓN",
            bg="#9C27B0",
            fg="white",
            font=("Arial", 12, "bold"),
            command=self.toggle_auto_alineacion,
            state=tk.DISABLED,
        )
        self.btn_auto.pack(fill=tk.X, padx=10, pady=5)

        self.btn_stop = tk.Button(
            self.root,
            text="PARO DE EMERGENCIA",
            bg="#B71C1C",
            fg="white",
            font=("Arial", 16, "bold"),
            command=self.enviar_stop,
            state=tk.DISABLED,
        )
        self.btn_stop.pack(fill=tk.X, padx=20, pady=10, ipady=15)

        self.txt_log = scrolledtext.ScrolledText(
            self.root, height=8, bg="black", fg="#00FF00", font=("Consolas", 10)
        )
        self.txt_log.pack(padx=20, pady=5, fill=tk.BOTH, expand=True)

    def _append_log(self, message: str) -> None:
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)

    def log(self, message: str) -> None:
        self.root.after(0, self._append_log, message)

    def _update_displays(self) -> None:
        self.lbl_x.config(text=f"X: {self.pos_x:.2f}")
        self.lbl_y.config(text=f"Y: {self.pos_y:.2f}")
        self.lbl_z.config(text=f"Z: {self.pos_z:.2f}")

    def _apply_button_state(self, connected: bool) -> None:
        self.btn_conectar.config(state=tk.DISABLED if connected else tk.NORMAL)
        self.btn_desconectar.config(state=tk.NORMAL if connected else tk.DISABLED)
        self.btn_enviar.config(state=tk.NORMAL if connected else tk.DISABLED)
        self.btn_auto.config(state=tk.NORMAL if connected else tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL if connected else tk.DISABLED)

    def _on_robot_state_change(self, state):
        self.root.after(0, self._apply_robot_state, state)

    def _apply_robot_state(self, state):
        self.pos_x = state["pos_x"]
        self.pos_y = state["pos_y"]
        self.pos_z = state["pos_z"]
        self._update_displays()
        self._apply_button_state(state["connected"])

    def conectar(self):
        ok = self.robot.connect()
        if not ok:
            messagebox.showerror("Error", "No se pudo conectar con el robot.")

    def desconectar(self):
        self.vision.stop_auto_alignment()
        self.robot.disconnect()

    def enviar_comando(self):
        cmd = self.entry_cmd.get().strip().upper()
        if not cmd:
            return

        if self.robot.send_command(cmd):
            self.entry_cmd.delete(0, tk.END)

    def enviar_stop(self):
        self.log("Paro de emergencia activado.")
        self.vision.stop_auto_alignment()
        self.robot.disconnect()
        self.root.after(1500, self.conectar)

    def toggle_auto_alineacion(self):
        activo = self.vision.toggle_auto_alignment()

        if activo:
            self.btn_auto.config(text="DETENER AUTO-ALINEACIÓN", bg="#FF5722")
            self.log("Auto-alineación activada.")
        else:
            self.btn_auto.config(text="INICIAR AUTO-ALINEACIÓN", bg="#9C27B0")
            self.log("Auto-alineación detenida.")