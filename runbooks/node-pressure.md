---
title: Давление на ноду и выселения
alerts: [KubeNodePressure, KubeNodeEviction]
---

## Простыми словами

kubelet видит, что на ноде кончается память, диск или PID, ставит ноде состояние `MemoryPressure` /
`DiskPressure` / `PIDPressure` и начинает выселять поды, чтобы спасти ноду. Выселяют сначала тех, кто
превысил свои requests.

## Чем грозит

Поды перезапускаются на других нодах (если есть место) или висят в `Pending`.

## Что проверить

1. `kubectl describe node <нода>` — `Conditions`, внизу события `Evicted` / `EvictionThresholdMet`
2. Выселенные поды: `kubectl get pods -A | grep Evicted`
3. Что съело ресурс — [ресурсы ноды](node-resources.html), [диск](disk.html)

## Как починить

- Память — найти под без `limits` или с завышенным потреблением, ограничить
- Диск — по runbook диска
- Убрать выселенные поды: `kubectl delete pods -A --field-selector status.phase=Failed`

## Когда звать на помощь

Выселения идут по кругу на всех воркерах — ёмкости не хватает, см.
[потерю воркера](workers-overcommit.html).
