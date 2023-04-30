#!/bin/bash


# 检查程序是否启动
function check_process {
    # 根据进程名查询进程ID，如果进程存在返回0，否则返回1
    if ps aux | grep -v grep | grep "gunicorn -w 10 -b 0.0.0.0:5000 main:app" > /dev/null; then
        return 0
    else
        return 1
    fi
}

# 启动程序
function start_process {
    # 切换到虚拟环境
    source venv/bin/activate
    # 启动程序
    gunicorn -w 10 -b 0.0.0.0:5000 main:app --timeout 120 >> gunicorn.log 2>&1 &
}

# 每隔 15 秒检查一次程序是否启动
while true; do
    check_process
    if [ $? -ne 0 ]; then
        echo "Process not running, starting process..."
        start_process
    fi
    sleep 15
done