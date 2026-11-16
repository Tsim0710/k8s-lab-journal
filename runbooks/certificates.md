---
title: Сертификат не продлевается
alerts: [CertificateExpiringSoon]
---

## Простыми словами

cert-manager продлевает сертификаты Let's Encrypt за 30 дней до конца. Если до конца осталось меньше
21 дня (warning) или 7 (critical) — продление уже не прошло, и само не пройдёт. Когда сертификат
истечёт, Cloudflare в режиме strict перестанет ходить на сайт и покажет 526.

## Чем грозит

Сайт ляжет в день истечения. Время ещё есть, но чинить надо сейчас.

## Что проверить

1. `kubectl -n <namespace> get certificate` — `READY`, срок
2. `kubectl -n <namespace> describe certificate <имя>` — события и причина
3. Цепочка cert-manager: `kubectl -n <namespace> get certificaterequest,order,challenge` — на каком
   шаге застряло
4. Логи: `kubectl -n cert-manager logs deploy/cert-manager --since=1h | grep -i error`

## Как починить

- DNS-01 через Cloudflare: проверить токен API (права на зону), что TXT-запись создаётся
- Лимиты Let's Encrypt — подождать, пока не кончится окно, не перевыпускать в цикле
- Запустить продление руками: `cmctl renew -n <namespace> <имя>`; без cmctl — удалить последний
  неудачный CertificateRequest, cert-manager создаст новый. **Secret сертификата не удалять:** ingress
  останется без сертификата, и Cloudflare сразу отдаст 526

## Когда звать на помощь

Critical (меньше 7 дней) и причина непонятна — завести запасной путь заранее, а не в день истечения.
