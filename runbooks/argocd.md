---
title: ArgoCD — приложение не синхронизировано
alerts: [ArgoAppOutOfSync, ArgoAppDegraded, ArgoAppSyncFailed, ArgoAppUnknown]
---

## Простыми словами

ArgoCD сравнивает то, что лежит в git, с тем, что в кластере. OutOfSync — есть разница. Degraded —
ресурсы приложения нездоровы. SyncFailed — синк упал. Unknown — ArgoCD не может сравнить (обычно не
читает репо или не рендерит чарт).

## Чем грозит

Изменения из git не доходят до кластера, или в кластере правят руками мимо git. Degraded — сервис
работает плохо.

## Что проверить

1. `kubectl -n argocd get applications` — какое приложение
2. Что именно отличается: `kubectl -n argocd get application <имя> -o json | jq -r
   '.status.resources[] | select(.status=="OutOfSync") | "\(.kind)/\(.name)"'`
3. Ошибка синка: `.status.operationState.message`, `.status.conditions`
4. Degraded — `kubectl -n <ns> get pods`, дальше [поды не готовы](pods.html)

## Как починить

- Правка руками мимо git — вернуть в git или дать selfHeal откатить
- Вечный OutOfSync на одном поле — значение по умолчанию, которое дописывает API-сервер. Написать его в
  values явно или добавить `ignoreDifferences`
- Unknown — доступ к репо (deploy key), рендер чарта: `helm template` с теми же values

## Когда звать на помощь

SyncFailed на платформенном приложении (kube-prometheus-stack, cert-manager, ingress) — не синкать
повторно вслепую, сначала прочитать ошибку.

## Было у нас

kube-prometheus-stack был вечно OutOfSync: в ServiceMonitor node-exporter API-сервер дописывал
`action: replace` по умолчанию (16.11.2026).

`ArgoAppSyncFailed` не сработал на первом провале синка у `notes-stage`: ряд счётчика провалов
появился сразу со значением 1, и `increase()` дал 0. Пришёл только `ArgoAppOutOfSync` через 15 минут.
Правило дополнено проверкой появления ряда, тесты — в gitops (20.11.2026).
