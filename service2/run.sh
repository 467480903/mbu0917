#!/bin/bash
# ─────────────────────────────────────────────────────────
#  G2 机器人 service2 控制服务 - 启动脚本
#
#  功能：
#    1. source /home/agi/app/gdk/scripts/env.sh /home/agi/app 加载 GDK 环境变量
#    2. 后台启动 /data/wxf/mbu0917/service2/main.py
#    3. 从 /data 工作目录启动 /data/wxf/mbu0917/runtime2/run.py
#    4. 以 /data/wxf/mbu0917/web 为根目录启动 HTTP :8002
#
#  运行目录：
#    service2 服务：/data/wxf/mbu0917/service2
#    runtime2 调试服务：/data
#    web 静态页：/data/wxf/mbu0917/web
#
#  日志：
#    logs/humanoid_server.log
#    logs/runtime_server.log
#    logs/web_server.log
#
#  用法：
#    sudo ./run.sh {start|stop|restart|status}
# ─────────────────────────────────────────────────────────

ACTION="${1:-start}"
case "$ACTION" in
    start|stop|restart|status) ;;
    *)
        echo "用法: $0 {start|stop|status|restart}" >&2
        exit 1
        ;;
esac

# 所有管理动作必须由 root 明确执行，避免脚本内部交互式 sudo。
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "[run.sh] ❌ $ACTION 必须以 root 运行；请使用: sudo $0 $ACTION" >&2
    exit 1
fi

RUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$RUN_DIR/.." && pwd)"
WEB_DIR="$PROJECT_DIR/web"
BACKEND_PATH="$RUN_DIR/main.py"
RUNTIME_PATH="$PROJECT_DIR/runtime2/run.py"
RUNTIME_WORK_DIR="/data"
cd "$RUN_DIR" || exit 1

# 加载 GDK 环境变量。必须显式传入 /home/agi/app，不能继承 run.sh 参数。
ENV_FILE="/home/agi/app/gdk/scripts/env.sh"
ENV_DIR="/home/agi/app"
if [ -f "$ENV_FILE" ]; then
    echo "[run.sh] 正在加载环境变量: source $ENV_FILE $ENV_DIR"
    source "$ENV_FILE" "$ENV_DIR"
    cd "$RUN_DIR" || exit 1
else
    echo "[run.sh] ⚠ 警告: 环境文件不存在: $ENV_FILE"
fi
export PYTHONPATH="/home/agi/.local/lib/python3.10/site-packages${PYTHONPATH:+:$PYTHONPATH}"

SERVICES=(
    "humanoid_server|$BACKEND_PATH"
    "runtime_server|$RUNTIME_PATH"
    "web_server|CMD:python3 -m http.server 8002|$WEB_DIR"
)
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

is_pid() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

process_alive() {
    local pid="$1" stat
    is_pid "$pid" || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    stat="$(ps -o stat= -p "$pid" 2>/dev/null)"
    [[ -n "$stat" && "$stat" != Z* ]]
}

is_python_argv0() {
    local base
    base="$(basename -- "$1")"
    [[ "$base" == python || "$base" == python[0-9]* ]]
}

