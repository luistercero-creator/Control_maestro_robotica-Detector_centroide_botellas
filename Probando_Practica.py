import socket
import time
import threading
import time
import select
import sys

mi_socket = socket.socket()

mi_socket.connect(("172.18.17.100", 8000))
respuesta = mi_socket.recv(1024)

print(respuesta)

while True:
    valor = input()
    mi_socket.send(bytes(valor, "utf-8"))
    #print("Coordenadas: ")
    #datos = input()
    #mi_socket.send(str(datos))

    time.sleep(10)