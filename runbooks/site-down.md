---
title: Сайт не открывается
kind: situation
checked: '2026-11-11'
journal: ['2026-11-11']
---

## Простыми словами

Между браузером и подом приложения несколько звеньев: Cloudflare → ingress на `k8s-w1` → Service →
под. Код ошибки почти всегда говорит, на каком звене обрыв. Идём по цепочке снаружи внутрь, а не
гадаем.

## Как разбирать

1. **Что видит браузер.** Страница Cloudflare с кодом 52x — ответа от нашего ingress не было
   (521/522 — нода или ingress не отвечают, 524 — соединились, но ответа нет, 526 — сертификат на
   нашей стороне). 502/503/504 без оформления Cloudflare — ответил наш ingress
2. **Ingress жив:** `kubectl -n ingress-nginx get pods -o wide` — он на hostNetwork и привязан к
   `k8s-w1`. Нода `k8s-w1` лежит — лежат все сайты
3. **Лог ingress по сайту:** `kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --since=10m
   | grep <host>` — код и адрес пода, куда он ходил
4. **Поды и endpoints:** `kubectl -n <ns> get pods -o wide`, `kubectl -n <ns> get endpointslices` —
   есть ли готовые адреса
5. **Сеть:** `upstream timed out while connecting` при живых подах — NetworkPolicy в namespace
6. **Сертификат:** `kubectl -n <ns> get certificate` — `READY`, срок

## Как чинить

- 503, нет готовых подов — [поды не готовы](pods.html)
- 504 по таймауту соединения при живых подах — политика не пускает ingress. Наш ingress на hostNetwork,
  его пакеты идут с адреса ноды: нужна CiliumNetworkPolicy с `fromEntities: [host, remote-node]`
- 526 — [сертификат](certificates.html)

## Чтобы не повторилось

Проверять сайт после любых перестановок подов и нод, а не только «поды Running». Синтетическая
проверка снаружи (blackbox exporter) поймала бы это без человека — пока не сделана.

## Было у нас

11.11, после перехода на три воркера: `podinfo` — 504 за 15 секунд. Политика 44 дня пускала
«namespace ingress-nginx», а работало только потому, что podinfo жил на той же ноде, что и ingress.
