#!/bin/bash
# Depends on:
#   ~/scripts/calc-stats.py from https://git.lekensteyn.nl/scripts.git
#   /tmp/x{,0..n} writable
#   ../Kconfiglib code
#   $PWD is linux at v4.2-rc5
#   $PWD/../Kconfiglib exists
set -u -e -o pipefail

py() {
    local code=$1
    PYTHONPATH=../Kconfiglib ARCH=x86_64 SRCARCH=x86 KERNELVERSION=4.2.0-rc5 \
        "$PYTHON" -c "$code"
}
calc_stats() {
    local timings=$(cat) # fully consume data first to not affect results
    (eval $(echo "$timings" |
            grep '^real.*\K\d\.\d+' -oP |
            ~/scripts/calc-stats.py |
            sed '/Data/d;s/[:=] */=/');
     printf '| %-22s| %.3fs | %.3fs | %.3fs | %.4fs |\n' \
            "$label" $Mean $min $max $sd)
}
py_n() {
    local code=$1 i
    py "$code" || return 0 # warming up and skip errors
    for ((i=0; i<n; i++)); do
        time py "$code"
    done |& calc_stats
}
: ${PYTHON:=python}

n=10
p_max=$("$PYTHON" -c 'import pickle; print(pickle.HIGHEST_PROTOCOL)')

desc="test (n=$n, $("$PYTHON" --version |& sed 's/Python /Py/'))"

printf '| %-22s| avg    | min    | max    | stdDev  |\n' "$desc"
printf '| --------------------- | ------ | ------ | ------ | ------- |\n'

label="Config"
py_n "import kconfiglib; kconfiglib.Config()"

for ((p=p_max; p>=0; p--)); do
    label="Config+pickle.dump($p)"
    rm -f /tmp/x /tmp/x$p
    py_n "import kconfiglib, pickle, sys; c=kconfiglib.Config(); sys.setrecursionlimit(100000); pickle.dump(c, open('/tmp/x','wb'), $p)"
    [ ! -s /tmp/x ] || mv /tmp/x /tmp/x$p
done

for ((p=p_max; p>=0; p--)); do
    [ -s /tmp/x$p ] || continue
    mv /tmp/x$p /tmp/x
    label="pickle.load [$p] $(du -sh /tmp/x | awk '{print $1}')"
    py_n "import kconfiglib, pickle, sys; c=pickle.load(open('/tmp/x','rb'))"
done

rm -f /tmp/x
