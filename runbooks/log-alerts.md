---
title: Алерты по логам
alerts: [AppErrorLogsHigh, ImagePullFailing, LoginFailuresHigh, LokiRulesNotLoaded, LokiRuleEvaluationFailing, LokiRulerCannotNotify]
---

## Простыми словами

Большинство алертов считает Prometheus по метрикам. Эти — Loki по строкам логов: раз в минуту его
ruler выполняет запросы из правил и, если результат выше порога, отправляет алерт в тот же
Alertmanager. Алерт по логам заводится там, где метрики нет или смысл только в тексте: метрика
скажет «образ не скачивается», строка kubelet — почему.

Три алерта про кластер и три — про сам ruler: он ломается молча, и тогда первые три просто не
приходят.

## Чем грозит

- `AppErrorLogsHigh` — приложение сыплет ошибками. Для сервиса без своих метрик это единственный
  сигнал, что ему плохо
- `ImagePullFailing` — под не стартует; если это новая версия при выкатке — выкатка стоит
- `LoginFailuresHigh` — кто-то подбирает пароль к ArgoCD или Grafana. Обе морды за Cloudflare Access,
  поэтому снаружи без входа в Access до формы не дойти: это свой, ошибся или скрипт со старым паролем
- `LokiRulesNotLoaded`, `LokiRuleEvaluationFailing`, `LokiRulerCannotNotify` — алерты по логам не
  работают совсем, и узнать об этом больше неоткуда

## Что проверить

1. **AppErrorLogsHigh** — сами строки в Grafana → Explore → Loki:
   `{namespace="<ns>", app="<app>"} | detected_level="error"`. Одна повторяющаяся строка или разные?
   С какого времени — совпадает ли с выкаткой (ArgoCD → история приложения)
2. **ImagePullFailing** — причина уже в алерте (`reason`), подробности —
   `kubectl -n <ns> describe pod <pod>`, раздел Events:
   - `not found` — такого тега нет: опечатка в теге или его удалила чистка registry
   - `unauthorized` (401) — нет pull-секрета или протухли креды в нём
   - `Forbidden` / `denied` (403) — креды есть, а прав на репозиторий нет; GHCR так же отвечает на
     чужой или несуществующий репозиторий без входа
   - `no such host`, `i/o timeout` — нода не достаёт до registry: DNS или сеть
   - `too many requests` — лимит Docker Hub на анонимные скачивания
3. **LoginFailuresHigh** — кто и откуда: в Explore
   `{app="argocd-server"} |~ "(?i)invalid username or password"` (для Grafana — `{app="grafana"}`).
   Адрес клиента — в access-логе ingress: `{app="ingress-nginx"} | json | host=~"argocd.*|grafana.*"`
4. **Ruler** — какие правила он видит и их состояние:
   `kubectl get --raw /api/v1/namespaces/logging/services/loki:3100/proxy/prometheus/api/v1/rules`.
   Пусто — правила не загружены; `"health":"err"` — запрос падает, текст в `lastError`

## Как починить

- `AppErrorLogsHigh` — чинить источник. Откат выкатки, если началось с неё. otel-demo роняет себя
  сам фичефлагами — его алерты идут в тихий канал
- `ImagePullFailing`:
  - `not found` — поправить тег в gitops; если тег удалила чистка — пересобрать образ или откатиться
    на живой тег
  - `unauthorized` — обновить pull-секрет и проверить `imagePullSecrets` у пода или ServiceAccount.
    Под после этого не ждать: `kubectl delete pod`, kubelet повторяет загрузку с паузой до 5 минут
- `LoginFailuresHigh` — если это не ты: сменить пароль admin, посмотреть, кто входил в Access
  (Cloudflare → Zero Trust → Logs)
- `LokiRulesNotLoaded`:
  - есть ли ConfigMap: `kubectl -n logging get cm -l loki_rule`. Нет — смотреть приложение
    `logging-rules` в ArgoCD
  - есть, а правил нет — лог сайдкара: `kubectl -n logging logs loki-0 -c loki-sc-rules`. Ruler
    ищет файлы в `/rules/fake`, `fake` — тенант без авторизации
  - битый YAML или LogQL — лог Loki: `kubectl -n logging logs loki-0 -c loki | grep -i rule`. До
    выкатки такое ловит проверка в CI (`scripts/check-log-rules.py`)
- `LokiRuleEvaluationFailing` — текст ошибки в `lastError` (шаг 4 выше). Таймаут или лимит потоков —
  сузить селектор запроса
- `LokiRulerCannotNotify` — жив ли Alertmanager (`kubectl -n monitoring get pods`), верен ли
  `rulerConfig.alertmanager_url` в `values/loki/values.yaml`

## Когда звать на помощь

`LoginFailuresHigh`, который не объясняется своими ошибками, — сразу: это вопрос безопасности, а не
надёжности.

## Было у нас

17.11.2026, шаг 2-9: правила проверили провокациями — под, который пишет строки уровня error, два
пода с несуществующими образами и неверные пароли. Первая версия `ImagePullFailing` давала на одну
неудачу два алерта: kubelet пишет про неё четыре строки, `ErrImagePull` есть в двух, а неймспейс
пода — только в одной.
