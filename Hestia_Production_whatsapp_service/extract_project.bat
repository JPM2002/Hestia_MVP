@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "OUT=project_extract.txt"
if exist "%OUT%" del "%OUT%"

set FILES=gunicorn.conf.py ^
Procfile ^
README.md ^
render.yaml ^
requirements.txt ^
run.py ^
run_notification_worker.py ^
test_fallback_message_simple.py ^
test_faq.json ^
test_faq_fallback.py ^
wsgi.py ^
gateway_app\config.py ^
gateway_app\filters.py ^
gateway_app\logging_cfg.py ^
gateway_app\wsgi.py ^
gateway_app\__init__.py ^
gateway_app\blueprints\webhook\routes.py ^
gateway_app\blueprints\webhook\__init__.py ^
gateway_app\blueprints\webhook\templates\webhook\webhook_debug.html ^
gateway_app\core\errors.py ^
gateway_app\core\faq_survey_handler.py ^
gateway_app\core\message_handler.py ^
gateway_app\core\models.py ^
gateway_app\core\status.py ^
gateway_app\core\survey_handler.py ^
gateway_app\core\timefmt.py ^
gateway_app\core\utils.py ^
gateway_app\core\conversation\orchestrator.py ^
gateway_app\core\conversation\session.py ^
gateway_app\core\conversation\__init__.py ^
gateway_app\core\conversation\pipeline\context.py ^
gateway_app\core\conversation\pipeline\pipeline.py ^
gateway_app\core\conversation\pipeline\__init__.py ^
gateway_app\core\conversation\pipeline\stages\base.py ^
gateway_app\core\conversation\pipeline\stages\cancellation_stage.py ^
gateway_app\core\conversation\pipeline\stages\fallback_stage.py ^
gateway_app\core\conversation\pipeline\stages\intent_routing_stage.py ^
gateway_app\core\conversation\pipeline\stages\nlu_stage.py ^
gateway_app\core\conversation\pipeline\stages\session_stage.py ^
gateway_app\core\conversation\pipeline\stages\shortcut_stage.py ^
gateway_app\core\conversation\pipeline\stages\state_routing_stage.py ^
gateway_app\core\conversation\pipeline\stages\__init__.py ^
gateway_app\core\conversation\utils\area_utils.py ^
gateway_app\core\conversation\utils\constants.py ^
gateway_app\core\conversation\utils\message_parser.py ^
gateway_app\core\conversation\utils\__init__.py ^
gateway_app\core\conversation\workflows\__init__.py ^
gateway_app\core\intents\base.py ^
gateway_app\core\intents\faq_handler.py ^
gateway_app\core\intents\handoff_handler.py ^
gateway_app\core\intents\identity_handler.py ^
gateway_app\core\intents\identity_handler_clarification.py ^
gateway_app\core\intents\smalltalk_handler.py ^
gateway_app\core\intents\ticket_handler.py ^
gateway_app\core\intents\ticket_status_handler.py ^
gateway_app\core\intents\__init__.py ^
gateway_app\core\utils\location_format.py ^
gateway_app\services\audio.py ^
gateway_app\services\conversation_logger.py ^
gateway_app\services\db.py ^
gateway_app\services\dsn.py ^
gateway_app\services\faq_llm.py ^
gateway_app\services\guest_llm.py ^
gateway_app\services\notify.py ^
gateway_app\services\routing_rules.py ^
gateway_app\services\sla.py ^
gateway_app\services\tickets.py ^
gateway_app\services\token_tracker.py ^
gateway_app\services\triage.py ^
gateway_app\services\whatsapp_api.py ^
gateway_app\services\workers_db.py ^
gateway_app\services\ai\prompt_loader.py ^
gateway_app\services\ai\__init__.py ^
gateway_app\services\ai\prompts\confirm_draft_v1.txt ^
gateway_app\services\ai\prompts\faq_system_v1.txt ^
gateway_app\services\ai\prompts\nlu_system_v1.txt ^
gateway_app\services\data\faq_items.json ^
gateway_app\services\data\faq_loader.py ^
gateway_app\services\data\__init__.py ^
gateway_app\services\notifications\handlers.py ^
gateway_app\services\notifications\notification_config.py ^
gateway_app\services\notifications\notification_db.py ^
gateway_app\services\notifications\notification_whatsapp.py ^
gateway_app\services\notifications\__init__.py ^
gateway_app\templates\base.html ^
gateway_app\templates\error.html ^
gateway_app\tests\test_faq_llm.py ^
gateway_app\tests\test_guest_llm.py ^
gateway_app\tests\test_state_machine.py ^
gateway_app\tests\test_webhook_smoke.py ^
gateway_app\workers\notification_worker.py ^
gateway_app\workers\__init__.py

for %%F in (%FILES%) do (
  echo === %%F ===>> "%OUT%"
  if exist "%%F" (
    type "%%F">> "%OUT%"
  ) else (
    echo [MISSING FILE] %%F>> "%OUT%"
  )
  echo.>> "%OUT%"
)

echo Listo. Generado: %OUT%
endlocal
