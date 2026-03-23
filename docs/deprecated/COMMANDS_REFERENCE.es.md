# 📖 Asdrubot v3.0 — Referencia de Comandos

Este documento lista todos los comandos de barra (slash commands) disponibles en el sistema.

> **Leyenda:**
> - `[argumento]`: Argumento opcional.
> - `<argumento>`: Argumento requerido.
> - **(Sensible a Fase)**: El comando se adapta automáticamente dependiendo de si es Día o Noche.

---

## 👥 Comandos de Jugador

Comandos generales disponibles para todos los participantes en el juego.

### 🗳️ Votación y Estado del Juego
- **/help**
  Muestra el menú interactivo con la lista de comandos.
- **/status**
  Muestra el estado global del juego: Fase Actual, Contador de Día/Noche, Tiempo Restante y recuento de Jugadores Vivos.
  *(Dependiendo de la expansión, puede mostrar información extra como Fase Lunar).*
- **/votes**
  Muestra el recuento actual de votos, incluyendo barras de progreso hacia los umbrales de linchamiento.
- **/vote cast `<miembro>`**
  Emite tu voto contra un jugador durante la fase de Día.
- **/vote clear**
  Elimina tu voto actual.
- **/vote mine**
  Revisa por quién estás votando actualmente.
- **/vote end_day**
  Vota para terminar la fase de Día anticipadamente (requiere una mayoría de 2/3 de los jugadores vivos).

### ⚔️ Acciones y Roleplay
- **/act `[objetivo]` `[nota]`**
  **El comando principal de acción.** Registra la habilidad de tu rol para la fase actual.
  - *Fase de Día:* Requiere el flag `day_act`.
  - *Fase de Noche:* Requiere el flag `night_act`.
  - *Notas:* DEBES adjuntar una nota para el GM describiendo tu acción (ej. matar, proteger, bloquear).
- **/player list**
  Muestra una lista de todos los jugadores registrados, separados por Vivos y Muertos.
- **/player alias_show `<miembro>`**
  Muestra los alias conocidos de un jugador específico.

### 🎲 Diversión y Utilidad
- **/dice `[caras]`**
  Lanza un dado con N caras (Por defecto: 20). Útil para roles basados en RNG (azar).
- **/coin**
  Lanza una moneda (Cara/Cruz).
- **/lynch `<objetivo>`**
  Genera una imagen falsa de "Póster de Linchamiento" usando el avatar del objetivo (Puramente cosmético).

## 🛡️ Comandos de Administrador / Moderador

Estos comandos requieren permisos de **Administrador** (o permisos específicos como *Gestionar Mensajes* donde se indique).

### 👥 Gestión de Jugadores
- **/player register `<usuario>` `[nombre]`**
  Registra a un jugador en la partida y le asigna el rol de "Vivo".
- **/player unregister `<usuario>`**
  Elimina a un jugador de la partida y revoca sus permisos de canal.
- **/player rename `<usuario>` `<nuevo_nombre>`**
  Cambia el nombre visual de un jugador en el sistema.
- **/player view `<usuario>`**
  Muestra un embed completo con el estado del jugador (nombre, vivo/muerto, rol, flags, efectos activos, alias).
- **/player edit `<usuario>` `<campo>` `<valor>`**
  Edita de forma segura campos almacenados (ej. `notes`, `name`).
  *(Nota: Usa `set_flag` para atributos de votación/juego).*
- **/player set_flag `<usuario>` `<flag>` `<valor>`**
  Establece una flag de juego (ej. `hidden_vote`, `voting_boost`, `night_act`). Soporta autocompletado.
- **/player del_flag `<usuario>` `<flag>`**
  Elimina una flag de un jugador.
- **/player kill `<usuario>`**
  Marca a un jugador como **Muerto** (actualiza roles, limpia votos, cura estados).
- **/player revive `<usuario>`**
  Marca a un jugador como **Vivo** (actualiza roles, limpia estados antiguos).

### 🧪 Motor de Estados (Efectos)
*Gestiona mejoras (buffs), perjuicios (debuffs) y contadores.*
- **/effects apply `<usuario>` `<nombre>` `[duración]` `[fuente]`**
  Aplica un efecto de estado (ej. `Silenced`, `Poisoned`, `RoseCounter`).
