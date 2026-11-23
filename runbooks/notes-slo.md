---
title: Доступность notes на stage
alerts:
  - NotesStageSLOBurnRate
  - NotesStageSLOProbeMissing
---

## Что проверяем

Каждые 30 секунд blackbox exporter читает одну тестовую заметку через внутренний Service `notes`.
Для успеха нужен HTTP 200 в течение пяти секунд. Цель — **99% успешных проб за последние семь суток**.
Это проверка клиентского пути на stage. Число собранных проб видно в `lab:notes_stage_sli:samples7d`.
После включения пробы или простоя лаба история за семь суток может быть неполной.

## Что проверить

1. Открой в Prometheus `probe_success{target="notes-stage-slo"}` и `probe_http_status_code{target="notes-stage-slo"}`.
   Код 0 означает, что HTTP-ответа не было. 404 требует проверить тестовую запись и маршрут.
2. При `NotesStageSLOBurnRate` сравни `lab:notes_stage_slo:burn_rate1h` и
   `lab:notes_stage_slo:burn_rate5m`. Проверь последнюю ревизию `notes-stage` в ArgoCD,
   порт Service, готовность pod и ошибки PostgreSQL.
3. При `NotesStageSLOProbeMissing` открой Prometheus Targets. Проверь, видна ли цель
   `notes-stage-slo` и отвечает ли blackbox exporter на опрос. Пустой ряд требует проверить
   сбор данных. Значение 0 в ряду означает, что exporter измерил отказ запроса.

## Как вернуть доступность

Если деградация началась после выкатки, верни рабочую ревизию конфигурации или совместимый тег
образа в stage overlay. Дождись применения этой ревизии ArgoCD. Подтверди HTTP 200 по той же
пробе. После того как неудачные пробы выйдут из окна пяти минут, быстрый алерт должен погаснуть.
Потраченная часть бюджета останется в семидневной истории.
