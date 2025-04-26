#!/bin/bash

# 检查 Docker 数据目录使用情况
DOCKER_DIR="/var/lib/docker"
USAGE=$(df -h $DOCKER_DIR | awk 'NR==2 {print $5}' | sed 's/%//')
THRESHOLD=80

if [ $USAGE -gt $THRESHOLD ]; then
    echo "警告: Docker 存储使用率超过 ${THRESHOLD}%"
    
    # 列出大型容器
    echo "最大的容器:"
    docker ps -s --format "{{.Names}}: {{.Size}}" | sort -k2 -h -r | head -n 5
    
    # 列出未使用的镜像
    echo "未使用的镜像:"
    docker images -f "dangling=true" -q
    
    # 可选：自动清理
    read -p "是否要清理未使用的资源? (y/n) " -n 1 -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker system prune -f
    fi
fi
