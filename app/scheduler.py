"""Programador de tareas en segundo plano (APScheduler).

Ejecuta periódicamente la liberación de reservas vencidas (RF-06, RN-03).
Cuidados:
- No arrancar dos veces con el reloader de debug de Flask.
- No iniciar en entorno de pruebas ("testing").
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler

# Referencia al scheduler para poder detenerlo si hiciera falta.
_scheduler = None


def _tarea_expirar(app):
    """Ejecuta la expiración de reservas dentro del contexto de la app."""
    with app.app_context():
        from app.services.reservas_service import expirar_reservas_vencidas
        try:
            liberadas = expirar_reservas_vencidas()
            if liberadas:
                app.logger.info(
                    "Scheduler: %s reserva(s) vencida(s) liberada(s).",
                    liberadas)
        except Exception:  # noqa: BLE001
            # Nunca dejamos que un fallo del job tumbe el scheduler.
            app.logger.exception("Scheduler: error al expirar reservas.")


def iniciar_scheduler(app):
    """Arranca el scheduler si procede según el entorno.

    - En entorno de pruebas, no arranca.
    - Con el reloader de Flask en debug, solo arranca en el proceso hijo
      (WERKZEUG_RUN_MAIN == 'true') para no duplicar el job.
    """
    global _scheduler

    if app.config.get("TESTING"):
        return  # nunca en pruebas

    # Evitar doble arranque con el reloader de debug.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    if _scheduler is not None and _scheduler.running:
        return  # ya está corriendo

    intervalo = app.config.get("SCHEDULER_INTERVALO_SEGUNDOS", 30)
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _scheduler.add_job(
        func=lambda: _tarea_expirar(app),
        trigger="interval",
        seconds=intervalo,
        id="expirar_reservas",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    app.logger.info(
        "Scheduler iniciado: expira reservas cada %s s.", intervalo)