- **/effects heal `<usuario>` `[nombre]` `[all=false]`**
  Elimina un estado específico o limpia todos los estados de un jugador.
- **/effects list `[usuario]`**
  Muestra los estados activos de un jugador, o un resumen de todos los efectos activos en la partida.
- **/effects inspect `<nombre>`**
  Ver detalles técnicos de un estado (duración, reglas de bloqueo).

### 🎮 Gestión del Juego
- **/game_start `[perfil]` `[rol_vivo]` `[rol_muerto]`**
  Inicia una nueva partida.
  - `perfil`: Reglas a cargar (ej. `default`, `smt`, `p3`).
  - `rol_vivo`/`rol_muerto`: (Opcional) Vincula roles existentes del servidor para un setup manual.
- **/game_reset**
  Reinicio forzoso del estado del juego (borra jugadores, votos e historial).
- **/finish_game `[razón]`**
  Finaliza la partida actual y archiva el estado.
- **/assign `<usuario>` `<rol>`**
  Asigna un rol específico (ej. "Makoto Yuki") a un jugador y **vincula su canal privado**.
- **/who `<usuario>`**
  Muestra la información del rol de un usuario.

### 🗳️ Fases y Votación
- **/start_day `[duración]` `[canal]` `[force]`**
  Inicia la fase de Día (abre el chat, anuncia el límite de tiempo, ejecuta ticks de estado).
- **/end_day**
  Termina la fase de Día (cierra el chat, resuelve el linchamiento).
- **/start_night `[duración]`**
  Inicia la fase de Noche (cierra el chat, ejecuta ticks de estado).
- **/end_night**
  Termina la fase de Noche.
- **/clearvotes**
  Fuerza la limpieza de todos los votos actuales.

### ⚔️ Acciones y Registros
- **/actions logs `[fase]` `[número]` `[usuario]` `[público]`**
  Ver el historial de acciones.
  - Filtra por `usuario` para ver su historial completo.
  - Filtra por `número` para ver el registro de un Día/Noche específico.
- **/actions breakdown `[fase]` `[número]`**
  Ver quién **puede actuar**, quién **actuó** y quién **falta**.

### 🌍 Infraestructura y Zonas Horarias
- **/setup**
  Ejecuta el asistente de configuración interactivo (Crea canales, roles y categorías automáticamente).
- **/wipe**
  Elimina todos los canales de juego etiquetados con `[ASDRUBOT]` (mantiene la categoría Admin).
- **/link_roles `<vivo>` `<muerto>`**
  Vincula manualmente roles existentes al bot sin ejecutar `/setup`.
- **/tz add `<canal>` `<tz>` `<etiqueta>`**
  Añade un reloj a un canal de voz (ej. `Europe/Madrid`).
- **/tz list**
  Lista todos los relojes de zona horaria activos.
- **/tz edit `<canal>` ...**
  Modifica un reloj existente.
- **/tz remove `<canal>`**
  Elimina un reloj.

### 🛡️ Moderación y Utilidad
- **/bc `<texto>`**
  Transmite un mensaje al Canal de Juego activo.
- **/set_channels `[canal_juego]` `[admin]`**
  Vincula los canales de texto principales para el bot.
- **/set_log_channel `[canal]`**
  Establece dónde se envían los registros del sistema.
- **/show_channels**
  Muestra la configuración actual de canales.
- **/purge `[cantidad]` `[usuario]` ...** *(Gestionar Mensajes)*
  Borrado masivo de mensajes con filtros.
- **/set_expansion `<perfil>`**
  Cambia el perfil de expansión a mitad de partida (usar con precaución).
- **/get_state**
  Ver una instantánea cruda del estado del juego (Fase, Día #, Expansión).

### 🧰 Mantenimiento
- **/debug_roles**
  Lista todas las claves de roles cargadas para la expansión actual.
- **/sync_here**
  Fuerza la sincronización de comandos de barra en el servidor actual.
- **/list_commands**
  Lista los comandos registrados.
- **/clean_commands**
  Elimina comandos obsoletos.