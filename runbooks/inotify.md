---
title: Кончаются inotify на ноде
alerts: [InotifyInstancesNearLimit, InotifyMetricsStale]
---

## Простыми словами

inotify — механизм «сообщи, когда файл изменится». Лимит `fs.inotify.max_user_instances` считается
на пользователя (uid), а под root на ноде живут kubelet, containerd и все root-контейнеры — они делят
один лимит. Кончился — новые программы падают с непонятным «too many open files», а systemd может
потерять слежение за дисками и начать гасить службы.

`InotifyMetricsStale` — другое: сайдкар, который считает inotify, перестал обновлять файл, и первый
алерт ослеп.

## Чем грозит

Нода уходит в `NotReady`, по SSH не пускает. Так у нас уже было.

## Что проверить

1. Кто держит: на ноде (`make ssh-w1` и т. п.) — по процессам `for p in /proc/[0-9]*; do n=$(sudo ls
   -l $p/fd 2>/dev/null | grep -c inotify); [ $n -gt 0 ] && echo "$n $(cat $p/comm)"; done | sort -rn
   | head`
2. Лимит: `sysctl fs.inotify.max_user_instances`
3. Для `InotifyMetricsStale`: `kubectl -n monitoring get pods -l
   app.kubernetes.io/name=prometheus-node-exporter -o wide`, логи контейнера `inotify` в поде с этой ноды

## Как починить

- Найти и унять источник: обычно сборщик логов без фильтра по ноде или под, который плодит watch'и
- Поднять лимит — `stage2/01-prereqs.sh` и `sysctl -w` на ноде
- Сайдкар не работает — проверить его права (root, `SYS_PTRACE`, AppArmor Unconfined): без них он не
  видит чужие процессы и молча занижает счёт

## Когда звать на помощь

Нода уже `NotReady` и SSH молчит — смотреть serial-консоль: `gcloud compute instances
get-serial-port-output <нода>`. Лечение — stop/start машины.

## Было у нас

[02.11.2026](../journal/2026-11-02.html): оба воркера `NotReady` 2 ч 38 мин, лимит 128, источник —
Alloy без фильтра по ноде. [11.11.2026](../journal/2026-11-11.html): сайдкар насчитал в 30 раз меньше
правды из-за AppArmor.
