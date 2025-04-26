"""
Port Manager - 动态端口管理工具

这个模块提供了端口池管理功能，用于动态分配和回收端口资源。
主要功能:
1. 端口池初始化和配置
2. 端口分配与回收
3. 端口状态查询和管理
4. 端口持久化存储和加载

可以与NPSManager配合使用，实现动态端口映射管理。
"""

import os
import json
import random
import threading
from typing import List, Dict, Optional, Tuple, Set
import time

class PortManager:
    def __init__(self, config_file=None):
        """
        初始化端口管理器
        
        参数:
            config_file: 配置文件路径，默认为 'config/port_config.json'
        """
        # 默认配置
        self.config = {
            "port_range": {
                "start": 10000,  # 端口池起始端口
                "end": 20000     # 端口池结束端口
            },
            "reserved_ports": [80, 443, 22, 8080, 8888],  # 保留端口，不会分配
            "allocation": {
                "strategy": "random",  # random: 随机分配, sequential: 顺序分配
                "prefer_ranges": []
            },
            "persistence": {
                "file": "state/port_allocation.json",  # 确认路径在 config.json 中正确配置
                "auto_save": True,        # 是否自动保存
                "save_interval": 300      # 自动保存间隔(秒)
            }
        }
        
        # 加载配置文件
        if config_file is None:
            default_paths = [
                "config/port_config.json",  # 相对于当前工作目录
                os.path.join(os.path.dirname(__file__), "config/port_config.json")  # 相对于脚本位置
            ]
            
            for path in default_paths:
                if os.path.exists(path):
                    config_file = path
                    break
                    
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    # 使用文件配置更新默认配置
                    self._update_nested_dict(self.config, file_config)
                    print(f"已从 {config_file} 加载端口配置")
            except Exception as e:
                print(f"加载端口配置文件出错: {e}")
        
        # 初始化端口池状态
        self.allocated_ports = {}  # {port: {"service": "ssh", "allocated_time": timestamp, "client_id": 1}}
        self.port_lock = threading.RLock()
        
        # 加载已分配的端口
        self._load_allocated_ports()
        
        # 自动保存线程
        if self.config["persistence"]["auto_save"]:
            interval = self.config["persistence"].get("save_interval", 300)
            if interval > 0:
                self.save_thread = threading.Thread(target=self._auto_save_thread, args=(interval,), daemon=True)
                self.save_thread.start()
                print(f"端口自动保存已启用，间隔: {interval} 秒")
            else:
                 print("端口自动保存已禁用 (save_interval <= 0)")
        else:
             print("端口自动保存已禁用 (auto_save=False)")
        
        print(f"端口管理器初始化完成，可用端口范围: {self.config['port_range']['start']}-{self.config['port_range']['end']}")
    
    def _update_nested_dict(self, d, u):
        """递归更新嵌套字典"""
        for k, v in u.items():
            if isinstance(v, dict):
                # 确保目标也是字典
                current_val = d.get(k, {})
                if not isinstance(current_val, dict):
                    current_val = {}
                d[k] = self._update_nested_dict(current_val, v)
            else:
                d[k] = v
        return d
    
    def _load_allocated_ports(self):
        """加载已分配的端口数据"""
        persistence_file = self.config["persistence"]["file"]
        if os.path.exists(persistence_file):
            try:
                with open(persistence_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, dict):
                         self.allocated_ports = loaded_data
                         print(f"从 {persistence_file} 加载了 {len(self.allocated_ports)} 个已分配端口")
                    else:
                         print(f"加载端口分配数据格式错误，文件内容不是字典: {persistence_file}")
                         self.allocated_ports = {}
            except json.JSONDecodeError as e:
                print(f"加载端口分配数据失败 (JSON 解析错误): {e} 文件: {persistence_file}")
                self.allocated_ports = {}
            except Exception as e:
                print(f"加载端口分配数据失败: {e} 文件: {persistence_file}")
                self.allocated_ports = {}
        else:
             print(f"端口分配文件 {persistence_file} 不存在，初始化为空。")
             self.allocated_ports = {}
    
    def save_allocated_ports(self):
        """保存已分配的端口数据"""
        persistence_file = self.config["persistence"]["file"]
        with self.port_lock:
            try:
                dir_path = os.path.dirname(persistence_file)
                if dir_path:
                     os.makedirs(dir_path, exist_ok=True)
                
                # 确保在持有锁的情况下写入文件
                with open(persistence_file, 'w', encoding='utf-8') as f:
                     json.dump(self.allocated_ports, f, indent=4)
                return True
            except Exception as e:
                print(f"保存端口分配数据失败: {e}")
                return False
    
    def _auto_save_thread(self, interval):
        """自动保存线程"""
        while True:
            time.sleep(interval)
            self.save_allocated_ports()
    
    def get_available_ports(self) -> List[int]:
        """获取所有可用的端口"""
        with self.port_lock:
            all_ports = set(range(self.config["port_range"]["start"], self.config["port_range"]["end"] + 1))
            reserved_ports = set(self.config["reserved_ports"])
            allocated_ports_set = set(int(p) for p in self.allocated_ports.keys() if p.isdigit())
            available = sorted(list(all_ports - reserved_ports - allocated_ports_set))
            return available
    
    def get_used_ports(self) -> Dict[str, Dict]:
        """获取所有已使用的端口及其信息"""
        with self.port_lock:
            copied_data = json.loads(json.dumps(self.allocated_ports))
            return copied_data
    
    def allocate_port(self, service_name: str, client_id: int = None, preferred_port: int = None) -> Optional[int]:
        """
        分配一个端口
        
        参数:
            service_name: 服务名称 (如 "ssh", "http", "jupyter"等)
            client_id: 客户端ID，可选
            preferred_port: 优先分配的端口，如果可用则分配该端口
            
        返回:
            分配的端口号，分配失败返回None
        """
        print(f"[PortManager] 请求分配端口: 服务='{service_name}', 偏好={preferred_port}")
        with self.port_lock:
            allocated_port = None
            
            # 如果指定了优先端口且该端口可用，则分配该端口
            if preferred_port is not None:
                if self._is_port_available(preferred_port):
                    allocated_port = preferred_port
            
            # 如果没有找到合适的优先端口，则按策略分配
            if allocated_port is None:
                available_ports = self.get_available_ports()
                
                if not available_ports:
                    print("[PortManager] Error: 端口池已耗尽，无可用端口")
                    return None
                
                strategy = self.config["allocation"]["strategy"]
    
                if strategy == "sequential":
                    allocated_port = min(available_ports)
                elif strategy == "random":
                    prefer_ranges = self.config["allocation"].get("prefer_ranges", [])
                    preferred_candidate_ports = []
                    if prefer_ranges:
                         valid_ranges = [r for r in prefer_ranges if isinstance(r, dict) and "start" in r and "end" in r]
                         for range_info in valid_ranges:
                             start = range_info["start"]
                             end = range_info["end"]
                             preferred_candidate_ports.extend([p for p in available_ports if start <= p <= end])
                    
                    if preferred_candidate_ports:
                        allocated_port = random.choice(preferred_candidate_ports)
                    elif available_ports:
                        allocated_port = random.choice(available_ports)
                else:
                    print(f"[PortManager] Error: 未知的分配策略 '{strategy}'")
            
            # 如果最终找到了要分配的端口
            if allocated_port is not None:
                self._mark_port_allocated(allocated_port, service_name, client_id)
                self.save_allocated_ports()
                return allocated_port
            else:
                # 无论是优先端口不可用还是策略选择失败
                print("[PortManager] Error: 无法分配合适的端口")
                return None
    
    def release_port(self, port: int) -> bool:
        """
        释放一个已分配的端口
        
        参数:
            port: 要释放的端口号
            
        返回:
            成功返回True，失败返回False
        """
        print(f"[PortManager] 请求释放端口: {port}")
        with self.port_lock:
            port_str = str(port)
            if port_str in self.allocated_ports:
                service_name = self.allocated_ports[port_str].get('service', 'unknown')
                del self.allocated_ports[port_str]
                print(f"[PortManager] 端口 {port} (服务: {service_name}) 已释放")
                self.save_allocated_ports()
                return True
            else:
                print(f"[PortManager] 端口 {port} 未被分配，无需释放")
                return False
    
    def release_ports_by_service(self, service_name: str) -> List[int]:
        """
        释放指定服务的所有端口
        
        参数:
            service_name: 服务名称
            
        返回:
            释放的端口列表
        """
        print(f"[PortManager] 请求释放服务 '{service_name}' 的所有端口")
        released_ports = []
        with self.port_lock:
            ports_to_release = []
            for port_str, info in self.allocated_ports.items():
                if isinstance(info, dict) and info.get("service") == service_name:
                    ports_to_release.append(port_str)
            if ports_to_release:
                 ports_were_released = False
                 for port_str in ports_to_release:
                      if port_str in self.allocated_ports:
                          del self.allocated_ports[port_str]
                          try:
                              released_ports.append(int(port_str))
                              ports_were_released = True
                          except ValueError:
                               print(f"[PortManager Warning] 分配中发现无效端口格式: {port_str}")
                 if ports_were_released:
                     print(f"[PortManager] 服务 {service_name} 的端口已释放: {released_ports}")
                     self.save_allocated_ports()
        return released_ports 
    
    def release_ports_by_client(self, client_id: int) -> List[int]:
        """
        释放指定客户端的所有端口
        
        参数:
            client_id: 客户端ID
            
        返回:
            释放的端口列表
        """
        print(f"[PortManager] 请求释放客户端 ID {client_id} 的所有端口")
        released_ports = []
        with self.port_lock:
            ports_to_release = []
            for port_str, info in self.allocated_ports.items():
                if isinstance(info, dict) and info.get("client_id") == client_id:
                    ports_to_release.append(port_str)
            if ports_to_release:
                 ports_were_released = False
                 for port_str in ports_to_release:
                      if port_str in self.allocated_ports:
                          del self.allocated_ports[port_str]
                          try:
                              released_ports.append(int(port_str))
                              ports_were_released = True
                          except ValueError:
                               print(f"[PortManager Warning] 分配中发现无效端口格式: {port_str}")
                 if ports_were_released:
                     print(f"[PortManager] 客户端 {client_id} 的端口已释放: {released_ports}")
                     self.save_allocated_ports()
        return released_ports 
    
    def get_port_info(self, port: int) -> Optional[Dict]:
        """
        获取端口信息
        
        参数:
            port: 端口号
            
        返回:
            端口信息字典，如果端口未分配则返回None
        """
        with self.port_lock:
            info = self.allocated_ports.get(str(port))
            copied_info = json.loads(json.dumps(info)) if info else None
            return copied_info
    
    def get_port_usage_summary(self) -> Dict[str, Dict]:
        """
        获取端口使用情况的摘要，按服务和客户端 ID 分组计数。
        Returns:
            一个字典，包含按服务和客户端 ID 分组的端口数量统计。
            例如: {'services': {'service_a': 10, 'service_b': 5}, 'clients': {1: 8, 2: 7}}
        """
        service_counts = {}
        client_counts = {}
        with self.port_lock:
            for port_str, info in self.allocated_ports.items():
                if isinstance(info, dict):
                    service = info.get("service")
                    client_id = info.get("client_id")

                    if service:
                        service_counts[service] = service_counts.get(service, 0) + 1
                    
                    if client_id is not None:
                        try:
                            # 确保 client_id 可以作为字典的键 (通常是整数或字符串)
                            client_key = int(client_id) if isinstance(client_id, (int, str)) and str(client_id).isdigit() else str(client_id)
                            client_counts[client_key] = client_counts.get(client_key, 0) + 1
                        except (ValueError, TypeError):
                             # 保留: 客户端ID格式错误警告
                             print(f"[PortManager Warning] 处理端口 {port_str} 的客户端 ID 时遇到无效格式: {client_id}")


        return {"services": service_counts, "clients": client_counts}
    
    def is_port_allocated(self, port: int) -> bool:
        """
        检查端口是否已分配
        
        参数:
            port: 要检查的端口号
            
        返回:
            如果端口已分配则返回True，否则返回False
        """
        with self.port_lock:
            allocated = str(port) in self.allocated_ports
            return allocated
    
    def _is_port_available(self, port: int) -> bool:
        """
        检查端口是否可用 (需要在持有锁的情况下调用)
        
        参数:
            port: 要检查的端口号
            
        返回:
            如果端口可用则返回True，否则返回False
        """
        if not isinstance(port, int):
             print(f"[PortManager Warning] _is_port_available called with non-integer port: {port}")
             return False
             
        if not (self.config["port_range"]["start"] <= port <= self.config["port_range"]["end"]):
            return False
        
        if port in self.config["reserved_ports"]:
            return False
        
        if str(port) in self.allocated_ports:
            return False
        
        return True
    
    def _mark_port_allocated(self, port: int, service_name: str, client_id: int = None):
        """
        标记端口为已分配 (需要在持有锁的情况下调用)
        
        参数:
            port: 端口号
            service_name: 服务名称
            client_id: 客户端ID，可选
        """
        self.allocated_ports[str(port)] = {
            "service": service_name,
            "allocated_time": int(time.time()),
            "client_id": client_id
        }
        print(f"[PortManager] 端口 {port} 已分配给服务 {service_name}" + (f" (客户端 {client_id})" if client_id else ""))

    @classmethod
    def create_default_config(cls, config_path="config/port_config.json", overwrite=False):
        """
        创建默认配置文件
        
        参数:
            config_path: 配置文件路径
            overwrite: 是否覆盖已存在的配置文件
            
        返回:
            成功返回True，失败返回False
        """
        if os.path.exists(config_path) and not overwrite:
            print(f"配置文件 {config_path} 已存在，不覆盖")
            return False
            
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 创建默认配置
        default_config = {
            "port_range": {
                "start": 10000,
                "end": 20000
            },
            "reserved_ports": [80, 443, 22, 8080, 8888],
            "allocation": {
                "strategy": "random",
                "prefer_ranges": []
            },
            "persistence": {
                "file": "state/port_allocation.json",
                "auto_save": True,
                "save_interval": 300
            }
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            print(f"默认端口配置文件已创建: {config_path}")
            return True
        except Exception as e:
            print(f"创建端口配置文件失败: {e}")
            return False


# 测试代码
if __name__ == "__main__":
    # 检查是否存在配置文件，不存在则创建
    if not os.path.exists("config/port_config.json"):
        print("未找到端口配置文件，创建默认配置...")
        PortManager.create_default_config()
    
    # 初始化端口管理器
    port_manager = PortManager()
    
    # 测试端口分配
    print("\n===== 测试端口分配 =====")
    ssh_port = port_manager.allocate_port("ssh", client_id=1)
    http_port = port_manager.allocate_port("http", client_id=1)
    jupyter_port = port_manager.allocate_port("jupyter", client_id=1)
    
    print(f"分配的端口: SSH={ssh_port}, HTTP={http_port}, Jupyter={jupyter_port}")
    
    # 测试端口信息查询
    print("\n===== 测试端口信息查询 =====")
    print(f"SSH端口信息: {port_manager.get_port_info(ssh_port)}")
    
    # 测试可用端口查询
    available_ports = port_manager.get_available_ports()
    print(f"可用端口数量: {len(available_ports)}")
    if len(available_ports) > 0:
        print(f"部分可用端口: {available_ports[:5]}...")
    
    # 测试端口释放
    print("\n===== 测试端口释放 =====")
    port_manager.release_port(ssh_port)
    print(f"端口 {ssh_port} 是否已分配: {port_manager.is_port_allocated(ssh_port)}")
    
    # 测试按服务释放端口
    print("\n===== 测试按服务释放端口 =====")
    released = port_manager.release_ports_by_service("http")
    print(f"释放的HTTP端口: {released}")
    
    # 保存分配状态
    port_manager.save_allocated_ports()
    
    print("\n===== 测试完成 =====") 