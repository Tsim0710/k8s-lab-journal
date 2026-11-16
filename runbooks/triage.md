---
title: Порядок разбора любого алерта
alerts: [AlertmanagerClusterFailedPeers, KubeJobNotCompleted, NodeBondingDegraded, NodeSystemdServiceCrashlooping, NodeSystemdServiceFailed, PrometheusOperatorStatusUpdateErrors, PrometheusHighQueryLoad, PrometheusKubernetesListWatchFailures, PrometheusScrapeBodySizeLimitHit, PrometheusScrapeSampleLimitHit, PrometheusSDRefreshFailure]
---

Сюда ведут алерты, для которых нет своей страницы. Порядок одинаковый для любого.

## Простыми словами

Алерт — это не диагноз, а симптом: какое-то правило в Prometheus ответило «да». Сначала понять, правда
ли это и насколько срочно, потом искать причину, и только потом чинить. Самая частая ошибка — начать
чинить первое, что пришло в голову.

## Что проверить

1. **Текст алерта.** Описание (`description`) почти всегда говорит, какая метрика и какой порог. Метки
   `namespace`, `pod`, `node` — где искать
2. **Жив ли сам мониторинг.** Если горит много всего сразу, особенно `*Down` — сначала
   [Prometheus не пишет данные](prometheus-no-data.html) и [компоненты пропали](components-down.html)
3. **Что менялось.** Последние коммиты в gitops, синки в ArgoCD, `lab-up` после простоя. Большинство
   поломок — следствие изменения
4. **Само правило.** В Grafana → Explore выполнить выражение алерта (`expr` в PrometheusRule) и
   посмотреть график за час — растёт, скачет, стоит на месте
5. **Объект.** `kubectl describe` по поду или ноде из меток, `kubectl get events -n <ns>
   --sort-by=.lastTimestamp`, логи (`kubectl logs`, в Grafana — Loki)

## Как починить

Зависит от алерта. Если чинишь не по runbook — после починки напиши runbook, чтобы в следующий раз он
был.

## Когда звать на помощь

- Затронуты пользователи (сайты отдают ошибки) и за 15 минут причины нет — откатить последнее изменение
  (`git revert` в gitops) и разбираться уже без давления
- Подозрение на данные (etcd, базы, тома) — сначала снимок или бэкап, потом любые действия
