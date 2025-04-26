"""
Dynamic Tunnel Manager - 动态隧道管理工具

这个模块整合了NPSManager和PortManager，提供了完整的动态端口映射隧道管理功能。
主要功能:
1. 自动分配端口并创建隧道
2. 维护端口池和隧道映射关系
3. 统一的隧道生命周期管理
4. 持久化隧道配置
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple

# 导入相关模块
from nps_manager import NPSManager
from port_manager import PortManager

class DynamicTunnelManager:
    def __init__(self, nps_config=None, port_config=None):
        """
        初始化动态隧道管理器
        
        参数:
            nps_config: NPS配置文件路径
            port_config: 端口配置文件路径
        """
        # 初始化NPS和端口管理器
        self.nps = NPSManager(config_file=nps_config)
        self.port_manager = PortManager(config_file=port_config)
        
        # 初始化隧道映射关系
        self.tunnel_mappings = {}  # {tunnel_id: {"port": port, "service": "ssh", "client_id": 1, ...}}
        
        # 加载隧道映射
        self._load_tunnel_mappings()
        
        print("动态隧道管理器初始化完成")
    
    def _load_tunnel_mappings(self):
        """加载隧道映射关系"""
        # 从NPS获取现有隧道
        client_id = self.nps.config.get("clients", {}).get("default_client_id", 2)
        tunnels = self.nps.list_tunnels(client_id=client_id)
        
        loaded_count = 0
        if tunnels and 'rows' in tunnels and tunnels['rows']:
            for tunnel in tunnels['rows']:
                tunnel_id = tunnel['Id']
                port = tunnel['Port']
                target = tunnel['Target']['TargetStr'] if 'Target' in tunnel and 'TargetStr' in tunnel['Target'] else ""
                remark = tunnel.get('Remark', '')
                
                # 提取服务名称，如果备注中包含服务信息
                service = "unknown"
                if "ssh" in remark.lower() or ":22" in target:
                    service = "ssh"
                elif "http" in remark.lower() or ":80" in target or ":8080" in target:
                    service = "http"
                elif "jupyter" in remark.lower() or ":8888" in target:
                    service = "jupyter"
                elif "web" in remark.lower(): # 更通用的web服务
                    service = "web"
                
                # 保存隧道映射关系
                self.tunnel_mappings[tunnel_id] = {
                    "port": port,
                    "service": service,
                    "client_id": client_id,
                    "target": target,
                    "remark": remark
                }
                
                # 在端口管理器中标记该端口已分配 (使用 internal 方法需要注意)
                # 确保端口管理器确实加载了该端口
                if not self.port_manager.is_port_allocated(port):
                    self.port_manager._mark_port_allocated(port, service, client_id)
                loaded_count += 1
            
            # 保留: 加载成功信息
            if loaded_count > 0:
                print(f"已从 NPS 加载并同步 {loaded_count} 个现有隧道映射")
    
    def create_tunnel(self, target: str, service_name: str, client_id: int = None, preferred_port: int = None, remark: str = None) -> Optional[Dict]:
        """
        创建新的动态隧道
        
        参数:
            target: 目标地址 (如 "172.19.102.74:22")
            service_name: 服务名称 (如 "ssh", "http", "jupyter")
            client_id: 客户端ID，如果不指定则使用默认值
            preferred_port: 优先使用的端口，如果不指定则自动分配
            remark: 隧道备注
            
        返回:
            成功返回隧道信息字典，失败返回None
        """
        print(f"[TunnelManager] 请求创建隧道: 服务='{service_name}', 目标='{target}', 偏好端口={preferred_port}")
        
        # 获取客户端ID
        if client_id is None:
            client_id = self.nps.config.get("clients", {}).get("default_client_id", 2)
        # print(f"[TunnelManager] Using Client ID: {client_id}") # 调试信息，注释掉

        # 分配端口
        # print(f"[TunnelManager] Allocating port for service '{service_name}' (Preferred: {preferred_port})...") # 调试信息，注释掉
        port = self.port_manager.allocate_port(service_name, client_id, preferred_port)
        if port is None:
            # 保留: 端口分配失败错误
            print(f"[TunnelManager] Error: 分配端口失败，无法创建隧道 (服务: {service_name})")
            return None
        # print(f"[TunnelManager] Allocated port: {port}") # 调试信息，注释掉

        # 生成隧道备注
        if remark is None:
            remark = f"{service_name}_{target}_{int(time.time())}"
        # print(f"[TunnelManager] Using Remark: '{remark}'") # 调试信息，注释掉

        # 创建隧道
        tunnel_type = "tcp"  # 默认使用TCP隧道
        # print(f"[TunnelManager] Calling NPS API to add tunnel (Client={client_id}, Type={tunnel_type}, Port={port}, Target={target}, Remark='{remark}')...") # 调试信息，注释掉
        result = self.nps.add_tunnel(
            client_id=client_id,
            tunnel_type=tunnel_type,
            port=port,
            target=target,
            remark=remark
        )
        # print(f"[TunnelManager] NPS API add_tunnel result: {result}") # 调试信息，注释掉

        if not result:
            # 创建失败，释放端口
            # print(f"[TunnelManager] NPS API call failed. Releasing allocated port {port}...") # 调试信息，注释掉
            self.port_manager.release_port(port)
            # 保留: NPS API 调用失败错误
            print(f"[TunnelManager] Error: 创建隧道失败 (NPS API 调用失败)，已释放端口 {port}")
            return None

        # 获取新建隧道的ID
        tunnel_id = None
        # print(f"[TunnelManager] Attempting to fetch Tunnel ID for port {port}...") # 调试信息，注释掉
        for attempt in range(3):  # 尝试3次
            # print(f"[TunnelManager] Fetch attempt {attempt + 1}/3...") # 调试信息，注释掉
            tunnels = self.nps.list_tunnels(client_id=client_id)
            if tunnels and 'rows' in tunnels and tunnels['rows']:
                for tunnel in tunnels['rows']:
                    # 确保 port 匹配
                    if tunnel.get('Port') == port: 
                        tunnel_id = tunnel.get('Id')
                        # print(f"[TunnelManager] Found Tunnel ID: {tunnel_id}") # 调试信息，注释掉
                        break
            
            if tunnel_id:
                break
                
            # print(f"[TunnelManager] Tunnel ID not found yet, sleeping for 1 second...") # 调试信息，注释掉
            time.sleep(1)  # 等待1秒后重试
        
        if not tunnel_id:
            # 虽然隧道可能已创建成功，但无法获取ID进行后续管理
            # 保留: 获取隧道 ID 失败警告
            print(f"[TunnelManager] Warning: 无法获取端口 {port} 的隧道 ID。隧道可能已创建但无法被管理器追踪。")
            # 依然返回信息，但标记 tunnel_id 为 None
            return {
                "port": port,
                "service": service_name,
                "client_id": client_id,
                "target": target,
                "remark": remark,
                "tunnel_id": None # 标记 ID 获取失败
            }
        
        # 保存隧道映射关系
        self.tunnel_mappings[tunnel_id] = {
            "port": port,
            "service": service_name,
            "client_id": client_id,
            "target": target,
            "remark": remark
        }
        # 保留: 隧道创建成功信息
        print(f"[TunnelManager] 隧道创建成功: ID={tunnel_id}, 端口={port}, 服务={service_name}, 目标={target}")
        
        # 返回隧道信息
        return {
            "tunnel_id": tunnel_id,
            "port": port,
            "service": service_name,
            "client_id": client_id,
            "target": target,
            "remark": remark
        }
    
    def delete_tunnel(self, tunnel_id: int) -> bool:
        """
        删除隧道
        
        参数:
            tunnel_id: 隧道ID
            
        返回:
            成功返回True，失败返回False
        """
        # 保留: 函数入口信息
        print(f"[TunnelManager] 请求删除隧道: ID={tunnel_id}")
        # 检查隧道是否存在
        if tunnel_id not in self.tunnel_mappings:
            # 保留: 隧道不存在错误
            print(f"[TunnelManager] Error: 删除隧道失败，隧道ID {tunnel_id} 不存在于映射中")
            # 尝试从 NPS 强制删除，以防映射不同步
            print(f"[TunnelManager] 尝试从 NPS 直接删除隧道 ID {tunnel_id}...")
            result = self.nps.delete_tunnel(tunnel_id)
            if result:
                print(f"[TunnelManager] Info: 成功从 NPS 删除了未被追踪的隧道 ID {tunnel_id}")
                # 即使本地没有，也检查下端口管理器里是否有残留端口
                port_to_check = None
                # (这里逻辑比较复杂，暂时不实现孤立端口的查找和释放)
                return True
            else:
                print(f"[TunnelManager] Error: 从 NPS 直接删除隧道 ID {tunnel_id} 也失败了")
                return False

        # 获取隧道信息
        tunnel_info = self.tunnel_mappings[tunnel_id]
        port = tunnel_info["port"]
        service_name = tunnel_info.get("service", "unknown")
        
        # 删除NPS隧道
        # print(f"[TunnelManager] Calling NPS API to delete tunnel ID {tunnel_id}...") # 调试信息，注释掉
        result = self.nps.delete_tunnel(tunnel_id)
        if not result:
            # 保留: NPS API 调用失败错误
            print(f"[TunnelManager] Error: 删除隧道失败 (NPS API 错误)，隧道 ID={tunnel_id}")
            return False
        
        # 释放端口
        # print(f"[TunnelManager] Releasing port {port}...") # 调试信息，注释掉
        self.port_manager.release_port(port)
        
        # 删除隧道映射
        del self.tunnel_mappings[tunnel_id]
        
        # 保留: 隧道删除成功信息
        print(f"[TunnelManager] 隧道删除成功: ID={tunnel_id}, 端口={port}, 服务={service_name}")
        return True
    
    def update_tunnel(self, tunnel_id: int, target=None, port=None, remark=None) -> bool:
        """
        更新隧道配置
        
        参数:
            tunnel_id: 隧道ID
            target: 新的目标地址，不修改则为None
            port: 新的端口，不修改则为None
            remark: 新的备注，不修改则为None
            
        返回:
            成功返回True，失败返回False
        """
        # 保留: 函数入口信息
        print(f"[TunnelManager] 请求更新隧道: ID={tunnel_id}, 新目标={target}, 新端口={port}, 新备注={remark}")
        # 检查隧道是否存在
        if tunnel_id not in self.tunnel_mappings:
            # 保留: 隧道不存在错误
            print(f"[TunnelManager] Error: 更新隧道失败，隧道ID {tunnel_id} 不存在于映射中")
            return False
        
        # 获取隧道信息
        tunnel_info = self.tunnel_mappings[tunnel_id]
        old_port = tunnel_info["port"]
        service_name = tunnel_info["service"]
        client_id = tunnel_info["client_id"]
        old_target = tunnel_info.get("target", "unknown")
        old_remark = tunnel_info.get("remark", "")
        
        # 确定最终要更新的值
        final_target = target if target is not None else old_target
        final_port = port if port is not None else old_port
        final_remark = remark if remark is not None else old_remark
        
        # 如果没有实际变化，则直接返回成功
        if final_target == old_target and final_port == old_port and final_remark == old_remark:
            print(f"[TunnelManager] Info: 隧道 {tunnel_id} 无需更新")
            return True
        
        allocated_new_port = False
        # 如果需要修改端口
        if port is not None and port != old_port:
            # 检查新端口是否可用
            if not self.port_manager._is_port_available(port):
                # 保留: 端口不可用错误
                print(f"[TunnelManager] Error: 更新隧道失败，新端口 {port} 不可用")
                return False
            
            # 尝试分配新端口
            if not self.port_manager._mark_port_allocated(port, service_name, client_id):
                print(f"[TunnelManager] Error: 更新隧道失败，无法在 PortManager 中标记新端口 {port}")
                return False
            allocated_new_port = True
            final_port = port # 确认使用新端口
            # print(f"[TunnelManager] New port {port} allocated for update.") # 调试信息，注释掉
        
        # 更新NPS隧道 (注意: NPS API 可能不支持只更新部分字段，需要确认API行为)
        # print(f"[TunnelManager] Calling NPS API to update tunnel ID {tunnel_id}...") # 调试信息，注释掉
        result = self.nps.update_tunnel(
            tunnel_id=tunnel_id,
            target=final_target if target is not None else None, # 只在明确指定时传递
            port=final_port if port is not None else None,       # 只在明确指定时传递
            remark=final_remark if remark is not None else None    # 只在明确指定时传递
        )
        
        if not result:
            # 更新失败，如果分配了新端口，需要释放
            if allocated_new_port:
                self.port_manager.release_port(port)
                # print(f"[TunnelManager] NPS API update failed. Released newly allocated port {port}.") # 调试信息，注释掉
            # 保留: NPS API 调用失败错误
            print(f"[TunnelManager] Error: 更新隧道失败 (NPS API 错误)，隧道 ID={tunnel_id}")
            return False
        
        # 更新成功，处理端口和映射
        if allocated_new_port:
            self.port_manager.release_port(old_port) # 释放旧端口
            self.tunnel_mappings[tunnel_id]["port"] = final_port
            # print(f"[TunnelManager] Old port {old_port} released.") # 调试信息，注释掉
        
        # 更新映射中的其他信息
        if target is not None:
            self.tunnel_mappings[tunnel_id]["target"] = final_target
        if remark is not None:
            self.tunnel_mappings[tunnel_id]["remark"] = final_remark
        
        # 保留: 隧道更新成功信息
        print(f"[TunnelManager] 隧道更新成功: ID={tunnel_id}")
        return True
    
    def get_tunnel_info(self, tunnel_id: int) -> Optional[Dict]:
        """
        获取隧道信息
        
        参数:
            tunnel_id: 隧道ID
            
        返回:
            成功返回隧道信息字典，失败返回None
        """
        # 检查本地缓存
        if tunnel_id in self.tunnel_mappings:
            info = self.tunnel_mappings[tunnel_id].copy()
            info["tunnel_id"] = tunnel_id
            # print(f"[TunnelManager] Tunnel info for ID {tunnel_id} found in cache.") # 调试信息，注释掉
            return info
        
        # 如果缓存没有，尝试从NPS获取 (可能表示映射不同步)
        # print(f"[TunnelManager] Tunnel ID {tunnel_id} not in cache, fetching from NPS...") # 调试信息，注释掉
        tunnel_info = self.nps.get_tunnel(tunnel_id)
        if tunnel_info and 'code' in tunnel_info and tunnel_info['code'] == 1 and 'data' in tunnel_info:
            data = tunnel_info['data']
            # 检查返回的数据是否有效
            if not data or 'Id' not in data or 'Port' not in data or 'Client' not in data or 'Id' not in data['Client']:
                print(f"[TunnelManager] Warning: 从 NPS 获取的隧道 {tunnel_id} 信息不完整或格式错误")
                return None

            # 提取服务名称
            port = data['Port']
            client_id = data['Client']['Id']
            target = data['Target']['TargetStr'] if 'Target' in data and 'TargetStr' in data['Target'] else ""
            remark = data.get('Remark', '')
            service = "unknown"
            if "ssh" in remark.lower() or ":22" in target:
                service = "ssh"
            elif "http" in remark.lower() or ":80" in target or ":8080" in target:
                service = "http"
            elif "jupyter" in remark.lower() or ":8888" in target:
                service = "jupyter"
            elif "web" in remark.lower():
                service = "web"
            
            # 更新本地缓存
            self.tunnel_mappings[tunnel_id] = {
                "port": port,
                "service": service,
                "client_id": client_id,
                "target": target,
                "remark": remark
            }
            # print(f"[TunnelManager] Tunnel info for ID {tunnel_id} fetched from NPS and cached.") # 调试信息，注释掉
            
            # 在端口管理器中标记该端口 (如果之前未标记)
            if not self.port_manager.is_port_allocated(port):
                self.port_manager._mark_port_allocated(port, service, client_id)
                print(f"[TunnelManager] Info: 从NPS同步并标记了端口 {port} (服务: {service})")
            
            result = self.tunnel_mappings[tunnel_id].copy()
            result["tunnel_id"] = tunnel_id
            return result
        else:
            # 保留: 获取隧道信息失败
            print(f"[TunnelManager] Info: 无法从 NPS 获取隧道 ID {tunnel_id} 的信息")
        
        return None
    
    def list_tunnels(self, client_id=None, service=None) -> List[Dict]:
        """
        获取隧道列表 (基于本地缓存)
        
        参数:
            client_id: 客户端ID筛选
            service: 服务名称筛选
            
        返回:
            隧道信息列表
        """
        result = []
        # print(f"[TunnelManager] Listing tunnels (Client={client_id}, Service={service})...") # 调试信息，注释掉
        
        # 创建副本以防迭代时修改
        mappings_copy = self.tunnel_mappings.copy()
        for tunnel_id, info in mappings_copy.items():
            # 筛选条件
            if client_id is not None and info.get("client_id") != client_id:
                continue
            if service is not None and info.get("service") != service:
                continue
            
            # 添加隧道ID
            tunnel_info = info.copy()
            tunnel_info["tunnel_id"] = tunnel_id
            result.append(tunnel_info)
        
        # print(f"[TunnelManager] Found {len(result)} tunnels matching criteria.") # 调试信息，注释掉
        return result
    
    def find_port_by_service(self, service_name: str, client_id=None) -> List[int]:
        """
        查找指定服务的所有端口 (基于本地缓存)
        
        参数:
            service_name: 服务名称
            client_id: 可选的客户端ID筛选
            
        返回:
            端口列表
        """
        result = []
        # print(f"[TunnelManager] Finding ports for service '{service_name}' (Client={client_id})...") # 调试信息，注释掉
        
        for info in self.list_tunnels(client_id=client_id, service=service_name):
            if "port" in info:
                result.append(info["port"])
        
        # print(f"[TunnelManager] Found ports for service '{service_name}': {result}") # 调试信息，注释掉
        return result
    
    def create_service_tunnels(self, services: List[Dict]) -> Dict[str, Dict]:
        """
        批量创建服务隧道
        
        参数:
            services: 服务列表，每个服务是一个字典，包含:
                - name: 服务名称
                - target: 目标地址
                - preferred_port: 优先端口 (可选)
                - client_id: 客户端ID (可选)
                - remark: 备注 (可选)
                
        返回:
            服务名称到成功创建的隧道信息的映射字典
        """
        # 保留: 函数入口信息
        print(f"[TunnelManager] 请求批量创建 {len(services)} 个服务隧道...")
        result = {}
        success_count = 0
        
        for service_config in services:
            name = service_config.get("name")
            target = service_config.get("target")
            
            if not name or not target:
                # 保留: 配置错误警告
                print(f"[TunnelManager] Warning: 跳过无效的服务配置: {service_config}")
                continue

            preferred_port = service_config.get("preferred_port")
            client_id = service_config.get("client_id")
            remark = service_config.get("remark")
            
            # print(f"[TunnelManager] Creating tunnel for service: {name}...") # 调试信息，注释掉
            tunnel = self.create_tunnel(
                target=target,
                service_name=name,
                client_id=client_id,
                preferred_port=preferred_port,
                remark=remark
            )
            
            if tunnel and tunnel.get("tunnel_id") is not None:
                result[name] = tunnel
                success_count += 1
            elif tunnel: # tunnel 创建了，但没拿到 ID
                result[name] = tunnel # 仍然记录，但标记 ID 问题
                # 警告已经在 create_tunnel 打印
            else:
                # 失败信息已经在 create_tunnel 打印
                pass

        # 保留: 批量创建结果信息
        print(f"[TunnelManager] 批量创建完成: {success_count} 个隧道成功创建 (共请求 {len(services)} 个)")
        return result
    
    def clear_service_tunnels(self, service_name: str, client_id=None) -> int:
        """
        清除指定服务的所有隧道
        
        参数:
            service_name: 服务名称
            client_id: 可选的客户端ID筛选
            
        返回:
            删除的隧道数量
        """
        # 保留: 函数入口信息
        print(f"[TunnelManager] 请求清除服务 '{service_name}' 的所有隧道" + (f" (客户端ID: {client_id})" if client_id else "") + "...")
        # 获取服务隧道 (基于缓存)
        tunnels_to_delete = self.list_tunnels(client_id=client_id, service=service_name)
        count = 0
        
        if not tunnels_to_delete:
            print(f"[TunnelManager] Info: 没有找到服务 '{service_name}' 的隧道，无需清除")
            return 0

        # 删除隧道
        for tunnel in tunnels_to_delete:
            tunnel_id = tunnel.get("tunnel_id")
            if tunnel_id:
                # print(f"[TunnelManager] Deleting tunnel ID: {tunnel_id} for service '{service_name}'...") # 调试信息，注释掉
                if self.delete_tunnel(tunnel_id):
                    count += 1
                else:
                    # 删除失败信息已在 delete_tunnel 打印
                    pass
            else:
                # 保留: 无法删除警告
                print(f"[TunnelManager] Warning: 无法删除服务 '{service_name}' 的一个隧道，因为它没有有效的 tunnel_id: {tunnel}")
        
        # 保留: 清除结果信息
        print(f"[TunnelManager] 已清除 {count} 个 '{service_name}' 服务隧道 (共找到 {len(tunnels_to_delete)} 个)")
        return count
    
    def cleanup(self):
        """保存状态并清理"""
        # 保存端口分配状态
        self.port_manager.save_allocated_ports()
        # 保留: 清理完成信息
        print("[TunnelManager] 已触发端口分配状态保存")


# 测试代码
if __name__ == "__main__":
    # 初始化管理器
    # 确保测试前 config 目录和空的 state 目录存在
    os.makedirs("config", exist_ok=True)
    os.makedirs("state", exist_ok=True)
    # 创建默认配置文件 (如果不存在)
    if not os.path.exists("config/nps_config.json"):
        NPSManager.create_default_config("config/nps_config.json")
    if not os.path.exists("config/port_config.json"):
        PortManager.create_default_config("config/port_config.json")

    print("开始测试 DynamicTunnelManager...")
    try:
        tunnel_manager = DynamicTunnelManager()
    except Exception as e:
        print(f"初始化 DynamicTunnelManager 失败: {e}")
        print("请确保 NPS 服务正在运行，并且配置文件 (config/nps_config.json, config/port_config.json) 正确。")
        exit()
    
    # 测试创建隧道
    print("\n===== 测试创建隧道 =====")
    ssh_target = "192.168.1.100:22" # 请替换为实际可访问的 SSH 目标
    ssh_tunnel = tunnel_manager.create_tunnel(
        target=ssh_target,
        service_name="ssh",
        remark="测试SSH隧道"
    )
    # print(f"SSH隧道信息: {ssh_tunnel}") # 已有成功/失败日志
    
    # 测试隧道列表 (应该能看到刚才创建的，如果成功)
    print("\n===== 测试隧道列表 =====")
    tunnels = tunnel_manager.list_tunnels()
    print(f"当前隧道数量: {len(tunnels)}")
    # for t in tunnels: print(t) # 打印详细列表可能太长，注释掉
    
    # 测试更新隧道
    if ssh_tunnel and ssh_tunnel.get("tunnel_id"):
        print("\n===== 测试更新隧道 =====")
        new_remark = f"更新的SSH隧道_{int(time.time())}"
        update_result = tunnel_manager.update_tunnel(
            tunnel_id=ssh_tunnel["tunnel_id"],
            remark=new_remark
        )
        # print(f"更新隧道结果: {update_result}") # 已有成功/失败日志
        
        # 获取更新后的隧道信息
        updated_info = tunnel_manager.get_tunnel_info(ssh_tunnel["tunnel_id"])
        print(f"更新后的隧道信息: {updated_info}")
    else:
        print("\n===== 跳过更新隧道测试 (未成功创建 SSH 隧道或获取 ID) =====")
    
    # 测试查找服务端口
    print("\n===== 测试查找服务端口 =====")
    ssh_ports = tunnel_manager.find_port_by_service("ssh")
    print(f"找到的 SSH 服务端口: {ssh_ports}")
    
    # 测试批量创建服务隧道
    print("\n===== 测试批量创建服务隧道 =====")
    web_target = "192.168.1.101:80" # 请替换为实际可访问的 Web 目标
    jupyter_target = "192.168.1.102:8888" # 请替换为实际可访问的 Jupyter 目标
    services_to_create = [
        {"name": "web", "target": web_target, "remark": "Web服务"},
        {"name": "jupyter", "target": jupyter_target, "remark": "Jupyter服务"}
    ]
    service_tunnels = tunnel_manager.create_service_tunnels(services_to_create)
    print(f"批量创建的服务隧道结果: {service_tunnels}")

    # 测试清除服务隧道 (清除刚才批量创建的 web)
    print("\n===== 测试清除服务隧道 (Web) =====")
    cleared_web = tunnel_manager.clear_service_tunnels("web")
    # print(f"清除的Web隧道数量: {cleared_web}") # 已有成功/失败日志

    # 清理所有剩余的SSH隧道
    print("\n===== 清理所有 SSH 隧道 =====")
    cleared_ssh = tunnel_manager.clear_service_tunnels("ssh")
    # print(f"清除的SSH隧道数量: {cleared_ssh}") # 已有成功/失败日志

    # 清理所有剩余的Jupyter隧道
    print("\n===== 清理所有 Jupyter 隧道 =====")
    cleared_jupyter = tunnel_manager.clear_service_tunnels("jupyter")
    # print(f"清除的Jupyter隧道数量: {cleared_jupyter}") # 已有成功/失败日志
    
    # 最终清理
    print("\n===== 执行最终清理 =====")
    tunnel_manager.cleanup()
    print("\n===== 测试完成 =====") 