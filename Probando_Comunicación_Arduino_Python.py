import serial
import time

try:
    serialArduino = serial.Serial("COM7", 9600, timeout=0.1)
    time.sleep(2) 
    print("Conexión establecida. Iniciando lectura del Pin 5...")
except Exception as e:
    print(f"Error al abrir el puerto: {e}")
    exit()

contador_python = 1
tiempo_ultimo_envio = time.time()

try:
    while True:
        # 1. PYTHON LEE LO QUE MANDA ARDUINO
        if serialArduino.in_waiting > 0:
            mensaje_entrante = serialArduino.readline().decode('ascii').strip()
            
            if mensaje_entrante:
                # Verificamos si el mensaje es la lectura del Pin 5
                if "PIN5:" in mensaje_entrante:
                    # Dividimos el texto por los dos puntos ":" y tomamos el valor
                    valor = mensaje_entrante.split(":")[1]
                    
                    if valor == "1":
                        print("<-- Arduino informa: El Pin 5 está en ALTO (HIGH)")
                    else:
                        print("<-- Arduino informa: El Pin 5 está en BAJO (LOW)")
                else:
                    # Si es otro mensaje (como la confirmación), lo imprime normal
                    print(f"<-- Recibido: {mensaje_entrante}")

        # 2. PYTHON ENVÍA UN MENSAJE A ARDUINO (Cada 3 segundos)
        tiempo_actual = time.time()
        if (tiempo_actual - tiempo_ultimo_envio) > 3:
            mensaje_saliente = f"Mensaje Python #{contador_python}\n"
            serialArduino.write(mensaje_saliente.encode('ascii'))
            print(f"--> Enviado: {mensaje_saliente.strip()}")
            
            contador_python += 1
            tiempo_ultimo_envio = tiempo_actual

except KeyboardInterrupt:
    print("\nPrueba finalizada. Cerrando puerto serial...")
    serialArduino.close()