---
title: Нода перегружена — CPU, диск, память
alerts: [NodeSystemSaturation, NodeCPUHighUsage, NodeDiskIOSaturation, NodeMemoryHighUtilization, NodeMemoryMajorPagesFaults]
---

## Простыми словами

На ноде не хватает ресурса: процессы стоят в очереди к процессору (нагрузка на ядро выше 2), ждут
диск, память почти кончилась или система постоянно дочитывает страницы с диска. Поды на такой ноде
работают медленно, а при нехватке памяти kubelet начнёт выселять их.

## Чем грозит

Тормозят все поды ноды. При нехватке памяти — выселения и OOM.

## Что проверить

1. Какая нода — метка `node` в алерте
2. Чем занят процессор — в Explore `sum by (mode) (rate(node_cpu_seconds_total{node="<нода>",
   mode!="idle"}[5m]))`: `user`/`system` — работают процессы, `iowait` — ждут диск, `steal` —
   гипервизор отдал процессор соседям по железу
3. Кто ест: `kubectl top pod -A --sort-by=cpu | head`, `--sort-by=memory`; что стоит на ноде:
   `kubectl get pods -A -o wide --field-selector spec.nodeName=<нода>`
4. Grafana: «Node Exporter / Nodes» и «Kubernetes / Compute Resources / Node (Pods)»

## Как починить

- Один прожорливый под — ограничить (`limits`), уменьшить нагрузку (у демо — генератор нагрузки)
- Поды скопились на одной ноде — `kubectl rollout restart` тяжёлых Deployment'ов: планировщик сам не
  перераспределяет, только при создании пода
- `steal` высокий — соседи по железу, у E2 так бывает; у N2 ядра выделенные

## Когда звать на помощь

Нода перестаёт отвечать (`NotReady`, SSH тормозит) — [нода NotReady](node-not-ready.html).

## Было у нас

[10.11.2026](../journal/2026-11-10.html): первый алерт после подключения Telegram — нагрузка 11–16 на
ядро на `k8s-w1`, почти весь OTel Demo на одной ноде.
