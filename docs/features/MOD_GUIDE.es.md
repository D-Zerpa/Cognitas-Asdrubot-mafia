# 🛡️ Guía del Moderador — Asdrubot v3.0

Esta guía explica paso a paso cómo administrar una partida de Mafia/Werewolf utilizando **Cognitas (Asdrubot)**.

---

## 1. Preparativos (Setup)

Antes de que los jugadores entren, debes configurar el servidor. Tienes dos opciones:

### Opción A: Setup Automático (Recomendado para servidores nuevos)
Si el servidor está vacío o quieres que el bot cree los canales por ti.

1.  Ejecuta: `/setup`
2.  Selecciona el perfil de juego (ej. **smt**, **p3**, **base**).
3.  Pulsa el botón **Create Structure**.
    * *El bot creará categorías, canales de roles privados, roles de Alive/Dead y configurará los permisos.*

### Opción B: Setup Manual (Si ya tienes canales y roles)
Si ya creaste los roles y canales a mano.

1.  Asegúrate de tener dos roles creados: uno para Vivos y otro para Muertos.
2.  Ejecuta: `/game_start profile:<perfil> alive_role:@Vivo dead_role:@Muerto`.
3.  Vincula los canales principales: `/set_channels game_channel:#juego admin:#gm`.
    * *Nota:* Los canales privados de rol no se vincularán automáticamente; tendrás que dar permisos manualmente si usas este método, o usar `/link_roles` si necesitas vincular roles sin iniciar la partida.

### Configuración de Hora (Timezones)
Fundamental para coordinar jugadores internacionales. El bot renombrará canales de voz para mostrar la hora real.

1.  Elige un canal de voz para usar de reloj.
2.  Ejecuta: `/tz add channel:[#CanalVoz] tz:[ZonaIANA] label:[Nombre]`
    * *Ejemplo España:* `/tz add channel:#Voz1 tz:Europe/Madrid label:España`
    * *Ejemplo Latam:* `/tz add channel:#Voz2 tz:America/Mexico_City label:México`

---

## 2. Registro de Jugadores

Una vez configurado, es hora de meter a la gente al sistema.

1.  **Registrar:** Por cada jugador, usa:
    `/player register user:@Jugador name:"NombreRP"`
    * *Esto le asigna el rol de "Vivo" automáticamente.*

2.  **Asignar Rol:** Dale su personaje secreto.
    `/assign user:@Jugador role:"Nombre Del Rol"`
    * *Ejemplo:* `/assign user:@Pepito role:"Makoto Yuki"`
    * *El bot le dará acceso inmediato a su canal privado `#role-makoto`.*

3.  **Verificar:** Usa `/player list` para ver si todos están "Alive" y registrados.

---

## 3. Inicio del Juego

Cuando todos tengan rol y estén listos:

1.  **Arrancar Día 1:**
    `/start_day duration:24h`
    * *El bot abre el canal de juego, anuncia el día y activa los temporizadores.*

---

## 4. Fase de Día (Debate y Votación)

Durante el día, los jugadores hablarán y votarán en el canal público.

* **Monitorear Votos:** Usa `/votes` para ver la tabla actual.
* **Forzar Final:** Si la discusión se estanca o hay consenso absoluto, puedes usar `/end_day`.
* **Linchamiento:**
    * Si al terminar el tiempo (o al usar `/end_day`) alguien supera el umbral de votos, será **Linchado automáticamente**.
    * El bot lo marcará como **Muerto**, cambiará su rol de Discord y limpiará sus estados.
    * Por cosas de roleplay, se puede dar una breve narrativa para describir la muerte, se revela la ficha del linchado y se procede a la fase de noche.

---

## 5. Fase de Noche (Acciones)

1.  **Iniciar Noche:**
    `/start_night duration:12h`
    * *El canal público se cierra.*

2.  **Gestión de Acciones:**
    * Los jugadores con habilidades nocturnas usarán `/act` en su canal privado.
    * Tú puedes ver qué hacen en tiempo real usando: `/actions logs phase:night`.
    * Si necesitas ver quién falta por actuar: `/actions breakdown phase:night`.

---

## 6. Nuevo Día y Ciclo

1.  **Terminar Noche:** `/end_night` (o espera al timer).

2.  **Resolución (GM):**
    * Antes de terminar la noche, revisa los logs.
    * Aplica los efectos resultantes usando el **Motor de Estados**:
        * `/effects apply user:@Victima name:Poisoned`
        * `/effects apply user:@Victima name:Silenced duration:1`
    * Si alguien muere por asesinato nocturno:
        * `/player kill user:@Victima`
        * Se revela la ficha del asesinado.

2.  **Iniciar Día Siguiente:** `/start_day duration:24h`.
    * *El bot anunciará los muertos, limpiará los votos y reducirá los contadores de los estados alterados automáticamente.*

---

## 🛠️ Situaciones Comunes y Soluciones

* **"¡Me equivoqué y maté al que no era!":**
    Usa `/player revive user:@Jugador`. Esto le devuelve el rol de vivo y lo deja listo para seguir jugando.

* **"El bot se reinició y no funcionan los comandos":**
    El bot tiene persistencia. Si se reinicia, simplemente sigue jugando. Si los roles de Discord dejan de responder, ejecuta `/setup` (sin borrar nada) para refrescar la memoria del bot.

* **Jugador abandona la partida (Modkill):**
    Usa `/player unregister user:@Jugador`. Esto lo borra de la base de datos y le quita el acceso a su canal privado.

* **Ajustar Hora/Fase:**
    Si necesitas saltar días o corregir el contador: `/bump_day delta:1` (Suma un día) o `/set_phase phase:night`.