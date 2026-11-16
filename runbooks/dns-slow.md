---
title: Внутри кластера тормозит или не работает DNS
kind: situation
checked: '2026-11-08'
journal: ['2026-11-08']
---

## Простыми словами

Без DNS приложения не падают, а тормозят: каждый запрос по имени ждёт таймаут. Поэтому сломанный DNS
часто выглядит как «всё медленно», а не как ошибка.

## Как разбирать

1. По имени и по IP из пода: если по IP быстро, а по имени долго или ошибка — это DNS
   (`kubectl run -it --rm dnstest --image=busybox:1.37.0 -- nslookup kubernetes.default`)
2. CoreDNS жив: `kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide` — сколько реплик и где
3. Логи: `kubectl -n kube-system logs -l k8s-app=kube-dns --since=10m` — `reload failed`, ошибки
   плагинов
4. Конфиг: `kubectl -n kube-system get cm coredns -o yaml`

## Как чинить

- Реплик 0 или все на одной упавшей ноде — вернуть; PDB у CoreDNS у нас есть
- Сломан Corefile — вернуть рабочую копию ConfigMap. Копию применять без `resourceVersion`, иначе 409

## Чтобы не повторилось

Опечатка в Corefile не ломает DNS сразу: CoreDNS остаётся на старом конфиге и пишет `reload failed`.
Ломается на следующем рестарте подов — поэтому проверять логи после правки конфига.

## Было у нас

08.11: CoreDNS в 0 — запрос по имени висел 4.8 с (musl в образе на Alpine ждёт таймаут), по IP — 0.025
с. Опечатка `cachee` — DNS держался на одном старом поде, rollout висел.
