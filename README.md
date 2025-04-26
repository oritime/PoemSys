# 诗云PoemSys 1.0 - Docker 容器管理系统

PoemSys 是一个基于 Python 的 Docker 容器生命周期管理系统，集成了 NPS（NProxy Server）动态隧道管理功能，专为 AI/ML 研发环境设计。系统提供完整的 RESTful API 接口，支持容器的创建、启动、停止、删除以及快照管理等核心功能。

## 系统特性

- **容器生命周期管理**：创建、启动、停止和删除 Docker 容器
- **快照功能**：支持容器状态快照创建与恢复
- **动态端口管理**：通过 NPS 实现动态端口分配和管理
- **服务隧道**：自动为容器内的 SSH、Jupyter 和应用服务创建外部访问隧道
- **GPU 支持**：内置对 NVIDIA GPU 的访问支持
- **持久化状态**：容器状态、镜像映射和隧道信息持久化
- **RESTful API**：完整的 HTTP API 接口，支持所有管理功能

## 环境要求

- Python 3.7+ 
- Docker 引擎
- NVIDIA 容器运行时（用于 GPU 支持）
- NPS 服务器（用于隧道管理）

## 安装步骤

1. **克隆代码仓库**

```bash
git clone https://github.com/oritime/poemsys.git
cd poemsys
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置系统**

编辑 `config.json` 文件，设置 Docker、NPS 和系统参数：

```json
{
  "persistence": {
    "container_state_file": "./data/container_tunnels.json",
    "image_mapping_file": "./data/container_images.json"
  },
  "container_config": {
    "ssh": {
      "port": 22,
      "root_password": "default_password"
    },
    "jupyter": {
      "port": 8888,
      "token": "",
      "base_url": "/jupyter",
      "notebook_dir": "/root"
    },
    "app": {
      "port": 5000
    }
  },
  "resource_limits": {
    "memory": "8g",
    "cpuset_cpus": "0-3"
  },
  "container_snapshots": {
    "max_history": 5
  },
  "volumes": {
    "/path/on/host": {"bind": "/path/in/container", "mode": "rw"}
  },
  "uvicorn": {
    "host": "0.0.0.0",
    "port": 8000,
    "reload": false
  },
  "auth": {
    "token_expire_minutes": 1440,
    "secret_key": "your-secret-key-here",
    "algorithm": "HS256",
    "users": {
      "admin": "password"
    }
  }
}
```

4. **确保 NPS 服务可用**

系统需要连接到 NPS 服务来管理隧道。确保您已按 NPS 文档配置了服务器和客户端。

## 运行系统

启动 API 服务器：

```bash
python api_server.py
```

系统默认在端口 8000 启动。可通过 `config.json` 的 `uvicorn` 部分修改主机和端口。

## API 接口文档

### 认证

所有 API 调用需要通过 Bearer 令牌认证：

```bash
# 获取认证令牌
curl -X POST "http://localhost:8000/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=password"
     
# 保存token到环境变量中（方便使用）
export TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 容器管理

#### 创建容器

```bash
curl -X POST "http://localhost:8000/containers" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "image": "nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04",
       "name": "container-name",
       "config": {
         "root_password": "your-password",
         "jupyter_token": "your-token"
       }
     }'
```

#### 停止容器

```bash
curl -X POST "http://localhost:8000/containers/container-name/stop" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

#### 启动容器

```bash
curl -X POST "http://localhost:8000/containers/container-name/start" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

#### 删除容器

```bash
curl -X DELETE "http://localhost:8000/containers/container-name?remove_snapshots=false" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

#### 查看容器状态

```bash
curl -X GET "http://localhost:8000/containers/container-name" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

#### 列出所有容器

```bash
curl -X GET "http://localhost:8000/containers" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

### 快照管理

#### 创建快照

```bash
curl -X POST "http://localhost:8000/containers/container-name/snapshots" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "commit_message": "Snapshot description"
     }'
```

#### 从快照启动

```bash
curl -X POST "http://localhost:8000/containers/container-name/start_from_snapshot" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version_tag": "v1_20240414_123456"
     }'
