---
title: Снимок etcd не делается
alerts: [EtcdBackupTooOld, EtcdBackupMissing]
---

## Простыми словами

Раз в час CronJob `etcd-backup` на мастере снимает снимок базы кластера и кладёт его на диск мастера
(`/var/backups/etcd`, хранятся последние 24). Алерт смотрит не на ошибки, а на время последнего
успешного снимка: CronJob, который удалили, приостановили или сломали так, что он не стартует, ошибок
не даёт — снимки просто перестают появляться.

Важно: снимок на том же диске, что и etcd, — ещё не настоящий бэкап. Умрёт диск мастера — пропадут
и база, и снимки. Вынос в бакет — шаг 4-3.

## Чем грозит

Если сейчас испортится база кластера, откатываться будет не к чему или к слишком старому снимку.

## Что проверить

1. CronJob на месте и не приостановлен: `kubectl -n kube-system get cronjob etcd-backup` —
   `SUSPEND False`, `LAST SCHEDULE`
2. Последние запуски: `kubectl -n kube-system get jobs -l job-name --sort-by=.status.startTime | tail`
   или `kubectl -n kube-system get jobs | grep etcd-backup`
3. Почему упал: `kubectl -n kube-system logs job/<имя> -c snapshot` (снимок) и `-c rotate` (имя и
   чистка); `kubectl -n kube-system describe job <имя>`
4. Сами снимки: на мастере `make ssh-cp`, `ls -lh /var/backups/etcd`; место — `df -h /`

## Как починить

- Ошибки сертификатов в `snapshot` — проверить пути к ключам etcd в CronJob (gitops,
  `manifests/kube-system/etcd-backup.yaml`)
- `SUSPEND True` или CronJob нет — вернуть из git (ArgoCD с selfHeal сделает сам, если правку
  руками)
- Нет места на мастере — [диск](disk.html)
- Проверить, что починилось, не дожидаясь часа:
  `kubectl -n kube-system create job --from=cronjob/etcd-backup etcd-backup-manual-1`

## Когда звать на помощь

Перед любой рискованной операцией с кластером без свежего снимка — сначала снимок руками:
`make etcd-backup` (копия уходит на ноутбук).