is_backend_pid() {
    local pid="$1"
    local -a argv=()
    process_alive "$pid" || return 1
    mapfile -d '' -t argv < "/proc/$pid/cmdline" 2>/dev/null || return 1
    ((${#argv[@]} == 2)) || return 1
    is_python_argv0 "${argv[0]}" || return 1
    [[ "${argv[1]}" == "$BACKEND_PATH" ]]
}

is_runtime_pid() {
    local pid="$1" cwd
    local -a argv=()
    process_alive "$pid" || return 1
    mapfile -d '' -t argv < "/proc/$pid/cmdline" 2>/dev/null || return 1
    ((${#argv[@]} == 2)) || return 1
    is_python_argv0 "${argv[0]}" || return 1
    [[ "${argv[1]}" == "$RUNTIME_PATH" ]] || return 1
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null)"
    [[ "$cwd" == "$RUNTIME_WORK_DIR" ]]
}

is_web_pid() {
    local pid="$1" cwd
    local -a argv=()
    process_alive "$pid" || return 1
    mapfile -d '' -t argv < "/proc/$pid/cmdline" 2>/dev/null || return 1
    ((${#argv[@]} == 4)) || return 1
    is_python_argv0 "${argv[0]}" || return 1
    [[ "${argv[1]}" == "-m" && "${argv[2]}" == "http.server" && "${argv[3]}" == "8002" ]] || return 1
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null)"
    [[ "$cwd" == "$WEB_DIR" ]]
}

is_expected_pid() {
    local name="$1" pid="$2"
    case "$name" in
        humanoid_server) is_backend_pid "$pid" ;;
        runtime_server) is_runtime_pid "$pid" ;;
        web_server) is_web_pid "$pid" ;;
        *) return 1 ;;
    esac
}

leader_info() {
    local pid="$1" sid pgid
    read -r sid pgid < <(ps -o sid=,pgid= -p "$pid" 2>/dev/null)
    sid="${sid//[[:space:]]/}"
    pgid="${pgid//[[:space:]]/}"
    [[ "$sid" == "$pid" && "$pgid" == "$pid" ]]
}

port_listening() {
    ss -H -ltn "sport = :$1" 2>/dev/null | grep -q .
}

port_owned_by_pid() {
    local port="$1" pid="$2"
    ss -H -ltnp "sport = :$port" 2>/dev/null | grep -Fq "pid=$pid,"
}

show_log_tail() {
    local log_file="$1"
    echo "[run.sh] ── 日志尾部: $log_file ──" >&2
    tail -n 50 "$log_file" 2>/dev/null >&2 || true
}

terminate_expected_pid() {
    local name="$1" pid="$2" pgid target elapsed
    if ! is_expected_pid "$name" "$pid"; then
        echo "[run.sh] ⚠ 拒绝终止 PID=$pid：cmdline/cwd 不属于 $name" >&2
        return 1
    fi

    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null)"
    pgid="${pgid//[[:space:]]/}"
    if [[ "$pgid" == "$pid" ]]; then
        target="-$pgid"
        echo "[run.sh] 向 $name 进程组 PGID=$pgid 发送 TERM"
    else
        # 仅兼容清理由旧脚本产生、未独立成组的严格匹配孤儿；绝不终止其共享进程组。
        target="$pid"
        echo "[run.sh] ⚠ $name PID=$pid 不是进程组 leader，仅安全终止该严格匹配进程"
    fi

    kill -TERM -- "$target" 2>/dev/null || true
    for elapsed in {1..10}; do
        process_alive "$pid" || break
        sleep 1
    done
    if process_alive "$pid"; then
        echo "[run.sh] ⚠ $name 未在 10 秒内退出，向目标发送 KILL"
        kill -KILL -- "$target" 2>/dev/null || true
        sleep 1
    fi
    if process_alive "$pid"; then
        echo "[run.sh] ❌ $name PID=$pid 无法终止" >&2
        return 1
    fi
    echo "[run.sh] ✅ $name 已停止 (PID=$pid)"
}

cleanup_orphans() {
    local name="$1" tracked_pid="${2:-}" proc pid
    for proc in /proc/[0-9]*; do
        pid="${proc##*/}"
        [[ "$pid" == "$tracked_pid" ]] && continue
        if is_expected_pid "$name" "$pid"; then
            if [[ "$name" == web_server ]] && ! port_owned_by_pid 8002 "$pid"; then
                continue
            fi
            echo "[run.sh] ⚠ 发现严格匹配的 $name 孤儿进程 PID=$pid，正在清理"
            terminate_expected_pid "$name" "$pid" || return 1
        fi
    done
}

prepare_start() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}.pid" old_pid=""
    if [ -f "$pid_file" ]; then
        old_pid="$(<"$pid_file")"
        if is_pid "$old_pid" && process_alive "$old_pid"; then
            if is_expected_pid "$name" "$old_pid" && leader_info "$old_pid"; then
                if [[ "$name" != web_server ]] || port_owned_by_pid 8002 "$old_pid"; then
                    echo "[run.sh] ⚠ $name 已在运行且身份有效 (PID=$old_pid)，跳过"
                    return 2
                fi
            fi
            echo "[run.sh] ⚠ PID 文件身份无效或服务状态不完整，移除陈旧记录: $pid_file (PID=$old_pid)"
        else
            echo "[run.sh] 清理陈旧 PID 文件: $pid_file${old_pid:+ (PID=$old_pid)}"
        fi
        rm -f "$pid_file"
    fi

    cleanup_orphans "$name" || return 1
    if [[ "$name" == web_server ]] && port_listening 8002; then
        echo "[run.sh] ❌ 8002 已被非预期进程占用；为安全起见不会终止该占用者" >&2
        ss -H -ltnp "sport = :8002" 2>/dev/null >&2 || true
        return 1
    fi
    return 0
}