```

#### 列出容器快照

```bash
curl -X GET "http://localhost:8000/containers/container-name/snapshots" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

#### 列出所有快照

```bash
curl -X GET "http://localhost:8000/snapshots" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

## 使用说明

### 容器创建与访问

1. 使用 API 创建容器后，系统会返回分配的端口信息：

```json
{
  "success": true,
  "message": "Container 'my-container' created successfully",
  "data": {
    "name": "my-container",
    "public_ports": {
      "ssh_port": 12345,
      "jupyter_port": 23456,
      "app_port": 34567
    },
    "credentials": {
      "ssh_password": "your-password",
      "jupyter_token": "your-token"
    }
  }
}
```

2. 通过返回的端口访问容器服务：

   - **SSH 访问**：`ssh root@your-server -p 12345`（密码为配置的 `root_password`）
   - **Jupyter 访问**：浏览器打开 `http://your-server:23456/jupyter/lab?token=your-token`
   - **应用服务**：浏览器或 API 客户端访问 `http://your-server:34567`

### 端口说明

系统使用 NPS 实现动态端口管理，每个容器服务映射到不同的公网端口：

- 当容器停止再启动时，端口会被重新分配
- 服务隧道信息会持久化存储，但仅对正在运行的容器有效

### 备份与快照

1. 创建容器快照前，系统会先停止容器，然后提交为 Docker 镜像
2. 每个容器的快照历史会被保留（默认为 5 个版本）
3. 超出数量限制的旧快照会被自动清理

## 架构说明

系统由以下主要组件构成：

- **DockerContainerManager**：核心容器管理类，负责容器生命周期和状态管理
- **DynamicTunnelManager**：隧道管理类，负责与 NPS 交互创建和删除端口隧道
- **FastAPI 服务器**：提供 RESTful API 接口，处理客户端请求

数据持久化通过 JSON 文件实现：
- `container_tunnels.json`：存储容器隧道映射信息
- `container_images.json`：存储容器镜像和快照历史信息

## 注意事项

- 容器停止后再启动，端口会重新分配
- 确保 Docker 守护进程正常运行且当前用户有权限访问
- 对 GPU 功能的支持需要正确安装 NVIDIA 容器运行时
- 生产环境建议配置更安全的认证方式

## 故障排除

如遇系统问题，请检查：

1. Docker 守护进程是否正常运行：`docker ps`
2. NPS 客户端连接状态：检查 NPS 客户端日志
3. API 服务器日志：启动 `api_server.py` 时的控制台输出
4. 容器内部日志：`docker logs <container-name>`
5. Jupyter 日志：容器内的 `/var/log/jupyter.log`

## 常见问题

### Docker 容器 IP 地址重合问题

当多个 Docker 容器使用相同子网导致 IP 地址重合时，可能会引起容器无法正常通信、服务冲突等问题。以下是解决方案：

#### 方案一：使用自定义网络

为不同容器组创建不同的自定义网络：

```bash
# 创建自定义网络
docker network create --subnet=172.20.0.0/16 network1
docker network create --subnet=172.30.0.0/16 network2

# 修改 container_manager.py 中的网络配置
```

在 `ContainerManager` 类中的 `create_container` 方法中添加网络配置参数：

```python
container = self.client.containers.run(
    image,
    # ... 其他参数
    network="network1",  # 指定自定义网络
    # 可选：固定 IP 地址
    # ip="172.20.0.10",
)
```

#### 方案二：为每个容器指定唯一的 IP 地址

在 `config.json` 中添加网络配置部分：

```json
"network_config": {
  "default_network": "custom_net",
  "subnet": "172.20.0.0/16",
  "ip_allocation": {
    "strategy": "sequential",
    "start_ip": "172.20.0.10"
  }
}
```

然后修改容器创建逻辑，为每个容器分配唯一 IP：

```python
# 在 ContainerManager 类中添加 IP 地址管理方法
def _allocate_container_ip(self):
    """分配唯一的容器 IP 地址"""
    # 实现 IP 地址分配逻辑
    return next_available_ip

# 创建容器时使用分配的 IP
network_config = {
    "EndpointsConfig": {
        self.config["network_config"]["default_network"]: {
            "IPAMConfig": {"IPv4Address": allocated_ip}
        }
    }
}
container = self.client.containers.run(
    image,
    # ... 其他参数
    network_mode=self.config["network_config"]["default_network"],
    networking_config=network_config
)
```

