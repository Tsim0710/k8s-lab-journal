---
title: etcd тормозит или растёт
alerts: [etcdDatabaseQuotaLowSpace, etcdExcessiveDatabaseGrowth, etcdDatabaseHighFragmentationRatio, etcdHighCommitDurations, etcdHighNumberOfFailedProposals, etcdHighNumberOfLeaderChanges, etcdMemberCommunicationSlow]
---

## Простыми словами

etcd — база, где Kubernetes хранит всё. Эти алерты — про её здоровье: база подходит к квоте (по
умолчанию 2 GiB, дальше etcd перестаёт принимать запись), растёт слишком быстро, сильно
фрагментирована, медленно пишет на диск, часто меняет лидера или плохо связывается с соседями. С
11.11 участник у нас один, поэтому алерты про лидера и связь между участниками сейчас почти не
актуальны.

## Чем грозит

Квота — кластер перестаёт принимать любые изменения. Медленный диск — тормозит весь API.

## Что проверить

1. Размер и квота: `make etcd ARGS='endpoint status -w table'` — `DB SIZE`
2. Кто раздувает базу: `make etcd ARGS='get /registry --prefix --keys-only' | cut -d/ -f3 | sort |
   uniq -c | sort -rn | head` — обычно events или CRD с большими объектами
3. Диск: в Explore `histogram_quantile(0.99,
   rate(etcd_disk_wal_fsync_duration_seconds_bucket[5m]))` — норма меньше 10 мс

## Как починить

- Фрагментация — `make etcd ARGS='defrag'` (на время дефрагментации участник не отвечает)
- Близко к квоте — найти источник, удалить мусор, потом компакция и defrag; `alarm disarm`, если
  сработал `NOSPACE`
- Медленный диск — pd-ssd вместо pd-balanced для мастера

## Когда звать на помощь

Перед любым defrag и чисткой — снимок `make etcd-backup`. etcd в `NOSPACE` — это стоп записи для всего
кластера, действовать сразу.

## Было у нас

[19.10.2026](../journal/2026-10-19.html) — etcd изнутри: ревизии, компакция, defrag после
перешифровки. [02.11.2026](../journal/2026-11-02.html) — снимок и восстановление.
