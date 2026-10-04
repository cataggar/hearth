#!/bin/sh
set -eu
/bin/busybox mount -t devtmpfs devtmpfs /dev
exec </dev/console >/dev/console 2>&1
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
/bin/busybox ip link set lo up
/bin/busybox ip addr add 192.0.2.2/30 dev eth0
/bin/busybox ip link set eth0 mtu 1500 up
/bin/busybox ip addr show eth0
/bin/busybox ip route show
/bin/busybox cat /sys/class/net/eth0/mtu /sys/class/net/eth0/address /proc/net/dev
/bin/busybox ls /sys/class/net/eth0/queues
/bin/peer 7000 &
/bin/peer 7001 &
/bin/peer 7002 &
/bin/peer 7003 &
echo PERF_TAP_READY
wait
