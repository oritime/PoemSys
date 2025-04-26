#!/bin/bash

# API服务器地址
API_URL="http://localhost:8000"
CONTAINER_NAME="test_container"
IMAGE_NAME="ubuntu20.04-cuda12.1-jupyter-v0.1"

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}启动测试...${NC}\n"

# 1. 获取访问令牌
echo "1. 获取访问令牌..."
TOKEN_RESPONSE=$(curl -s -X POST "${API_URL}/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123")

# 提取访问令牌
ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | grep -o '"access_token":"[^"]*' | grep -o '[^"]*$')

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}获取令牌失败${NC}"
    exit 1
fi

echo -e "${GREEN}获取令牌成功${NC}\n"

# 2. 创建容器
echo "2. 创建容器..."
CREATE_RESPONSE=$(curl -s -X POST "${API_URL}/containers/create" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     -H "Content-Type: application/json" \
     -d "{
           \"image\": \"${IMAGE_NAME}\",
           \"name\": \"${CONTAINER_NAME}\",
           \"config\": {
             \"root_password\": \"123456\",
             \"jupyter_token\": \"123456\"
           }
         }")

echo "创建容器响应："
echo $CREATE_RESPONSE | python3 -m json.tool
echo -e "\n等待5秒...\n"
sleep 5

# 3. 获取容器状态
echo "3. 获取容器状态..."
STATUS_RESPONSE=$(curl -s -X GET "${API_URL}/containers/${CONTAINER_NAME}" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "容器状态："
echo $STATUS_RESPONSE | python3 -m json.tool
echo -e "\n"

# 4. 停止容器
echo "4. 停止容器..."
STOP_RESPONSE=$(curl -s -X POST "${API_URL}/containers/${CONTAINER_NAME}/stop" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     -H "Content-Type: application/json" \
     -d "{
           \"commit_message\": \"测试停止容器\",
           \"keep_history\": 1
         }")

echo "停止容器响应："
echo $STOP_RESPONSE | python3 -m json.tool
echo -e "\n等待5秒...\n"
sleep 5

# 5. 检查容器状态
echo "5. 检查停止后的状态..."
STATUS_RESPONSE=$(curl -s -X GET "${API_URL}/containers/${CONTAINER_NAME}" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "容器状态："
echo $STATUS_RESPONSE | python3 -m json.tool
echo -e "\n"

# 6. 启动容器
echo "6. 重新启动容器..."
START_RESPONSE=$(curl -s -X POST "${API_URL}/containers/${CONTAINER_NAME}/start" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     -H "Content-Type: application/json" \
     -d "{}")

echo "启动容器响应："
echo $START_RESPONSE | python3 -m json.tool
echo -e "\n等待5秒...\n"
sleep 5

# 7. 再次检查状态
echo "7. 检查启动后的状态..."
STATUS_RESPONSE=$(curl -s -X GET "${API_URL}/containers/${CONTAINER_NAME}" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "容器状态："
echo $STATUS_RESPONSE | python3 -m json.tool
echo -e "\n"

# 8. 删除容器
echo "8. 删除容器..."
DELETE_RESPONSE=$(curl -s -X DELETE "${API_URL}/containers/${CONTAINER_NAME}" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}")

echo "删除容器响应："
echo $DELETE_RESPONSE | python3 -m json.tool
echo -e "\n"

echo -e "${GREEN}测试完成${NC}" 