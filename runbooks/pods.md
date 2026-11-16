---
title: Поды падают или не готовы
alerts: [KubePodCrashLooping, KubePodNotReady, KubeDeploymentReplicasMismatch, KubeDeploymentRolloutStuck, KubePdbNotEnoughHealthyPods]
---

## Простыми словами

Под перезапускается по кругу, висит неготовым, у Deployment'а меньше готовых реплик, чем нужно, или
выкатка встала. Одна поломка обычно даёт сразу несколько этих алертов — они про одно и то же.

## Чем грозит

Сервис работает не на всех репликах или не работает совсем. Если PDB уже нарушен — drain ноды
заблокируется.

## Что проверить

1. `kubectl -n <ns> get pods -o wide` — статус, рестарты, нода
2. `kubectl -n <ns> describe pod <под>` — `Last State`, `Reason` (`OOMKilled`, `Error`), события
   (`FailedScheduling`, `Unhealthy`, пробы)
3. Логи упавшего экземпляра: `kubectl -n <ns> logs <под> --previous`
4. `Pending` — в событиях причина: `Insufficient memory`, `didn't match PersistentVolume's node
   affinity` (том на другой ноде), taint
5. Выкатка: `kubectl -n <ns> rollout status deploy/<имя>`, `rollout history`

## Как починить

- `OOMKilled` — поднять `limits.memory` в values
- Пробы — проверить путь, порт и задержку (`initialDelaySeconds`)
- Ждёт зависимость в init-контейнере — чинить зависимость (часто база)
- Плохая выкатка — `git revert` в gitops; `kubectl rollout undo` ArgoCD с selfHeal откатит обратно

## Когда звать на помощь

Падают все реплики сервиса и логи ничего не говорят — откатить последнее изменение.

## Было у нас

Prometheus внутри OTel Demo падает по памяти на лимите 400Mi — три алерта на одну причину, до починки
заглушён silence ([10.11.2026](../journal/2026-11-10.html)).