#### 方案三：使用网络命名空间隔离

对于需要完全网络隔离的容器，可以使用 `None` 网络模式，然后通过 NPS 隧道提供服务访问：

```python
container = self.client.containers.run(
    image,
    # ... 其他参数
    network_mode="none",  # 完全隔离网络
)
```

这种方式下，容器没有网络连接，只能通过 NPS 隧道访问容器内的服务。需要注意以下几点：

1. **NPS 客户端连接**：
   - 当容器使用 `network_mode="none"` 时，NPS 客户端会使用 `127.0.0.1`（localhost）作为目标地址
   - 这是因为容器内服务实际上是通过 Docker 的 Unix 域套接字转发到宿主机的
   - NPS 配置示例：
     ```json
     {
       "target": "127.0.0.1:container_port",
       "host_header": "container_name",
       "local_network": "unix"
     }
     ```

2. **端口映射机制**：
   - Docker 会在宿主机上创建一个 Unix 域套接字
   - 容器内的服务通过这个套接字与宿主机通信
   - NPS 通过监听这个套接字来转发流量

3. **配置调整**：
   ```python
   # 在 DynamicTunnelManager 中处理 network_mode="none" 的情况
   def create_tunnel(self, container_name, container_port, service_type):
       if container.attrs['HostConfig']['NetworkMode'] == 'none':
           # 使用 Unix 域套接字方式
           target = f"127.0.0.1:{container_port}"
           socket_path = f"/var/run/docker/{container_name}_{service_type}.sock"
           
           # 创建 Unix 域套接字转发
           self._create_socket_forward(socket_path, container_port)
           
           # 配置 NPS 隧道
           tunnel_config = {
               "target": target,
               "host_header": container_name,
               "local_network": "unix",
               "socket_path": socket_path
           }
       else:
           # 常规网络模式的处理...
           pass
   ```

4. **安全性提升**：
   - 容器完全隔离，没有任何网络访问能力
   - 所有通信都通过 Unix 域套接字进行，更安全
   - 避免了任何可能的 IP 冲突问题

5. **限制**：
   - 容器间无法直接通信
   - 所有网络访问必须通过 NPS 隧道
   - 需要额外的 Unix 域套接字管理

### 如何验证和解决 IP 冲突

如果怀疑存在 IP 冲突，可以采取以下步骤检查和解决：

1. **检查当前容器网络信息**：
   ```bash
   docker network inspect bridge  # 检查默认桥接网络
   ```

2. **检查容器内部网络配置**：
   ```bash
   docker exec container-name ip addr show
   ```

3. **查看容器间网络连接**：
   ```bash
   docker exec container-name ping other-container-ip
   ```

4. **修改现有容器网络**：
   ```bash
   # 停止容器
   docker stop container-name
   
   # 将容器连接到新网络
   docker network connect --ip 172.20.0.10 custom_network container-name
   
   # 断开旧网络连接
   docker network disconnect bridge container-name
   
   # 启动容器
   docker start container-name
   ```

### 更新系统以防止 IP 冲突

为防止 IP 冲突问题，我们已经在 PoemSys 1.3 中添加了以下功能：

1. 容器创建时自动分配唯一网络配置
2. 容器启动前检查 IP 冲突情况
3. 网络资源跟踪和回收

如需启用这些功能，请确保在 `config.json` 中配置了 `network_config` 部分。

## 开发与扩展

系统设计具有良好的可扩展性：

- 容器管理逻辑和隧道管理逻辑分离
- 核心类采用模块化设计，便于扩展和测试
- API 接口使用 Pydantic 模型进行验证和文档生成

若需添加新功能，可专注于以下文件：
- `container_manager.py`：容器管理核心逻辑
- `dynamic_tunnel_manager.py`：隧道管理核心逻辑
- `api_server.py`：API 接口定义和请求处理 