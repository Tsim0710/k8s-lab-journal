---
title: Логи не доходят до Loki
alerts: [LogShippingFailing, LokiDiscardingLogs]
---

## Простыми словами

На каждой ноде работает Fluent Bit: дочитывает файлы логов контейнеров и журнал kubelet и отправляет
строки в Loki. Сломаться может на двух участках, и в Grafana оба выглядят одинаково — «логов нет»:

- **Fluent Bit не может отдать строки** (`LogShippingFailing`) — Loki лежит, недоступен по сети или
  отвечает ошибкой. Строки пока копятся в буфере на диске ноды и будут досланы, когда Loki оживёт.
  Буфер ограничен (256 МБ на ноду), переполнится — новые строки начнут теряться
- **Loki принял строки и выбросил** (`LokiDiscardingLogs`) — со стороны Fluent Bit всё хорошо, а
  строк в Loki нет. Причина в метке `reason`: `too_far_behind` (строка старее, чем Loki готов принять
  в этот поток), `rate_limited` (слишком много строк в секунду), `line_too_long`, `stream_limit`

## Чем грозит

Логи нужны ровно тогда, когда что-то сломалось. Без них разбор инцидента — гадание. Отброшенные
строки не вернуть.

## Что проверить

1. Жив ли Loki: `kubectl -n logging get pods` — `loki-0` Running и готов
2. Что пишет Fluent Bit на проблемной ноде:
   `kubectl -n logging logs ds/fluent-bit --since=15m | grep -iE 'error|warn'` (или под конкретной ноды:
   `kubectl -n logging get pods -o wide`)
3. Кого и почему выбрасывает Loki — в его логе есть поток и причина:
   `kubectl -n logging logs loki-0 -c loki --since=15m | grep -iE 'discard|too far behind|rate limit'`
4. Буфер Fluent Bit — метрика `fluentbit_input_storage_chunks` и место на диске ноды в
   `/var/lib/fluent-bit/storage`

## Как починить

- Loki лежит или его нода — поднять ([нода недоступна](../situations/node-unreachable.html)). Fluent Bit
  дошлёт буфер сам
- `too_far_behind` у одного потока — в потоке есть строка «из будущего» (часы ноды убегали), и всё
  нынешнее для Loki слишком старо. Проверить время на нодах (`timedatectl` через `make ssh-*`, алерт
  `NodeClockSkewDetected`). Поток живёт, пока в него пишут: новые строки с другим набором меток идут в
  новый поток
- `rate_limited` — кто-то пишет лавину: найти по `sum by (app) (rate({namespace=~".+"}[1m]))` в
  Grafana Explore, чинить источник. Поднимать `ingestion_rate_mb` в Loki — только если поток законный
- `line_too_long` — приложение пишет строки длиннее 256 КБ, обычно дамп; чинить в приложении

## Когда звать на помощь

Если Loki не поднимается из-за диска или WAL — сначала сохранить под и PVC, не удалять их: в WAL
последние строки, которые ещё не легли в хранилище.

## Было у нас

17.11.2026, шаг 2-8: при замене Alloy на Fluent Bit выяснилось, что Loki с 10.11 выбрасывал около
23% строк с причиной `too_far_behind` — и никто не знал: метрик Loki в Prometheus не было. Причина —
мина с часами из шага 1-8: часы на w2 ушли в 2028 год, и строки Loki, Prometheus, Grafana и
otel-collector с w2 легли в Loki с датой из будущего. Защита Loki от будущего (`creation_grace_period`)
не сработала: Loki сам живёт на w2 и считал по тем же часам. Fluent Bit пишет с другими метками —
в новые потоки, и отбросы прекратились вместе с Alloy. С тех пор метрики Loki в Prometheus и этот алерт.
