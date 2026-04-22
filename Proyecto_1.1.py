import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

# === CONFIGURACION ===
ROBOT_IP = "192.168.1.21"
ROBOT_PORT = 8000

class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Consola de Control ABB - FaceNet")
        self.root.geometry("500x750") 
        self.root.configure(bg="#2d2d2d")
        
        self.sock = None
        self.conectado = False
        
        # Coordenadas acumuladas
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0
        
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
        frame_conn.pack(pady=10, fill=tk.X, padx=20)
        self.btn_conectar = tk.Button(frame_conn, text="Conectar", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=self.conectar)
        self.btn_conectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.btn_desconectar = tk.Button(frame_conn, text="Desconectar", bg="#f44336", fg="white", font=("Arial", 10, "bold"), command=self.desconectar, state=tk.DISABLED)
        self.btn_desconectar.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # --- 3. PANEL DE COMANDOS ---
        frame_cmd = tk.Frame(root, bg="#2d2d2d")
        frame_cmd.pack(pady=10, fill=tk.X, padx=20)
        tk.Label(frame_cmd, text="Comando (ej. X,50 | R,90 | HOME):", bg="#2d2d2d", fg="white", font=("Arial", 10)).pack(anchor=tk.W)
        self.entry_cmd = tk.Entry(frame_cmd, font=("Arial", 14))
        self.entry_cmd.pack(fill=tk.X, pady=5)
        self.entry_cmd.bind("<Return>", lambda event: self.enviar_comando())
        self.btn_enviar = tk.Button(frame_cmd, text="Enviar Comando", bg="#2196F3", fg="white", font=("Arial", 12, "bold"), command=self.enviar_comando, state=tk.DISABLED)
        self.btn_enviar.pack(fill=tk.X, pady=5)

        # --- 4. ACCIONES RÁPIDAS ---
        self.btn_home = tk.Button(root, text="Ir a HOME", bg="#FF9800", fg="white", font=("Arial", 12, "bold"), command=lambda: self.enviar_texto("HOME"), state=tk.DISABLED)
        self.btn_home.pack(fill=tk.X, padx=20, pady=5)
        self.btn_stop = tk.Button(root, text="⚠ PARO DE EMERGENCIA ⚠", bg="#B71C1C", fg="white", font=("Arial", 16, "bold"), command=self.enviar_stop, state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X, padx=20, pady=15, ipady=15)

        # --- 5. CONSOLA ---
        self.txt_log = scrolledtext.ScrolledText(root, height=10, bg="black", fg="#00FF00", font=("Consolas", 10))
        self.txt_log.pack(padx=20, pady=5, fill=tk.BOTH, expand=True)
        self.log("Sistema iniciado.")

    def log(self, mensaje):
        self.txt_log.insert(tk.END, mensaje + "\n")
        self.txt_log.see(tk.END)

    def actualizar_displays(self):
        self.lbl_x.config(text=f"X: {self.pos_x:.2f}")
        self.lbl_y.config(text=f"Y: {self.pos_y:.2f}")
        self.lbl_z.config(text=f"Z: {self.pos_z:.2f}")

    def procesar_respuesta(self, respuesta):
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
            self.btn_conectar.config(state=tk.DISABLED); self.btn_desconectar.config(state=tk.NORMAL)
            self.btn_enviar.config(state=tk.NORMAL); self.btn_home.config(state=tk.NORMAL); self.btn_stop.config(state=tk.NORMAL)
            self.log(f"✔ Conectado a {ROBOT_IP}")
            threading.Thread(target=self.escuchar_robot, daemon=True).start()
        except Exception as e: messagebox.showerror("Error", f"Fallo: {e}")

    def desconectar(self):
        self.conectado = False
        if self.sock: 
            try: self.sock.close() 
            except: pass
        self.btn_conectar.config(state=tk.NORMAL); self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED); self.btn_home.config(state=tk.DISABLED); self.btn_stop.config(state=tk.DISABLED)
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
            self.enviar_texto(cmd)
            self.entry_cmd.delete(0, tk.END)

    def enviar_stop(self):
        # El Paro de Emergencia por "Cable Trampa"
        self.log("⚠ PARO SOLICITADO: Cortando conexion para frenar motores...")
        self.conectado = False
        if self.sock:
            try: self.sock.close()
            except: pass
            
        self.btn_conectar.config(state=tk.NORMAL); self.btn_desconectar.config(state=tk.DISABLED)
        self.btn_enviar.config(state=tk.DISABLED); self.btn_home.config(state=tk.DISABLED); self.btn_stop.config(state=tk.DISABLED)
        
        self.log("Reconectando en 1.5 segundos para retomar control...")
        self.root.after(1500, self.conectar)

if __name__ == "__main__":
    root = tk.Tk()
    app = RobotGUI(root)
    root.mainloop()