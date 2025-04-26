#!/usr/bin/env python3
import docker
import docker.types
import threading
import json
import os
import time
import socket
from typing import Dict, Tuple, Optional, List, Any
from datetime import datetime # 确保导入

# 导入 DynamicTunnelManager
from dynamic_tunnel_manager import DynamicTunnelManager

def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        # 保留: 配置加载错误
        print(f"[ContainerManager] Error: 加载配置文件失败 ({config_path}): {e}") 
        return None

# 全局配置
CONFIG = load_config()
if not CONFIG:
    raise RuntimeError("加载配置失败，请检查 config.json")

# 移除 PortPoolManager 类
# class PortPoolManager:
#     ...

class DockerContainerManager:
    """Docker容器生命周期管理 (已集成动态隧道管理)"""

    def __init__(self, tunnel_manager: DynamicTunnelManager):
        """
        初始化 DockerContainerManager

        Args:
            tunnel_manager: 一个 DynamicTunnelManager 实例
        """
        docker_connected = False
        connection_errors = []
        # 尝试不同的连接方式
        urls_to_try = ['tcp://localhost:2375', 'tcp://localhost:2376', 'unix://var/run/docker.sock']
        for url in urls_to_try:
            try:
                # print(f"[ContainerManager Debug] Attempting to connect to Docker at {url}...") # 注释掉
                self.client = docker.DockerClient(base_url=url)
                self.client.ping() # 确保连接成功
                # 保留: 连接成功信息
                print(f"[ContainerManager] 成功连接到 Docker Daemon: {url}") 
                docker_connected = True
                break
            except Exception as e:
                # print(f"[ContainerManager Debug] Connection to {url} failed: {e}") # 注释掉
                connection_errors.append(f"{url}: {e}")
        
        if not docker_connected:
            error_details = ' / '.join(connection_errors)
            # 保留: 连接失败错误
            raise RuntimeError(f"[ContainerManager] Error: 无法连接到 Docker 守护进程。尝试的地址: {error_details}. "
                               f"请确保 Docker Daemon 正在运行并配置了正确的访问权限/端口。")
        
        self.tunnel_manager = tunnel_manager
        
        # 状态变量初始化
        self.container_images = {}
        self.image_history = {}
        self.max_history_per_container = CONFIG.get('container_snapshots', {}).get('max_history', 1)
        self.container_tunnels: Dict[str, Dict[str, Any]] = {}
        
        # 加载持久化状态
        self._load_container_images()
        self._load_container_states()
        # 保留: 初始化完成信息
        print("[ContainerManager] 初始化完成，已加载状态。") 

    def _load_container_images(self):
        """从文件加载容器-镜像映射关系和历史记录"""
        image_file = CONFIG['persistence']['image_mapping_file']
        if os.path.exists(image_file):
            try:
                with open(image_file, 'r') as f:
                    data = json.load(f)
                    self.container_images = data.get('current', {})
                    self.image_history = data.get('history', {})
                    # print(f"[ContainerManager Debug] Loaded container images from {image_file}") # 注释掉
            except Exception as e:
                # 保留: 加载失败警告
                print(f"[ContainerManager] Warning: 加载容器镜像映射失败 ({image_file}): {e}") 

    def _save_container_images(self):
        """保存容器-镜像映射关系和历史记录到文件"""
        image_file = CONFIG['persistence']['image_mapping_file']
        try:
            os.makedirs(os.path.dirname(image_file), exist_ok=True)
            with open(image_file, 'w') as f:
                json.dump({
                    'current': self.container_images,
                    'history': self.image_history
                }, f, indent=2)
            # print(f"[ContainerManager Debug] Saved container images to {image_file}") # 注释掉
        except Exception as e:
            # 保留: 保存失败警告
            print(f"[ContainerManager] Warning: 保存容器镜像映射失败 ({image_file}): {e}") 
            
    def _load_container_states(self):
        """从文件加载容器隧道状态"""
        state_file = CONFIG['persistence']['container_state_file']
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    self.container_tunnels = json.load(f)
                    # print(f"[ContainerManager Debug] Loaded container states from {state_file}") # 注释掉
            except Exception as e:
                # 保留: 加载失败警告
                print(f"[ContainerManager] Warning: 加载容器隧道状态失败 ({state_file}): {e}") 
                self.container_tunnels = {}

    def _save_container_states(self):
        """保存容器隧道状态到文件"""
        state_file = CONFIG['persistence']['container_state_file']
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, 'w') as f:
                json.dump(self.container_tunnels, f, indent=2)
            # print(f"[ContainerManager Debug] Saved container states to {state_file}") # 注释掉
        except Exception as e:
            # 保留: 保存失败警告
            print(f"[ContainerManager] Warning: 保存容器隧道状态失败 ({state_file}): {e}") 

    def _get_container_ip(self, container_name_or_id: str) -> Optional[str]:
        """获取运行中容器的IP地址"""
        try:
            container = self.client.containers.get(container_name_or_id)
            container.reload()
            networks = container.attrs['NetworkSettings']['Networks']
            if networks:
                first_network_name = list(networks.keys())[0]
                ip_address = networks[first_network_name]['IPAddress']
                if ip_address:
                    return ip_address
            # 保留: 未找到 IP 警告
            print(f"[ContainerManager] Warning: 未找到容器 {container_name_or_id} 的 IP 地址") 
            return None
        except docker.errors.NotFound:
            # 保留: 容器不存在错误
            print(f"[ContainerManager] Error: 尝试获取 IP 时，容器 {container_name_or_id} 未找到。") 
            return None
        except Exception as e:
            # 保留: 获取 IP 异常错误
            print(f"[ContainerManager] Error: 获取容器 {container_name_or_id} 的 IP 地址时出错: {e}") 
            return None

    def _cleanup_old_images(self, container_name: str):
        """清理旧的镜像，只保留最近的几个版本"""
        if container_name not in self.image_history:
            return

        history = self.image_history[container_name]
        max_history = max(1, self.max_history_per_container)
        if len(history) > max_history:
            images_to_remove = history[:-max_history]
            # print(f"[ContainerManager Debug] Cleaning up old images for {container_name}: {images_to_remove}") # 注释掉
            removed_count = 0
            failed_count = 0
            for image_tag in images_to_remove:
                try:
                    self.client.images.get(image_tag) # 检查是否存在
                    self.client.images.remove(image_tag, force=True)
                    # print(f"[ContainerManager] Removed old image: {image_tag}") # 注释掉
                    removed_count += 1
                except docker.errors.ImageNotFound:
                    # print(f"[ContainerManager Debug] Old image {image_tag} already removed.") # 注释掉
                    pass # 不算失败
                except docker.errors.APIError as e:
                    failed_count += 1
                    if 'image is being used by stopped container' in str(e) or 'image is referenced in multiple repositories' in str(e):
                         # print(f"[ContainerManager] Info: Cannot remove image {image_tag} as it might be in use or referenced elsewhere.") # 注释掉
                         pass # 这种情况可以容忍
                    else:
                        # 保留: 删除旧镜像 API 错误
                        print(f"[ContainerManager] Warning: 删除旧镜像失败 {image_tag} (API Error): {e}") 
                except Exception as e:
                    failed_count += 1
                    # 保留: 删除旧镜像未知错误
                    print(f"[ContainerManager] Warning: 删除旧镜像时发生未知错误 {image_tag}: {e}") 
            
            if removed_count > 0 or failed_count > 0:
                 # 保留: 清理结果信息
                 print(f"[ContainerManager] 旧镜像清理完成 ({container_name}): 成功移除 {removed_count} 个, 失败 {failed_count} 个。") 
            # 更新历史记录
            self.image_history[container_name] = history[-max_history:]
            self._save_container_images()

    def create_container(self, image: str, name: str, container_config: dict = None) -> Optional[Dict[str, int]]:
        """创建并启动容器，并为其服务创建NPS隧道"""
        # print(f"[ContainerManager Debug] Request to create container: Name={name}, Image={image}") # 注释掉
        try:
            existing_container = self.client.containers.get(name)
            if existing_container:
                # 保留: 容器已存在错误
                print(f"[ContainerManager] Error: 容器 '{name}' 已存在。")
                return self.get_container_ports(name)
        except docker.errors.NotFound:
            pass # Ok
        except Exception as e:
            # 保留: 检查存在性时出错
            print(f"[ContainerManager] Error: 检查容器 '{name}' 是否存在时出错: {e}")
            return None

        # 配置合并逻辑
        default_config = CONFIG.get('container_config', {}) # 使用 .get 以防 key 不存在
        if container_config is None:
            container_config = {}
        
        ssh_config = default_config.get('ssh', {})
        jupyter_config = default_config.get('jupyter', {})
        app_config = default_config.get('app', {})

        # --- Restore priority logic for notebook_dir --- 
        # 1. Check runtime config ('jupyter_dir')
        # 2. Check config.json ('container_config.jupyter.notebook_dir')
        # 3. Default to '/root'
        notebook_dir = container_config.get('jupyter_dir', 
                        jupyter_config.get('notebook_dir', '/root'))
        # Restore logging to show the source of the notebook_dir
        if 'jupyter_dir' in container_config:
            print(f"[ContainerManager] Info: 容器 '{name}' 将使用 Jupyter 根目录: '{notebook_dir}' (来自运行时参数 'jupyter_dir')")
        elif 'notebook_dir' in jupyter_config:
             print(f"[ContainerManager] Info: 容器 '{name}' 将使用 Jupyter 根目录: '{notebook_dir}' (来自 config.json)")
        else:
             print(f"[ContainerManager] Info: 容器 '{name}' 将使用 Jupyter 根目录: '{notebook_dir}' (默认值)")
        
        config = {
            'ssh': {
                'port': ssh_config.get('port', 22),
                'root_password': container_config.get('root_password', ssh_config.get('root_password', 'password'))
            },
            'jupyter': {
                'port': jupyter_config.get('port', 8888),
                'token': container_config.get('jupyter_token', jupyter_config.get('token', '')),
                'base_url': container_config.get('jupyter_base_url', jupyter_config.get('base_url', '/jupyter')),
                'notebook_dir': notebook_dir # Use the resolved notebook_dir
            },
            'app': {
                'port': app_config.get('port', 5000)
            }
        }

        notebook_dir_setup = f"mkdir -p {config['jupyter']['notebook_dir']} && chmod -R 777 {config['jupyter']['notebook_dir']}"
        # Corrected start_command f-string definition
        start_command = f"""
set -e
# Prepare SSH environment
mkdir -p /var/run/sshd
echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config
echo 'root:{config['ssh']['root_password']}' | chpasswd
ssh-keygen -A
/usr/sbin/sshd -D &
echo "SSH service started"

# Prepare and start Jupyter Lab
{notebook_dir_setup}
source /root/miniconda3/bin/activate || echo "Miniconda not found or activation failed"
echo "Starting Jupyter Lab..."
jupyter lab \\
    --ip=0.0.0.0 \\
    --port={config['jupyter']['port']} \\
    --allow-root \\
    --no-browser \\
    --ServerApp.token='{config['jupyter']['token']}' \\
    --notebook-dir='{config['jupyter']['notebook_dir']}' \\
    --ServerApp.base_url='{config['jupyter']['base_url']}' &> /var/log/jupyter.log &
echo "Jupyter Lab started in background, logs at /var/log/jupyter.log"

echo "Container setup complete. Keeping container alive."
tail -f /dev/null
"""

        # Define environment variables
        env_list = {
            'JUPYTER_PORT': str(config['jupyter']['port']),
            'JUPYTER_TOKEN': config['jupyter']['token'],
            'JUPYTER_BASE_URL': config['jupyter']['base_url'],
            'ROOT_PASSWORD': config['ssh']['root_password']
        }

        # Define volume configuration - removed all mounts
        volume_config = {}

        # Define working directory
        working_dir = config['jupyter']['notebook_dir']

        # Define resource configuration
        resource_config = {
            'mem_limit': '4g',
            'memswap_limit': '4g',
            'cpu_period': 100000,
            'cpu_quota': 200000,
            'shm_size': '1g'
        }

        try:
            # 添加 GPU 支持参数
            device_requests = [
                docker.types.DeviceRequest(device_ids=['0'], capabilities=[['gpu']])
            ]

            # 设置运行时为 nvidia
            runtime = 'nvidia'

            # 定义端口映射
            ports = {
                '22/tcp': None,    # SSH
                '8888/tcp': None,  # Jupyter
                '5000/tcp': None   # App
            }

            # 修正 containers.run 调用，确保参数格式正确
            container = self.client.containers.run(
                image=image,
                name=name,
                hostname=CONFIG.get('container_config', {}).get('hostname', 'origincloud'),  # 从配置文件获取主机名，默认为 origincloud
                detach=True,
                tty=True,
                stdin_open=True,
                restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
                command=["/bin/bash", "-c", start_command],
                environment=env_list,
                volumes=volume_config,
                working_dir=working_dir,
                runtime=runtime,
                device_requests=device_requests,
                ports=ports,
                **resource_config
            )
            print(f"[ContainerManager] 容器 '{name}' 创建成功 (ID: {container.short_id})，已请求 GPU 访问。")

            # 更新状态并保存
            self.container_images[name] = image
            if name not in self.image_history: self.image_history[name] = []
            self.image_history[name].append(image)
            self._save_container_images()

            # 等待并获取 IP
            time.sleep(5)
            container_ip = self._get_container_ip(name)
            if not container_ip:
                print(f"[ContainerManager] Error: 无法获取容器 IP，正在尝试清理...")
                try:
                    container.stop(timeout=5)
                    container.remove()
                    print(f"[ContainerManager] Info: 失败的容器 '{name}' 已清理。")
                except Exception as rm_err:
                    print(f"[ContainerManager] Warning: 清理失败的容器 '{name}' 时出错: {rm_err}")
                return None

            # 创建隧道逻辑
            created_tunnels = {}
            ports_info = {}
            services_to_tunnel = {
                "ssh": config['ssh']['port'],
                "jupyter": config['jupyter']['port'],
                "app": config['app']['port']
            }
            tunnel_creation_failed = False
            failed_services = []

            for service_name, internal_port in services_to_tunnel.items():
                target = f"{container_ip}:{internal_port}"
                remark = f"Container:{name}_Service:{service_name}"
                tunnel_info = self.tunnel_manager.create_tunnel(
                    target=target,
                    service_name=service_name,
                    remark=remark
                )

                if tunnel_info and tunnel_info.get("port") is not None:
                    created_tunnels[service_name] = tunnel_info
                    ports_info[f"{service_name}_port"] = tunnel_info["port"]
                else:
                    print(f"[ContainerManager] Error: 为容器 '{name}' 的服务 '{service_name}' 创建隧道失败。")
                    tunnel_creation_failed = True
                    failed_services.append(service_name)
                    if service_name == 'ssh':
                        break

            if tunnel_creation_failed:
                print(f"[ContainerManager] Error: 由于服务 {failed_services} 的隧道创建失败，正在回滚容器 '{name}'...")
                for service, info in created_tunnels.items():
                    if info.get("tunnel_id") is not None:
                        self.tunnel_manager.delete_tunnel(info["tunnel_id"])
                try:
                    container.stop(timeout=5)
                    container.remove()
                except Exception as clean_err:
                    print(f"[ContainerManager] Warning: 回滚清理容器 '{name}' 时出错: {clean_err}")
                if name in self.container_images: del self.container_images[name]
                if name in self.image_history: del self.image_history[name]
                self._save_container_images()
                if name in self.container_tunnels: del self.container_tunnels[name]
                self._save_container_states()
                return None

            self.container_tunnels[name] = created_tunnels
            self._save_container_states()
            print(f"[ContainerManager] 容器 '{name}' 及关联隧道创建完成。")
            return ports_info

        except docker.errors.ImageNotFound:
            print(f"[ContainerManager] Error: 镜像 '{image}' 未找到。")
            return None
        except docker.errors.APIError as e:
            print(f"[ContainerManager] Error: 创建容器 '{name}' 时出现 Docker API 错误: {e}")
            if "container with name \\\"/{name}\\\" is already in use" in str(e):
                 print(f"[ContainerManager] Info: 容器 '{name}' 已存在。将返回现有端口。")
                 return self.get_container_ports(name)
            return None
        except Exception as e:
            print(f"[ContainerManager] Error: 创建容器 '{name}' 时发生意外错误: {e}")
            try:
                cont = self.client.containers.get(name)
                cont.stop()
                cont.remove()
            except: pass
            return None

    def get_container_ports(self, name: str) -> Optional[Dict[str, int]]:
        """获取容器映射的公网端口 (主要从状态文件获取)"""
        if name in self.container_tunnels:
            ports_info = {}
            for service, tunnel_data in self.container_tunnels[name].items():
                if tunnel_data and 'port' in tunnel_data:
                    ports_info[f"{service}_port"] = tunnel_data['port']
            return ports_info if ports_info else None
        # print(f"[ContainerManager Debug] No tunnel info found in state for {name}") # 注释掉
        return None

    def stop_container(self, name: str) -> bool:
        """停止容器并删除其关联的NPS隧道"""
        container = None
        try:
            container = self.client.containers.get(name)
            # print(f"[ContainerManager Debug] Stopping container {name}...") # 注释掉
            container.stop(timeout=10)
            # 保留: 停止成功信息
            print(f"[ContainerManager] 容器 '{name}' 已停止。") 
        except docker.errors.NotFound:
            # 保留: 容器不存在警告 (但仍需清理隧道)
            print(f"[ContainerManager] Warning: 尝试停止时，容器 '{name}' 未找到。") 
            # 继续执行下面的隧道清理逻辑
        except docker.errors.APIError as e:
            # 保留: 停止 API 错误
            print(f"[ContainerManager] Error: 停止容器 '{name}' 时出错 (API Error): {e}") 
            # 即使停止失败，也尝试清理隧道
        except Exception as e:
            # 保留: 停止未知错误
            print(f"[ContainerManager] Error: 停止容器 '{name}' 时发生意外错误: {e}") 
            # 即使停止失败，也尝试清理隧道

        # 清理隧道逻辑 (无论容器是否找到或停止成功，都尝试清理)
        tunnel_cleanup_success = True
        if name in self.container_tunnels:
            tunnels_to_delete = self.container_tunnels.pop(name) # 直接从字典移除
            self._save_container_states() # 更新状态文件
            # print(f"[ContainerManager Debug] Deleting tunnels for container {name}...") # 注释掉
            deleted_count = 0
            failed_count = 0
            for service, tunnel_info in tunnels_to_delete.items():
                if tunnel_info and tunnel_info.get("tunnel_id") is not None:
                    tunnel_id = tunnel_info["tunnel_id"]
                    # print(f"[ContainerManager Debug] Deleting tunnel {tunnel_id} for service {service}...") # 注释掉
                    if self.tunnel_manager.delete_tunnel(tunnel_id):
                        # print(f"[ContainerManager Debug] Tunnel {tunnel_id} deleted.") # 注释掉
                        deleted_count += 1
                    else:
                        # 隧道删除失败信息已由 tunnel_manager 打印
                        print(f"[ContainerManager] Warning: 删除服务 '{service}' (Tunnel ID: {tunnel_id}) 的隧道失败。") 
                        tunnel_cleanup_success = False
                        failed_count += 1
                else:
                     # 保留: 无 Tunnel ID 警告
                     print(f"[ContainerManager] Warning: 无法删除服务 '{service}' 的隧道，因为状态中缺少 tunnel_id (容器: {name})。") 
            if deleted_count > 0 or failed_count > 0:
                 # 保留: 隧道清理结果
                 print(f"[ContainerManager] 隧道清理完成 ({name}): 成功删除 {deleted_count} 个, 失败 {failed_count} 个。") 
        else:
            # print(f"[ContainerManager Debug] No tunnel information found in state for container {name}.") # 注释掉
            pass # 没有隧道记录，无需清理
            
        # 返回操作是否成功 (容器成功停止或不存在，且隧道清理无致命错误)
        # 容器停止成功或不存在，并且隧道清理没有失败，才算完全成功
        return (container is not None or not docker.errors.NotFound) and tunnel_cleanup_success 

    def start_container(self, name: str) -> Optional[Dict[str, int]]:
        """启动已停止的容器，并重新创建NPS隧道"""
        try:
            container = self.client.containers.get(name)
            if container.status == 'running':
                 # 保留: 已运行信息
                 print(f"[ContainerManager] Info: 容器 '{name}' 已在运行中。尝试获取现有端口...") 
                 return self.get_container_ports(name)
                 
            # print(f"[ContainerManager Debug] Starting container {name}...") # 注释掉
            container.start()
            # 保留: 启动成功信息
            print(f"[ContainerManager] 容器 '{name}' 已启动。") 

            # print(f"[ContainerManager Debug] Waiting for container {name} network...") # 注释掉
            time.sleep(5) 
            container_ip = self._get_container_ip(name)
            if not container_ip:
                # 错误已在 _get_container_ip 打印
                print(f"[ContainerManager] Error: 无法获取已启动容器 '{name}' 的 IP。尝试停止...") 
                try: container.stop(timeout=5) 
                except: pass
                return None
            
            # print(f"[ContainerManager Debug] Container {name} IP: {container_ip}. Re-creating tunnels...") # 注释掉

            # 获取内部端口配置
            config = CONFIG['container_config']
            services_to_tunnel = {
                "ssh": config['ssh'].get('port', 22),
                "jupyter": config['jupyter'].get('port', 8888),
                "app": config['app'].get('port', 5000)
            }
            
            # 重新创建隧道
            created_tunnels = {}
            ports_info = {}
            tunnel_creation_failed = False
            failed_services = []
            # print(f"[ContainerManager Debug] Re-creating tunnels for container {name}...") # 注释掉
            for service_name, internal_port in services_to_tunnel.items():
                target = f"{container_ip}:{internal_port}"
                remark = f"Container:{name}_Service:{service_name}"
                # print(f"[ContainerManager Debug] Creating tunnel for {service_name} -> {target}") # 注释掉
                tunnel_info = self.tunnel_manager.create_tunnel(
                    target=target,
                    service_name=service_name,
                    remark=remark
                )

                if tunnel_info and tunnel_info.get("port") is not None:
                    created_tunnels[service_name] = tunnel_info
                    ports_info[f"{service_name}_port"] = tunnel_info["port"]
                    # print(f"[ContainerManager Debug] Tunnel for {service_name} re-created: Port {tunnel_info['port']}") # 注释掉
                else: # Handle failure WITHIN the loop
                    # 保留: 隧道创建失败错误
                    print(f"[ContainerManager] Error: 为已启动的容器 '{name}' 重新创建服务 '{service_name}' 的隧道失败。")
                    tunnel_creation_failed = True
                    failed_services.append(service_name)
                    if service_name == 'ssh': # Break loop on critical failure
                        break

            if tunnel_creation_failed:
                # 保留: 回滚信息
                print(f"[ContainerManager] Error: 由于服务 {failed_services} 的隧道重建失败，正在停止容器 '{name}' 并回滚...")
                for created_service, info in created_tunnels.items():
                     if info.get("tunnel_id") is not None:
                         self.tunnel_manager.delete_tunnel(info["tunnel_id"])
                try: container.stop(timeout=5) 
                except: pass
                return None

            # 更新并保存状态
            self.container_tunnels[name] = created_tunnels
            self._save_container_states()
            
            # 保留: 启动和隧道重建成功
            print(f"[ContainerManager] 容器 '{name}' 启动成功，并已重新创建关联隧道。") 
            return ports_info

        except docker.errors.NotFound:
            # 保留: 容器不存在错误
            print(f"[ContainerManager] Error: 尝试启动时，容器 '{name}' 未找到。") 
            return None
        except docker.errors.APIError as e:
            # 保留: 启动 API 错误
            print(f"[ContainerManager] Error: 启动容器 '{name}' 时出错 (API Error): {e}") 
            return None
        except Exception as e:
            # 保留: 启动未知错误
            print(f"[ContainerManager] Error: 启动容器 '{name}' 时发生意外错误: {e}") 
            return None

    def remove_container(self, name: str, remove_snapshots: bool = False) -> bool:
        """完全删除容器，关联的隧道和可选的快照镜像"""
        container_exists = True
        container = None
        try:
            container = self.client.containers.get(name)
            if container.status == 'running':
                # print(f"[ContainerManager Debug] Container {name} is running. Stopping it first...") # 注释掉
                # stop_container 会处理隧道删除和状态更新，并打印日志
                if not self.stop_container(name): 
                     print(f"[ContainerManager] Warning: 停止运行中的容器 '{name}' 失败，但仍将尝试移除。")
        except docker.errors.NotFound:
            container_exists = False
            # print(f"[ContainerManager Debug] Container {name} not found. Checking for residual tunnel state...") # 注释掉
            # 清理残留隧道 (stop_container 内部已包含此逻辑，理论上不需要重复，但保险起见)
            if name in self.container_tunnels:
                # print(f"[ContainerManager Debug] Deleting residual tunnels for non-existent container {name}...") # 注释掉
                tunnels_to_delete = self.container_tunnels.pop(name)
                self._save_container_states()
                deleted_count = 0
                for service, tunnel_info in tunnels_to_delete.items():
                    if tunnel_info and tunnel_info.get("tunnel_id") is not None:
                        if self.tunnel_manager.delete_tunnel(tunnel_info["tunnel_id"]):
                             deleted_count += 1
                if deleted_count > 0:
                     # 保留: 清理残留隧道信息
                     print(f"[ContainerManager] Info: 清理了 {deleted_count} 个与不存在容器 '{name}' 关联的残留隧道。") 
        except Exception as e:
            # 保留: 检查容器错误
            print(f"[ContainerManager] Error: 移除前检查容器 '{name}' 时出错: {e}. 将继续尝试移除...") 
            
        remove_success = False
        try:
            if container_exists and container: # 确保 container 对象有效
                 # print(f"[ContainerManager Debug] Removing container {name}...") # 注释掉
                 container.remove(force=True) # 强制移除
                 # 保留: 容器移除成功
                 print(f"[ContainerManager] 容器 '{name}' 已移除。") 
                 remove_success = True
            elif not container_exists:
                 # print(f"[ContainerManager Debug] Container {name} was already removed or never existed.") # 注释掉
                 remove_success = True # 容器不存在也算成功
        except docker.errors.NotFound:
             # print(f"[ContainerManager Debug] Container {name} not found during removal attempt.") # 注释掉
             remove_success = True # 不存在也算成功
        except docker.errors.APIError as e:
            # 保留: 移除 API 错误
            print(f"[ContainerManager] Error: 移除容器 '{name}' 时出错 (API Error): {e}") 
        except Exception as e:
             # 保留: 移除未知错误
             print(f"[ContainerManager] Error: 移除容器 '{name}' 时发生意外错误: {e}") 

        # 清理镜像映射 (无论容器移除是否成功，都清理记录)
        image_record_cleaned = False
        if name in self.container_images:
            del self.container_images[name]
            self._save_container_images()
            image_record_cleaned = True
        
        # 清理快照
        snapshot_cleaned = False
        if remove_snapshots:
            if name in self.image_history:
                # print(f"[ContainerManager Debug] Removing snapshots for {name}...") # 注释掉
                images_to_remove = self.image_history.pop(name) # 使用 pop 获取并删除
                self._save_container_images()
                removed_count = 0
                failed_count = 0
                for image_tag in images_to_remove:
                    try:
                        self.client.images.remove(image_tag, force=True)
                        # print(f"[ContainerManager Debug] Removed snapshot image: {image_tag}") # 注释掉
                        removed_count += 1
                    except docker.errors.ImageNotFound:
                        # print(f"[ContainerManager Debug] Snapshot image {image_tag} not found, skipping.") # 注释掉
                        pass
                    except docker.errors.APIError as e:
                        # 保留: 快照删除 API 错误
                        print(f"[ContainerManager] Warning: 删除快照镜像失败 {image_tag} (API Error): {e}") 
                        failed_count += 1
                    except Exception as e:
                         # 保留: 快照删除未知错误
                         print(f"[ContainerManager] Warning: 删除快照镜像时发生未知错误 {image_tag}: {e}")
                         failed_count += 1
                if removed_count > 0 or failed_count > 0:
                     # 保留: 快照清理结果
                     print(f"[ContainerManager] 快照清理完成 ({name}): 成功移除 {removed_count} 个, 失败 {failed_count} 个。") 
                snapshot_cleaned = (failed_count == 0) # 只有全部成功才算清理成功
            else:
                snapshot_cleaned = True # 没有历史记录也算清理成功
        else:
             snapshot_cleaned = True # 不要求删除快照则认为成功

        # 确保隧道状态最终被清理
        tunnel_record_cleaned = False
        if name in self.container_tunnels:
            del self.container_tunnels[name]
            self._save_container_states()
        tunnel_record_cleaned = (name not in self.container_tunnels)
            
        # 最终成功状态取决于：容器移除成功 + (如果需要)快照清理成功 + 状态记录清理成功
        final_success = remove_success and snapshot_cleaned and image_record_cleaned and tunnel_record_cleaned
        if final_success:
             print(f"[ContainerManager] 容器 '{name}' 及相关记录和快照（如果请求）已成功移除。")
        else:
             print(f"[ContainerManager] Warning: 容器 '{name}' 移除过程中可能存在问题，请检查日志。")
        return final_success

    def container_status(self, name: str) -> Optional[Dict[str, Any]]:
        """检查容器详细状态，包括公网端口"""
        try:
            container = self.client.containers.get(name)
            inspect = container.attrs
            status_info = inspect.get('State', {})
            
            result = {
                "name": name,
                "id": container.short_id,
                "status": status_info.get('Status', 'unknown'),
                "running": status_info.get('Running', False),
                "exit_code": status_info.get('ExitCode'),
                "error": status_info.get('Error'),
                "created": inspect.get('Created'),
                "image": inspect.get('Config', {}).get('Image'),
                "ip_address": self._get_container_ip(name),
                "public_ports": self.get_container_ports(name)
            }
            return result

        except docker.errors.NotFound:
            # print(f"[ContainerManager Debug] Container {name} not found for status check.") # 注释掉
            # 检查是否有残留隧道信息
            ports = self.get_container_ports(name)
            if ports:
                 # 保留: 容器不存在但有残留端口警告
                 print(f"[ContainerManager] Warning: 容器 '{name}' 未找到，但存在残留的隧道端口记录: {ports}") 
                 return {
                     "name": name,
                     "status": "not found (with tunnels)",
                     "running": False,
                     "public_ports": ports
                 }
            return {
                 "name": name,
                 "status": "not found",
                 "running": False,
                 "public_ports": None
             }
        except Exception as e:
            # 保留: 获取状态错误
            print(f"[ContainerManager] Error: 获取容器 '{name}' 状态时出错: {e}") 
            return None

    def list_containers(self, all_containers=True) -> List[Dict[str, Any]]:
        """列出容器及其状态和公网端口"""
        containers_list = []
        try:
            docker_containers = self.client.containers.list(all=all_containers)
            managed_containers = set(self.container_tunnels.keys()) | set(self.container_images.keys())
            processed_names = set()

            for container in docker_containers:
                name = container.name
                processed_names.add(name)
                status_info = self.container_status(name)
                if status_info:
                     containers_list.append(status_info)
                else: 
                     # 获取状态失败，提供基本信息
                     # 保留: 状态获取失败警告
                     print(f"[ContainerManager] Warning: 获取容器 '{name}' 的详细状态失败，仅列出基本信息。") 
                     containers_list.append({
                         "name": name,
                         "id": container.short_id,
                         "status": container.status,
                         "running": container.status == 'running',
                         "image": container.image.tags[0] if container.image.tags else 'unknown',
                         "public_ports": self.get_container_ports(name)
                     })

            # 添加状态记录中存在但 Docker 中没有的容器
            for name in managed_containers:
                 if name not in processed_names:
                     status_info = self.container_status(name) # 会返回 not found 状态
                     if status_info:
                          containers_list.append(status_info)
            
            return containers_list
        except Exception as e:
            # 保留: 列出容器错误
            print(f"[ContainerManager] Error: 列出容器时出错: {e}") 
            return []

    def stop_and_commit(self, name: str, commit_message: str = None) -> Optional[str]:
        """停止容器，删除隧道，并将其提交为新快照镜像"""
        container = None
        try:
            container = self.client.containers.get(name)
        except docker.errors.NotFound:
            # 保留: 容器不存在错误
            print(f"[ContainerManager] Error: 无法提交快照，容器 '{name}' 未找到。") 
            return None
        except Exception as e:
            print(f"[ContainerManager] Error: 检查容器 '{name}' 时出错: {e}")
            return None
            
        # 1. 停止容器并删除隧道
        # stop_container 会打印相关日志
        if not self.stop_container(name):
            # 保留: 停止失败错误
            print(f"[ContainerManager] Error: 停止容器 '{name}' 或删除隧道失败。中止快照提交。") 
            return None

        # 2. 生成新标签
            timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._load_container_images() # 确保历史最新
        version = len(self.image_history.get(name, [])) + 1
        new_image_tag_base = f"{name}" # Repository name
        new_image_tag_version = f"v{version}_{timestamp}" # Tag part
        
        # 3. 准备 commit changes
        config = container.attrs['Config']
        changes = []
        if config.get('Entrypoint'): changes.append(f"ENTRYPOINT {json.dumps(config['Entrypoint'])}")
        if config.get('Cmd'): changes.append(f"CMD {json.dumps(config['Cmd'])}")
        if config.get('WorkingDir'): changes.append(f"WORKDIR {config['WorkingDir']}")
        if config.get('Env'):
            for env_str in config['Env']:
                if not env_str.startswith("JUPYTER_PORT=") and not env_str.startswith("APP_PORT="):
                    changes.append(f"ENV {env_str}")
        if config.get('ExposedPorts'):
            for port_proto in config['ExposedPorts']:
                changes.append(f"EXPOSE {port_proto}")

        # 4. 提交镜像
        final_image_tag = None
        try:
            # print(f"[ContainerManager Debug] Committing container {name} to image {new_image_tag_base}:{new_image_tag_version}...") # 注释掉
            new_image = container.commit(
                repository=new_image_tag_base,
                tag=new_image_tag_version,
                message=commit_message or f"Snapshot v{version} for {name} at {timestamp}",
                changes=changes
            )
            final_image_tag = new_image.tags[0] if new_image.tags else f"{new_image_tag_base}:{new_image_tag_version}" # 获取最终标签
            # 保留: 提交成功信息
            print(f"[ContainerManager] 镜像 '{final_image_tag}' 创建成功。") 
        except docker.errors.APIError as e:
            # 保留: 提交 API 错误
            print(f"[ContainerManager] Error: 提交容器 '{name}' 为镜像时出错 (API Error): {e}") 
            return None
        except Exception as e:
             # 保留: 提交未知错误
             print(f"[ContainerManager] Error: 提交容器 '{name}' 为镜像时发生意外错误: {e}") 
             return None
        
        # 5. 更新状态并保存
        self.container_images[name] = final_image_tag
        if name not in self.image_history: self.image_history[name] = []
        self.image_history[name].append(final_image_tag)
        self._save_container_images()
            
        # 6. 删除旧容器 (此时容器已停止)
        try:
            container.remove()
            # print(f"[ContainerManager Debug] Original container {name} removed after commit.") # 注释掉
        except docker.errors.APIError as e:
             # 保留: 删除旧容器警告
             print(f"[ContainerManager] Warning: 提交快照后未能移除原始容器 '{name}': {e}") 
        except Exception as e:
             print(f"[ContainerManager] Warning: 移除原始容器 '{name}' 时发生意外错误: {e}")
        
        # 7. 清理旧镜像
        self._cleanup_old_images(name) # 会打印清理日志
        
        # 保留: 快照流程完成
        print(f"[ContainerManager] 容器 '{name}' 的快照 '{final_image_tag}' 创建完成。") 
        return final_image_tag

    def start_from_snapshot(self, name: str, version_tag: str = None) -> Optional[Dict[str, int]]:
        """从快照镜像启动一个新容器，并创建隧道"""
        self._load_container_images()
        available_versions = self.image_history.get(name, [])
        if not available_versions:
            # 保留: 无快照错误
            print(f"[ContainerManager] Error: 未找到容器 '{name}' 的任何快照。") 
            return None

        image_tag_to_use = None
        if version_tag is None:
            image_tag_to_use = available_versions[-1]
            # print(f"[ContainerManager Debug] Starting from latest snapshot for {name}: {image_tag_to_use}") # 注释掉
        else:
            found = False
            for tag in reversed(available_versions):
                if version_tag == tag or version_tag in tag.split(':')[-1]:
                    image_tag_to_use = tag
                    found = True
                    # print(f"[ContainerManager Debug] Found snapshot matching '{version_tag}': {image_tag_to_use}") # 注释掉
                    break
            if not found:
                # 保留: 未找到指定版本快照错误
                print(f"[ContainerManager] Error: 未找到与 '{version_tag}' 匹配的快照版本 (容器: {name})。") 
                # print("Available snapshots:")
                # for v in available_versions: print(f"  - {v}") # 调试时可取消注释
                return None

        # print(f"[ContainerManager Debug] Attempting to start from snapshot: {image_tag_to_use}") # 注释掉
        try:
            # print(f"[ContainerManager Debug] Checking if snapshot image {image_tag_to_use} exists locally...") # 注释掉
            image = self.client.images.get(image_tag_to_use)
            # print(f"[ContainerManager Debug] Snapshot image found.") # 注释掉
        except docker.errors.ImageNotFound:
            # 保留: 快照镜像不存在错误
            print(f"[ContainerManager] Error: 快照镜像 '{image_tag_to_use}' 在本地未找到。") 
            return None
        except Exception as e:
             # 保留: 检查镜像错误
             print(f"[ContainerManager] Error: 检查快照镜像 '{image_tag_to_use}' 时出错: {e}") 
             return None
            
        # 检查并移除同名容器
        try:
            existing_container = self.client.containers.get(name)
            # 保留: 移除现有容器信息
            print(f"[ContainerManager] Info: 容器 '{name}' 已存在，将在从快照启动前移除它...") 
            if not self.remove_container(name, remove_snapshots=False):
                 # 保留: 移除失败错误
                 print(f"[ContainerManager] Error: 移除现有容器 '{name}' 失败。无法从快照启动。") 
                 return None
            # print(f"[ContainerManager Debug] Existing container {name} removed.") # 注释掉
        except docker.errors.NotFound:
            # print(f"[ContainerManager Debug] No existing container named {name} found. Proceeding to start from snapshot.") # 注释掉
            # 清理残留隧道状态
            if name in self.container_tunnels:
                # print(f"[ContainerManager Debug] Cleaning up residual tunnel state for {name}...") # 注释掉
                tunnels_to_delete = self.container_tunnels.pop(name)
                self._save_container_states()
                for service, tunnel_info in tunnels_to_delete.items():
                    if tunnel_info and tunnel_info.get("tunnel_id") is not None:
                         self.tunnel_manager.delete_tunnel(tunnel_info["tunnel_id"])
        except Exception as e:
             # 保留: 检查/移除现有容器错误
             print(f"[ContainerManager] Error: 检查或移除现有容器 '{name}' 时出错: {e}. 谨慎继续...") 

        # 使用 create_container 逻辑启动
        # 保留: 从快照启动信息
        print(f"[ContainerManager] 正在从快照 '{image_tag_to_use}' 启动容器 '{name}'...") 
        # create_container 会打印后续日志
        return self.create_container(image=image_tag_to_use, name=name, container_config=None)

    def list_snapshots(self, name: str = None) -> List[Dict[str, Any]]:
        """列出容器的快照历史 (返回结构化数据)"""
        snapshot_list = []
        self._load_container_images()
        history_to_show = {}
        if name:
            if name not in self.image_history:
                # print(f"[ContainerManager Debug] No snapshots found for container {name}") # 注释掉
                return []
            history_to_show = {name: self.image_history[name]}
        else:
            history_to_show = self.image_history

        for container_name, versions in history_to_show.items():
            container_snapshots = {"container_name": container_name, "versions": []}
            for i, version_tag in enumerate(reversed(versions), 1):
                snapshot_info = {"tag": version_tag, "index": len(versions) - i + 1}
                try:
                    image = self.client.images.get(version_tag)
                    created_str = image.attrs.get('Created', 'N/A')
                    # Attempt to parse the date string, fall back to raw string on error
                    try:
                        if isinstance(created_str, str) and 'T' in created_str:
                             time_part = created_str.split('.')[0] # Remove fractional seconds
                             created_dt = datetime.fromisoformat(time_part)
                             snapshot_info["created"] = created_dt.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                             snapshot_info["created"] = created_str # Use raw string if not matching format
                    except (ValueError, TypeError) as date_parse_err: # Catch potential parsing errors
                         print(f"[ContainerManager] Warning: Could not parse date format '{created_str}' for snapshot '{version_tag}'. Using raw value. Error: {date_parse_err}")
                         snapshot_info["created"] = created_str # Fallback to raw string on error

                    snapshot_info["size_mb"] = round(image.attrs.get('Size', 0) / (1024*1024), 1)
                    snapshot_info["message"] = image.attrs.get('Comment', '')
                    snapshot_info["id"] = image.short_id
                    snapshot_info["found"] = True
                except docker.errors.ImageNotFound:
                    snapshot_info["found"] = False
                    snapshot_info["message"] = "(镜像在本地未找到)"
                except Exception as e:
                     snapshot_info["found"] = False
                     snapshot_info["message"] = f"(获取信息时出错: {e})"
                
                container_snapshots["versions"].append(snapshot_info)
            snapshot_list.append(container_snapshots)
            
        return snapshot_list

