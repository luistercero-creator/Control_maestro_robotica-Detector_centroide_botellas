import socket
import serial
import time

# --- CONFIGURACIONES ---
UPDATE_INTERVAL = 2  # Segundos para enviar Start/Stop a RAPID
ROBOT_IP = "192.168.48.218"
ROBOT_PORT = 8000
PUERTO_ARDUINO = "COM4" # Recuerda verificar si el MEGA usa este COM

# --- CONEXIÓN SOCKET (ROBOTSTUDIO) ---
mi_socket = socket.socket()
try:
    mi_socket.connect((ROBOT_IP, ROBOT_PORT))
    print(f"✔ Conectado a RobotStudio en {ROBOT_IP}:{ROBOT_PORT}")
except Exception as e:
    print("❌ Error conectando a RobotStudio:", e)
    exit(1)

# --- CONEXIÓN SERIAL (ARDUINO) ---
try:
    # timeout pequeño para leer rápido y no bloquear el bucle
    serialArduino = serial.Serial(PUERTO_ARDUINO, 9600, timeout=0.05)
    time.sleep(2) # Espera a que el MEGA se estabilice tras abrir el puerto
    print(f"✔ Conectado a Arduino en {PUERTO_ARDUINO}")
except Exception as e:
    print("❌ Error conectando a Arduino:", e)
    exit(1)

last_time = 0  

# Variables de estado inicializadas en valores seguros (forzando STOP por defecto)
distancia_actual = 999.0 
potenciometro_actual = 1023 

print("\n--- SISTEMA LISTO ---")
print("Traduciendo señales de Arduino MEGA a comandos para ABB RobotStudio...")
print("Presiona Ctrl+C en la consola para salir.\n")

try:
    while True:
        # 1. LEER DATOS DE ARDUINO (Vaciando el buffer de entrada)
        while serialArduino.in_waiting > 0:
            try:
                mensaje_entrante = serialArduino.readline().decode('ascii').strip()
                
                # Filtrar y extraer la Distancia
                if "Distancia =" in mensaje_entrante:
                    partes = mensaje_entrante.split(" ")
                    if len(partes) >= 3:
                        distancia_actual = float(partes[2])
                
                # MEDIDA DE SEGURIDAD: Si el sensor falla, forzamos una distancia irreal para asegurar el STOP
                elif "Error:" in mensaje_entrante:
                     distancia_actual = 999.0
                
                # Filtrar y extraer el Potenciómetro
                elif "Potenciometro =" in mensaje_entrante:
                    partes = mensaje_entrante.split(" ")
                    if len(partes) >= 3:
                        potenciometro_actual = int(partes[2])
                        
            except Exception as e:
                pass # Ignora basura electromagnética en la línea serial

        # 2. LÓGICA DE CONTROL
        # START solo si potenciómetro es menor a 300 Y distancia es 5 cm o menos.
        if potenciometro_actual < 300 and distancia_actual <= 5.0:
            command = "Start"
        else:
            command = "Stop"

        # 3. ENVIAR COMANDO AL ROBOT (Respetando el UPDATE_INTERVAL)
        tiempo_actual = time.time()
        if tiempo_actual - last_time > UPDATE_INTERVAL:
            try:
                mi_socket.send(command.encode("utf-8"))
                
                # Imprimir en consola el estado actual de los sensores y el comando
                print(f"[{time.strftime('%H:%M:%S')}] Dist: {distancia_actual}cm | Pot: {potenciometro_actual} -> Enviando: {command}")
                
            except Exception as e:
                print("❌ Error de red: Se perdió la conexión con RobotStudio.", e)
                break 
            
            last_time = tiempo_actual

        # Pequeña pausa de 10 milisegundos
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nDeteniendo sistema de forma segura...")

finally:
    # --- LIMPIEZA ---
    mi_socket.close()
    serialArduino.close()
    print("Conexiones cerradas correctamente.")