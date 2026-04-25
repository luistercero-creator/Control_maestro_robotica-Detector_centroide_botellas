# Pick and Place con Servovisión

Desarrollamos este sistema para automatizar la manipulación y el traslado de envases reciclables mediante un brazo robótico ABB IRB 140. Proponemos un esquema de centrado visual dinámico que busca el objeto, calcula su centroide y lo traslada de forma autónoma, superando las limitaciones de las trayectorias rígidas convencionales.

## 1. Materiales Usados

Para la ejecución de este proyecto, determinamos el uso de materiales y componentes que aseguran la estabilidad del sistema y la precisión de la captura visual.

| Componente | Descripción |
| :--- | :--- |
| **Efector Final** | Gripper de actuación neumática paralela. |
| **Material de Manufactura** | PLA de alta densidad procesado mediante manufactura aditiva. |
| **Sensor de Visión** | Cámara HD integrada en el efector (configuración Eye-in-Hand). |
| **Controlador** | ABB IRC5 con soporte para comunicación vía Sockets. |
| **Manipulador** | ABB IRB 140. |
| **Software de Orquestación** | Python 3.11 con librerías OpenCV y Keras. |

## 2. Configuración de Red e IP

La comunicación entre el orquestador y el robot se realiza a través de Sockets TCP/IP. Para garantizar el funcionamiento, se debe ajustar la dirección IP en el código de Python según el entorno:

* **Para pruebas en simulador o local**: Se debe colocar la IP `127.0.0.1` (localhost).
* **Para pruebas con el controlador real**: Se debe configurar la dirección IP asignada al controlador IRC5 (usualmente `192.168.125.1`).

## 3. Pruebas de Conexión

Determinamos que para realizar una prueba inicial de comunicación no se requiere ejecutar todo el sistema de visión. Solo es necesario cargar y ejecutar el código RAPID en el controlador. Al iniciar la rutina, el robot quedará en estado de escucha; si la interfaz logra conectarse, se confirma que el enlace físico y lógico es correcto, permitiendo probar movimientos básicos manualmente desde la interfaz antes de pasar al modo autónomo.

## 4. Resolución de Problemas: Índice de Cámara

En caso de que el programa de Python devuelva un error al intentar abrir la cámara, se debe ajustar manualmente el índice del dispositivo en la siguiente línea del código:

`cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)`

Si la cámara integrada de la computadora interfiere, se debe cambiar el valor `0` por `1` o `2` hasta detectar la cámara montada en el gripper.

## 5. Estructura del Repositorio

| Carpeta/Archivo | Contenido |
| :--- | :--- |
| **modelos/** | Archivos del modelo Keras y etiquetas de entrenamiento. |
| **rappid/** | Archivos .mod con las rutinas de movimiento y servidor Socket. |
| **Cruz_Proyecto.py** | Código principal en Python que gestiona la IA y la interfaz. |
| **requirements.txt** | Listado de librerías necesarias para el entorno de ejecución. |

## 6. Resultados de Validación

Realizamos un proceso de validación para asegurar que el sistema cumple con los requisitos técnicos de la asignatura.

| Aspecto clave | Criterio evaluado | Resultado | Observación |
| :--- | :--- | :--- | :--- |
| **Integridad de datos** | Envío de coordenadas por visión | Cumple | No se observaron pérdidas en la transmisión. |
| **Latencia** | Intercambio Python–robot | Cumple | Respuesta en tiempo oportuno durante la ejecución. |
| **Detección** | Identificación de la botella | Cumple | El modelo fue consistente en las pruebas. |
| **Precisión** | Ubicación del centroide | Cumple | El centrado fue estable y repetitivo. |
| **Alineación en Z** | Aproximación al cuello | Cumple | El ajuste vertical fue adecuado para la sujeción. |
| **Sujeción** | Acción del gripper | Cumple | La apertura y cierre respondieron correctamente. |
| **Ciclo completo** | Búsqueda y descarga | Cumple | La secuencia se completó de forma ordenada. |
| **Gestión de errores** | Respuesta ante fallos | Cumple | Se preservó el control ante eventos inesperados. |