def main():
    # 保留测试代码中的主要流程信息，减少细节打印
    try:
        tunnel_manager = DynamicTunnelManager() 
    except Exception as e:
        print(f"[Main Error] 初始化 DynamicTunnelManager 失败: {e}")
        return

    manager = DockerContainerManager(tunnel_manager=tunnel_manager)

    container_name = "test-container-01" # 使用唯一的测试名称
    base_image = "hello-world" # 使用简单的基础镜像进行测试

    print(f"\n--- 0. 清理旧的测试容器 '{container_name}' (如果存在) ---")
    manager.remove_container(container_name, remove_snapshots=True) # 清理快照

    print(f"\n--- 1. 创建容器 '{container_name}' ---")
    ports = manager.create_container(base_image, container_name)
    if ports:
        print(f"[Main Info] 容器 '{container_name}' 创建，端口: {ports}")
    else:
        print(f"[Main Info] 容器 '{container_name}' 创建失败 (对于 hello-world，隧道失败是正常的)。")
        pass 

    print(f"\n--- 2. 列出容器状态 ---")
    containers = manager.list_containers()
    found_test = False
    for c in containers:
        if c.get('name') == container_name:
            print(f"[Main Info] 找到测试容器: Name={c.get('name')}, Status={c.get('status')}, Running={c.get('running')}")
            found_test = True
            break
    if not found_test:
        print(f"[Main Warning] 未在列表中找到测试容器 '{container_name}'")

    print(f"\n--- 6. 提交快照 for '{container_name}' ---")
    try:
        manager.client.containers.get(container_name)
        snapshot_tag = manager.stop_and_commit(container_name, commit_message="Test Snapshot")
        if snapshot_tag:
            print(f"[Main Info] 快照创建成功: {snapshot_tag}")
        else:
            print(f"[Main Error] 创建快照失败。")
    except docker.errors.NotFound:
        print(f"[Main Info] 容器 '{container_name}' 不存在，无法提交快照 (hello-world 可能已自动移除)。")

    print(f"\n--- 7. 列出快照 ---")
    snapshots = manager.list_snapshots(container_name)
    if snapshots:
        for snap_info in snapshots:
            print(f"[Main Info] 容器: {snap_info['container_name']}")
            for v in snap_info['versions']:
                print(f"  - Tag: {v['tag']}, Found: {v['found']}")
    else:
        print(f"[Main Info] 未找到 '{container_name}' 的快照。")

    print(f"\n--- 10. 清理容器 '{container_name}' 和快照 ---")
    if manager.remove_container(container_name, remove_snapshots=True):
        print(f"[Main Info] 容器 '{container_name}' 和快照清理成功。")
    else:
        print(f"[Main Error] 容器 '{container_name}' 和快照清理失败。")

if __name__ == "__main__":
    main()
