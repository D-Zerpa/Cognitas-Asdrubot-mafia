# :video_game: Guía de Usuario: Cognitas 

## :busts_in_silhouette: Comandos de Jugador

### :ballot_box: Votación y Estado del Juego
- **/status**
  Muestra el estado global de la partida: Fase actual (Día/Noche), contador del ciclo, tiempo restante para el cierre de fase y anuncios climáticos o de la expedición.

- **/vote**
  Despliega tu **Panel de Votación** interactivo (disponible durante el Día). Todo se maneja mediante botones desde un mismo mensaje:
  - **Votar/Cambiar voto:** Selecciona a un jugador del menú para condenarlo al linchamiento, o elige la opción "No Linchar".
  - **Retirar Voto:** Elimina tu selección actual para quedar neutral.
  - **Ver Resumen:** Genera un reporte en vivo de las barras de progreso, umbrales de linchamiento y quién está votando a quién.
  - **Terminar Día:** Suma tu voto para acelerar el reloj y cerrar la fase de Día de forma anticipada.

### :crossed_swords: Acciones y Habilidades
- **/act**
  Despliega tu **Panel de Acciones** privado. Es el comando principal para usar tu rol:
  - **Botones de Habilidad:** Mostrará únicamente los poderes que tienes habilitados para la fase actual.
  - **Selección de Objetivo:** Al presionar una habilidad, el bot te preguntará sobre quién deseas usarla.
  - **Notas Adicionales:** Si usas una habilidad compleja (que requiera de detalles), se abrirá una ventana emergente en tu pantalla para que escribas los detalles exactos de tu jugada.
  - **Feedback Inmediato:** Tras confirmar tu jugada, el bot te notificará al instante si algún estado alterado (ej. *Confusión, Quemadura*) intercedió en tu acción.

### :game_die: Diversión y Utilidad
- **/player list**
  Muestra una lista de todos los jugadores registrados en la partida, separados por Vivos y Muertos.

- **/dice `[caras]`**
  Lanza un dado con N caras (Por defecto: 20). Útil para mecánicas basadas en azar.

- **/coin**
  Lanza una moneda (Cara/Sello).