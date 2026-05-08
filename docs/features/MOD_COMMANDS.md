# 🛡️ Guía del Game Master: Cognitas – Expedición 33

Esta es la lista completa de comandos exclusivos para Administradores/GM. Estos comandos controlan el motor del juego, el flujo del tiempo y las mecánicas manuales. 

---

## 🌍 Setup y Terraformación
*Se usan principalmente antes de iniciar la partida.*

* **`/terraform <expansión>`**: Comando maestro. Crea automáticamente la categoría, canales públicos, canales privados para cada rol, genera los roles de Discord "Vivo" y "Muerto", y carga la expansión en memoria.
* **`/wipe`**: Botón de pánico/Reinicio. Destruye todos los canales y roles creados por el Terraform y limpia la memoria del bot.
* **`/set_expansion <perfil>`**: Carga los roles (JSON) y mecánicas (Python) de una expansión sin tener que crear los canales (útil si ya hiciste Terraform antes).
* **`/assign <miembro> <rol>`**: Asigna un rol del JSON a un jugador de Discord, lo registra en el motor, le da el rol "Vivo" y le otorga acceso exclusivo a su cuarto privado.
* **`/debug_roles`**: Lista las claves internas de todos los roles cargados en memoria (útil para saber qué escribir en `/assign`).
* **`/show_channels`**: Muestra la configuración actual de canales y roles de Discord vinculados al motor.

---

## ⏳ Flujo de Partida (Ciclos y Reportes)
*Para gestionar el avance natural del juego.*

* **`/next_phase [minutos]`**: Avanza el juego (de Día a Noche, o viceversa). Cierra los canales correspondientes, procesa duraciones de estados alterados, y opcionalmente inicia un reloj para la nueva fase.
* **`/lock_channel`**: Detiene el tiempo y cierra el canal público de inmediato (como el antiguo `end_day`). Ideal para frenar el juego e iniciar resoluciones.
* **`/action_report`**: Imprime la "Hoja de Ruta" del GM. Muestra quién falta por actuar, y lista todas las acciones enviadas **ordenadas por prioridad**, indicando si pasaron el RNG, el objetivo, y las **notas de los Modales**.
* **`/timer adjust <minutos>`**: Añade o resta minutos al cronómetro actual en vivo. (Usa números negativos para restar).
* **`/timer cancel`**: Detiene el cronómetro actual dejándolo en tiempo infinito, sin cerrar el canal.
* **`/set_phase <fase> <ciclo>`**: Sobrescribe la fase actual (Día/Noche) y el número de ciclo de forma forzada. Actualiza el nombre del canal público.

---

## 🔥 Gestión de Estados Alterados y Flags
*Para alterar atributos mecánicos de los jugadores.*

* **`/effects apply <jugador> <estado> [duración]`**: Aplica una condición negativa o positiva a un jugador (ej. `burned`, `confusion`, `silenced`). Cuenta con autocompletado.
* **`/effects heal <jugador> [estado]`**: Cura un estado específico. Si no se especifica el estado, limpia absolutamente todos los estados del jugador.
* **`/effects list <jugador>`**: Muestra un resumen de todos los estados activos del jugador y sus fases restantes/cargas acumuladas.
* **`/effects inspect <estado>`**: Muestra los detalles técnicos de cómo funciona un estado por dentro (si bloquea acciones, votos, acumulación, etc).
* **`/set_flag <jugador> <flag> <tipo> <valor>`**: Permite editar o inyectar variables pasivas al jugador. Cuenta con autocompletado para flags clave (ej. `is_awakened`, `is_act3`, `vote_weight`, `lynch_weight`, `hidden_vote`).

---

## ⚡ Intervención Divina y Sistema
*Herramientas para corregir errores o forzar eventos.*

* **`/force_kill <jugador> [razón]`**: Ejecuta al jugador instantáneamente, enviándolo al cementerio y quitándole permisos de Vivo. Ignora cualquier protección.
* **`/force_revive <jugador>`**: Resucita a un jugador muerto, dándole el rol de Vivo nuevamente.
* **`/save_game`**: Guarda la partida completa (jugadores, votos, canales, acciones) en el disco duro. El bot hace esto automáticamente cada 5 minutos de todos modos.
* **`/load_game`**: Carga el último guardado y sobrescribe la partida actual. (Útil en caso de crash del bot).
* **`/broadcast <mensaje> [título] [canal]`**: Envía un mensaje con formato de Embed (Anuncio) haciéndose pasar por el bot en el canal principal o en uno específico.
* **`/purge <cantidad>`**: Elimina en masa de 1 a 100 mensajes en el canal donde se ejecuta.

---
*💡 Tip: Usa la tecla `TAB` mientras escribes comandos como `/effects apply` o `/set_flag` para aprovechar el autocompletado inteligente de las expansiones.*