start_service() {
    local entry="$1"
    local name="${entry%%|*}" rest="${entry#*|}"
    local log_file="$LOG_DIR/${name}.log" pid_file="$LOG_DIR/${name}.pid"
    local pid attempt prep_rc

    # prepare_start 用返回码 2 表示“服务身份有效，跳过启动”。
    # 在全局 set -e 下必须放进 if 条件，否则返回 2 会让整个 run.sh
    # 提前退出，后续 web_server 永远没有机会启动。
    if prepare_start "$name"; then
        prep_rc=0
    else
        prep_rc=$?
    fi
    [[ "$prep_rc" -eq 2 ]] && return 0
    [[ "$prep_rc" -eq 0 ]] || return 1

    if [[ "$name" == runtime_server ]]; then
        if [ ! -f "$RUNTIME_PATH" ]; then
            echo "[run.sh] ❌ 文件不存在: $RUNTIME_PATH" >&2
            return 1
        fi
        if [ ! -d "$RUNTIME_WORK_DIR" ]; then
            echo "[run.sh] ❌ 工作目录不存在: $RUNTIME_WORK_DIR" >&2
            return 1
        fi
        (cd "$RUNTIME_WORK_DIR" && exec nohup setsid python3 "$RUNTIME_PATH" </dev/null >"$log_file" 2>&1) &
    elif [[ "$rest" == CMD:* ]]; then
        if [ ! -d "$WEB_DIR" ]; then
            echo "[run.sh] ❌ 工作目录不存在: $WEB_DIR" >&2
            return 1
        fi
        (cd "$WEB_DIR" && exec nohup setsid python3 -m http.server 8002 </dev/null >"$log_file" 2>&1) &
    else
        if [ ! -f "$BACKEND_PATH" ]; then
            echo "[run.sh] ❌ 文件不存在: $BACKEND_PATH" >&2
            return 1
        fi
        (cd "$RUN_DIR" && exec nohup setsid python3 "$BACKEND_PATH" </dev/null >"$log_file" 2>&1) &
    fi
    pid=$!
    printf '%s\n' "$pid" > "$pid_file"

    for attempt in {1..8}; do
        if is_expected_pid "$name" "$pid" && leader_info "$pid"; then
            if [[ "$name" != web_server ]] || port_owned_by_pid 8002 "$pid"; then
                echo "[run.sh] ✅ $name 已启动 (PID=$pid, SID/PGID=$pid, 日志=$log_file)"
                return 0
            fi
        fi
        process_alive "$pid" || break
        sleep 1
    done

    echo "[run.sh] ❌ $name 启动验证失败（进程身份、独立 SID/PGID 或 8002 监听不符合预期）" >&2
    show_log_tail "$log_file"
    if is_expected_pid "$name" "$pid"; then
        terminate_expected_pid "$name" "$pid" || true
    fi
    rm -f "$pid_file"
    return 1
}

