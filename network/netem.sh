#!/bin/bash
# netem.sh — Apply tc netem network profiles on WSL2 loopback (lo).
# Chrome traffic to localhost:3000 travels through lo in WSL2 mirrored mode.
# Usage: sudo ./netem.sh {baseline|latency|loss|congested|clear}

IFACE=lo

# Always clear any existing qdisc first
tc qdisc del dev $IFACE root 2>/dev/null

case "$1" in

  baseline|clear)
    echo "Profile: baseline — no impairment"
    ;;

  latency)
    tc qdisc add dev $IFACE root netem delay 150ms
    echo "Profile: latency — 150ms delay"
    ;;

  loss)
    tc qdisc add dev $IFACE root netem loss 3%
    echo "Profile: loss — 3% packet loss"
    ;;

  congested)
    tc qdisc add dev $IFACE root handle 1: htb default 10
    tc class add dev $IFACE parent 1: classid 1:10 htb rate 1500kbit
    tc qdisc add dev $IFACE parent 1:10 handle 10: netem delay 50ms loss 1%
    echo "Profile: congested — 1.5 Mbps cap + 50ms delay + 1% loss"
    ;;

  *)
    echo "Usage: sudo $0 {baseline|latency|loss|congested|clear}"
    exit 1
    ;;

esac
