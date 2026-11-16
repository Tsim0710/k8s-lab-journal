---
title: Сайт отвечает ошибками или тормозит
alerts: [IngressErrorRateHigh, IngressLatencyHigh]
---

## Простыми словами

Это то, что видит пользователь. Через ingress больше 5% запросов к сайту заканчиваются ошибкой 5xx
(25% — critical), или 1% самых медленных ответов дольше 2 секунд. Ошибку 5xx отдаёт либо само
приложение, либо ingress, когда не может до приложения достучаться.

## Чем грозит

Пользователи получают ошибки или ждут. Это главный алерт для сайта — остальные объясняют причину.

## Что проверить

1. Какой код: в логах ingress `kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --since=10m
   | grep <host>` — 502 (приложение упало или не слушает), 503 (нет готовых подов), 504 (таймаут)
2. Поды приложения: `kubectl -n <ns> get pods -o wide`, готовы ли, где живут
3. Endpoints: `kubectl -n <ns> get endpointslices` — есть ли адреса с `ready=true`
4. Логи приложения: `kubectl -n <ns> logs deploy/<app> --since=10m`
5. Сеть: `upstream timed out while connecting` при живых подах — смотреть NetworkPolicy в namespace

## Как починить

- Поды падают — [поды не готовы](pods.html)
- Таймаут на соединение при живых подах — проверить, что NetworkPolicy пускает ingress. Наш ingress на
  hostNetwork, его пакеты идут с адреса ноды: нужна CiliumNetworkPolicy с `fromEntities: [host,
  remote-node]`, `namespaceSelector` его не видит
- Медленно — нагрузка на ноду ([ресурсы ноды](node-resources.html)), база, внешний сервис

## Когда звать на помощь

Critical (больше 25% ошибок) и причины нет за 15 минут — откатить последнее изменение приложения.

## Было у нас

[11.11.2026](../journal/2026-11-11.html): podinfo отдавал 504 после переезда подов на другие воркеры —
NetworkPolicy никогда не пускала ingress на hostNetwork, а работало, пока они жили на одной ноде.