stop_service() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}.pid" pid="" rc=0
    if [ -f "$pid_file" ]; then
        pid="$(<"$pid_file")"
        if is_pid "$pid" && process_alive "$pid"; then
            if is_expected_pid "$name" "$pid"; then
                terminate_expected_pid "$name" "$pid" || rc=1
            else
                echo "[run.sh] ⚠ $name PID 文件已陈旧/身份不符 (PID=$pid)，不会误杀该进程" >&2
            fi
        else
            echo "[run.sh] ⚠ $name PID 文件陈旧 (PID=${pid:-无效})"
        fi
        rm -f "$pid_file"
    else
        echo "[run.sh] ⚠ $name 无 PID 文件"
    fi
    cleanup_orphans "$name" || rc=1
    return "$rc"
}

status_service() {
    local name="$1"
    local pid_file="$LOG_DIR/${name}.pid" pid sid pgid
    if [ ! -f "$pid_file" ]; then
        echo "[run.sh] ○ $name 未启动（无 PID 文件）"
        return
    fi
    pid="$(<"$pid_file")"
    if ! is_pid "$pid" || ! process_alive "$pid"; then
        echo "[run.sh] ○ $name stale PID (PID=${pid:-无效}，进程不存在)"
        return
    fi
    if ! is_expected_pid "$name" "$pid"; then
        echo "[run.sh] ○ $name stale PID (PID=$pid，cmdline/cwd 身份不符)"
        return
    fi
    read -r sid pgid < <(ps -o sid=,pgid= -p "$pid" 2>/dev/null)
    sid="${sid//[[:space:]]/}"
    pgid="${pgid//[[:space:]]/}"
    if [[ "$name" == web_server ]] && ! port_owned_by_pid 8002 "$pid"; then
        echo "[run.sh] ◐ $name 进程身份有效但未持有 8002 (PID=$pid SID=$sid PGID=$pgid)"
    else
        echo "[run.sh] ● $name 身份有效 (PID=$pid SID=$sid PGID=$pgid)"
    fi
}

status_port() {
    local port="$1" label="$2"
    if port_listening "$port"; then
        echo "[run.sh] ● $label 端口 $port 正在监听"
        ss -H -ltnp "sport = :$port" 2>/dev/null | sed 's/^/           /'
    else
        echo "[run.sh] ○ $label 端口 $port 未监听"
    fi
}

case "$ACTION" in
    start)
        echo "════════════════════════════════════════════════════"
        echo "  Humanoid 机器人控制服务启动  $(date '+%Y-%m-%d %H:%M:%S')"
        echo "════════════════════════════════════════════════════"
        rc=0
        for svc in "${SERVICES[@]}"; do
            start_service "$svc" || rc=1
        done
        echo "────────────────────────────────────────────────────"
        echo "  日志目录: $LOG_DIR"
        echo "  查看状态: sudo ./run.sh status"
        echo "  停止服务: sudo ./run.sh stop"
        echo "════════════════════════════════════════════════════"
        exit "$rc"
        ;;
    stop)
        echo "正在停止所有服务..."
        rc=0
        for svc in "${SERVICES[@]}"; do
            stop_service "${svc%%|*}" || rc=1
        done
        echo "停止完成。"
        exit "$rc"
        ;;
    status)
        echo "════════════════════════════════════════════════════"
        echo "  Humanoid 服务状态  $(date '+%Y-%m-%d %H:%M:%S')"
        echo "════════════════════════════════════════════════════"
        for svc in "${SERVICES[@]}"; do
            status_service "${svc%%|*}"
        done
        status_port 8002 "Web"
        status_port 1883 "MQTT"
        status_port 9001 "MQTT WebSocket"
        ;;
    restart)
        "$0" stop || exit 1
        sleep 2
        exec "$0" start
        ;;
esac
