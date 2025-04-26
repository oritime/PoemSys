"""
NPSManager - NPS（NProxy Server）管理工具

这个模块提供了一个用于管理 NPS 服务器的 Python 类，支持客户端和隧道的完整管理功能。
通过 NPSManager 类，你可以执行以下操作：
1. 客户端管理：列出、添加和删除客户端
2. 隧道管理：列出、获取、添加、修改、删除、启动和停止隧道

使用示例:
    from nps_manager import NPSManager
    
    # 初始化
    nps = NPSManager()
    
    # 获取客户端列表
    clients = nps.list_clients()
    
    # 获取隧道列表
    tunnels = nps.list_tunnels(client_id=2)

详细文档请参考 README.md 文件
"""

import requests
import hashlib
import time
import json
import os
from datetime import datetime
from typing import Dict, Optional, Any

class NPSManager:
    def __init__(self, config_file=None, server_addr=None, server_port=None, auth_key=None):
        """
        初始化 NPS Manager
        
        参数:
            config_file: 配置文件路径，默认为 'config/nps_config.json'
            server_addr: NPS 服务器地址，如果提供则覆盖配置文件中的值
            server_port: NPS 服务器 Web 管理端口，如果提供则覆盖配置文件中的值
            auth_key: 配置的 auth_key 用于生成认证签名，如果提供则覆盖配置文件中的值
        """
        # 默认配置
        self.config = {
            "server": {
                "address": "127.0.0.1", # 默认指向本地，安全起见
                "port": 8081
            },
            "auth": {
                "key": "YOUR_NPS_AUTH_KEY" # 需要用户配置
            },
            "api": {
                "timeout": 10,
                "retry_count": 3
            },
            "clients": {
                "default_client_id": 2 # 默认使用的客户端ID
            },
            "nps_version_compatibility": {
                "post_content_type": "application/x-www-form-urlencoded"
            }
        }
        
        # 加载配置文件
        found_config_file = None
        if config_file is None:
            default_paths = [
                "config/nps_config.json",
                os.path.join(os.path.dirname(__file__), "config/nps_config.json")
            ]
            for path in default_paths:
                if os.path.exists(path):
                    config_file = path
                    found_config_file = path
                    break
                    
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    self._update_nested_dict(self.config, file_config)
                    # 保留: 配置加载成功信息
                    print(f"已从 {config_file} 加载NPS配置") 
            except Exception as e:
                # 保留: 配置加载错误信息
                print(f"加载NPS配置文件出错 ({config_file}): {e}") 
        elif found_config_file:
             # 如果尝试找默认文件但找到了无效的
             print(f"警告: 找到NPS配置文件 {found_config_file} 但加载失败。")
        else:
             # 保留: 配置文件不存在警告
             print(f"警告: 未找到NPS配置文件，使用默认配置。请确保配置正确。") 

        # 命令行参数覆盖
        if server_addr:
            self.config["server"]["address"] = server_addr
        if server_port:
            self.config["server"]["port"] = server_port
        if auth_key:
            self.config["auth"]["key"] = auth_key
            
        # 设置服务器 URL 和认证密钥
        self.server_url = f"http://{self.config['server']['address']}:{self.config['server']['port']}"
        self.auth_key = self.config["auth"]["key"]
        self.timeout = self.config["api"]["timeout"]
        self.retry_count = self.config["api"]["retry_count"]
        self.post_content_type = self.config.get("nps_version_compatibility", {}).get("post_content_type", "application/x-www-form-urlencoded")
        
        # 保留: 初始化完成信息
        print(f"NPS Manager 初始化完成，服务器: {self.server_url}") 
        # 检查 auth_key 是否为默认值
        if self.auth_key == "YOUR_NPS_AUTH_KEY":
             # 保留: 配置不完整警告
             print("警告: NPS auth_key 未配置，请在配置文件中设置正确的 auth.key") 
    
    def _update_nested_dict(self, d, u):
        """递归更新嵌套字典"""
        for k, v in u.items():
            if isinstance(v, dict):
                # 如果键不存在或不是字典，直接用 v 替换，而不是尝试合并
                d[k] = self._update_nested_dict(d.get(k, {}), v) 
            else:
                d[k] = v
        return d
    
    def _md5(self, text: str) -> str:
        """计算 MD5 哈希值"""
        return hashlib.md5(text.encode()).hexdigest()

    def _send_request(self, endpoint: str, data: Optional[Dict] = None, method: str = 'POST') -> Optional[Dict]:
        """发送API请求并处理响应 (日志精简版)"""
        url = f"{self.server_url}/{endpoint}"
        headers = {}
        
        timestamp = str(int(time.time()))
        auth_str = f"{self.auth_key}{timestamp}"
        sign = self._md5(auth_str)
        auth_params = {'auth_key': sign, 'timestamp': timestamp}
        
        query_params = auth_params.copy()
        request_body_data = None
        req_method = method.upper()

        # print(f"[NPSManager Debug] Preparing {req_method} request for endpoint: {endpoint}") # 注释掉

        if req_method == 'GET':
            if data:
                query_params.update(data)
            # print(f"[NPSManager] GET request - Query Params: {query_params}") # 注释掉
        elif req_method == 'POST':
            request_body_data = data
            if self.post_content_type == "application/json":
                 headers['Content-Type'] = 'application/json'
                 # print(f"[NPSManager] POST request (JSON) - Query Params: {query_params}") # 注释掉
                 # if request_body_data:
                 #     print(f"[NPSManager] POST request - Body (JSON): {json.dumps(request_body_data)}") # 注释掉
            else:
                 headers['Content-Type'] = 'application/x-www-form-urlencoded'
                 # print(f"[NPSManager] POST request (Form) - Query Params: {query_params}") # 注释掉
                 # if request_body_data:
                 #     print(f"[NPSManager] POST request - Body (Form Data): {request_body_data}") # 注释掉
        else:
            # 保留: 不支持的 HTTP 方法错误
            print(f"[NPSManager] Error: 不支持的 HTTP 方法 '{method}' (Endpoint: {endpoint})") 
            return None

        for attempt in range(self.retry_count):
            # print(f"[NPSManager] Sending {req_method} request to {url} (Attempt {attempt + 1}/{self.retry_count})...") # 注释掉
            try:
                if req_method == 'POST':
                    if self.post_content_type == "application/json":
                         response = requests.post(url, headers=headers, params=query_params, json=request_body_data, timeout=self.timeout)
                    else:
                         response = requests.post(url, headers=headers, params=query_params, data=request_body_data, timeout=self.timeout)
                elif req_method == 'GET':
                    response = requests.get(url, headers=headers, params=query_params, timeout=self.timeout)
                
                # print(f"[NPSManager] Received response: Status Code={response.status_code}") # 注释掉
                # 如果是 4xx 或 5xx 错误，会抛出异常
                response.raise_for_status() 
                
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    try:
                        response_json = response.json()
                        # print(f"[NPSManager] Response JSON: {json.dumps(response_json, indent=2, ensure_ascii=False)}") # 注释掉
                        return response_json
                    except json.JSONDecodeError as e:
                        # 保留: JSON 解析错误
                        print(f"[NPSManager] Error: 解析 NPS 响应 JSON 失败 (Endpoint: {endpoint}): {e}") 
                        print(f"[NPSManager] Raw response text: {response.text[:200]}...") # 显示部分原始文本
                        return {"status": 0, "msg": f"JSON Decode Error: {e}"} 
                else:
                    # 保留: 非 JSON 响应警告
                    print(f"[NPSManager] Warning: NPS 响应 Content-Type 为 '{content_type}'，不是 JSON (Endpoint: {endpoint}).") 
                    # print(f"[NPSManager] Raw response text: {response.text}") # 注释掉
                    # 尝试解释非 JSON 响应
                    if response.status_code == 200 and ("success" in response.text.lower() or "任务下发成功" in response.text): 
                         # print("[NPSManager] Interpreted non-JSON response as success.") # 注释掉
                         return {"status": 1, "msg": "Success (interpreted)"} 
                    else:
                         # 保留: 无法解析的非 JSON 响应错误
                         print(f"[NPSManager] Error: 无法解析的非 JSON 响应或操作失败 (Endpoint: {endpoint}). Response text: {response.text[:100]}...") 
                         return {"status": 0, "msg": f"Non-JSON response or failure: {response.text[:100]}..."}

            except requests.exceptions.Timeout:
                # 保留: 超时错误
                print(f"[NPSManager] Warning: 请求 NPS 超时 (Endpoint: {endpoint}, Timeout={self.timeout}s, Attempt {attempt + 1}/{self.retry_count}).") 
                if attempt == self.retry_count - 1: 
                    print(f"[NPSManager] Error: 请求 NPS 超时，已达最大重试次数 (Endpoint: {endpoint}).") 
                    return None
                time.sleep(1)
            except requests.exceptions.HTTPError as e:
                # 保留: HTTP 错误 (4xx, 5xx)
                print(f"[NPSManager] Error: NPS 返回 HTTP 错误 (Endpoint: {endpoint}, Status: {response.status_code}, Attempt {attempt + 1}/{self.retry_count}): {e}") 
                print(f"[NPSManager] Response Body: {response.text[:200]}...") # 显示部分错误响应体
                if attempt == self.retry_count - 1: 
                    print(f"[NPSManager] Error: NPS HTTP 错误，已达最大重试次数 (Endpoint: {endpoint}).") 
                    return None # 返回 None 表示请求彻底失败
                time.sleep(1) # 重试前等待
            except requests.exceptions.RequestException as e:
                # 保留: 其他请求错误 (连接错误等)
                print(f"[NPSManager] Error: 请求 NPS 失败 (Endpoint: {endpoint}, Attempt {attempt + 1}/{self.retry_count}): {e}") 
                if attempt == self.retry_count - 1: 
                    print(f"[NPSManager] Error: 请求 NPS 失败，已达最大重试次数 (Endpoint: {endpoint}): {e}") 
                    return None
                time.sleep(1)
            except Exception as e:
                # 保留: 未知错误
                print(f"[NPSManager] Error: 请求 NPS 时发生意外错误 (Endpoint: {endpoint}): {e}") 
                return None # 意外错误，不重试
                
        return None # 所有重试失败
    
    # 客户端管理
    def list_clients(self, search="", order="", offset=0, limit=10) -> Optional[Dict]:
        """获取客户端列表 (使用 GET)"""
        endpoint = 'client/list'
        params = {
            "searchkey": search,
            "order": order,
            "offset": offset,
            "limit": limit
        }
        # print(f"[NPSManager] Preparing to list clients with params: {params}") # 注释掉
        response = self._send_request(endpoint, data=params, method='GET')
        # 调用方处理响应
        return response
    
    def add_client(self, remark, vkey, **kwargs) -> bool:
        """添加客户端 (使用 POST)"""
        endpoint = 'client/add'
        params = {
            "remark": remark,
            "vkey": vkey,
            "config_conn_allow": kwargs.get('config_conn_allow', 1),
            "compress": kwargs.get('compress', 1),
            "crypt": kwargs.get('crypt', 0),
            "rate_limit": kwargs.get('rate_limit', ""),
            "flow_limit": kwargs.get('flow_limit', ""),
            "max_conn": kwargs.get('max_conn', ""),
            "max_tunnel": kwargs.get('max_tunnel', ""),
            "u": kwargs.get('u', ""),
            "p": kwargs.get('p', "")
        }
        # print(f"[NPSManager] Preparing to add client with data: {params}") # 注释掉
        response = self._send_request(endpoint, data=params, method='POST')
        success = response is not None and response.get('status') == 1
        if success:
             # 保留: 操作成功信息
             print(f"[NPSManager] 客户端添加成功: 备注='{remark}'") 
        else:
             error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
             # 保留: 操作失败信息
             print(f"[NPSManager] Error: 添加客户端失败: {error_msg}") 
        return success
    
    def delete_client(self, client_id) -> bool:
        """删除客户端 (使用 POST)"""
        endpoint = 'client/del'
        params = {"id": client_id}
        # print(f"[NPSManager] Preparing to delete client {client_id}") # 注释掉
        response = self._send_request(endpoint, data=params, method='POST')
        success = response is not None and response.get('status') == 1
        if success:
             # 保留: 操作成功信息
             print(f"[NPSManager] 客户端删除成功: ID={client_id}") 
        else:
             error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
             # 保留: 操作失败信息
             print(f"[NPSManager] Error: 删除客户端失败: ID={client_id}, 原因: {error_msg}") 
        return success
    
    # 隧道管理
    def list_tunnels(self, client_id: str = '', tunnel_type: str = '', search: str = '', offset: int = 0, limit: int = 100) -> Optional[Dict]:
        """获取隧道列表 (使用 GET)"""
        endpoint = 'index/gettunnel'
        params = {
            'client_id': client_id,
            'type': tunnel_type,
            'searchkey': search,
            'offset': offset,
            'limit': limit
        }
        # print(f"[NPSManager] Preparing to list tunnels with params: {params}") # 注释掉
        response = self._send_request(endpoint, data=params, method='GET')
        return response
    
    def get_tunnel(self, tunnel_id) -> Optional[Dict]:
        """获取单条隧道信息 (使用 GET)"""
        endpoint = 'index/getonetunnel'
        params = {"id": tunnel_id}
        # print(f"[NPSManager] Preparing to get tunnel {tunnel_id}") # 注释掉
        response = self._send_request(endpoint, data=params, method='GET')
        return response
    
    def add_tunnel(self, client_id: int, tunnel_type: str, port: int, target: str, remark: str = '', **kwargs) -> bool:
        """添加隧道 (使用 POST)"""
        endpoint = 'index/add' 
        data = {
            'type': tunnel_type, 
            'client_id': client_id,
            'remark': remark,
            'port': port, 
            'target': target,
        }
        # 合并其他可能的参数 (如密码、strip_pre 等)
        # 过滤掉 None 值，因为 API 可能不允许空值
        data.update({k: v for k, v in kwargs.items() if v is not None}) 
        
        # print(f"[NPSManager] Preparing to add tunnel with data: {data}") # 注释掉
        response = self._send_request(endpoint, data=data, method='POST')
        
        success = response is not None and response.get('status') == 1
        if success:
            # 保留: 操作成功信息
            print(f"[NPSManager] 隧道添加成功: Port={port}, Target={target}, Remark='{remark}'") 
        else:
            error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
            # 保留: 操作失败信息
            print(f"[NPSManager] Error: 添加隧道失败: Port={port}, Target={target}, 原因: {error_msg}") 
        return success
    
    def update_tunnel(self, tunnel_id, **kwargs) -> bool:
        """更新隧道 (使用 POST)"""
        endpoint = 'index/edit'
        # 确保 id 在参数中
        data = kwargs.copy() 
        data['id'] = tunnel_id
        # 过滤掉值为 None 的参数，避免覆盖已有值
        data_to_send = {k: v for k, v in data.items() if v is not None} 
             
        # print(f"[NPSManager] Preparing to update tunnel {tunnel_id} with data: {data_to_send}") # 注释掉
        response = self._send_request(endpoint, data=data_to_send, method='POST')
        
        success = response is not None and response.get('status') == 1
        if success:
            # 保留: 操作成功信息
            print(f"[NPSManager] 隧道更新成功: ID={tunnel_id}") 
        else:
            error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
            # 保留: 操作失败信息
            print(f"[NPSManager] Error: 更新隧道失败: ID={tunnel_id}, 原因: {error_msg}") 
        return success
    
    def delete_tunnel(self, tunnel_id) -> bool:
        """删除隧道 (使用 POST)"""
        endpoint = 'index/del'
        params = {"id": tunnel_id}
        # print(f"[NPSManager] Preparing to delete tunnel {tunnel_id}") # 注释掉
        response = self._send_request(endpoint, data=params, method='POST')
        success = response is not None and response.get('status') == 1
        if success:
             # 保留: 操作成功信息
             print(f"[NPSManager] 隧道删除成功: ID={tunnel_id}") 
        else:
             error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
             # 保留: 操作失败信息
             print(f"[NPSManager] Error: 删除隧道失败: ID={tunnel_id}, 原因: {error_msg}") 
        return success
    
    def start_tunnel(self, tunnel_id) -> bool:
        """启动隧道 (使用 POST)"""
        endpoint = 'index/start'
        params = {"id": tunnel_id}
        # print(f"[NPSManager] Preparing to start tunnel {tunnel_id}") # 注释掉
        response = self._send_request(endpoint, data=params, method='POST')
        success = response is not None and response.get('status') == 1
        if success:
             # 保留: 操作成功信息
             print(f"[NPSManager] 隧道启动成功: ID={tunnel_id}") 
        else:
             error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
             # 保留: 操作失败信息
             print(f"[NPSManager] Error: 启动隧道失败: ID={tunnel_id}, 原因: {error_msg}") 
        return success
    
    def stop_tunnel(self, tunnel_id) -> bool:
        """停止隧道 (使用 POST)"""
        endpoint = 'index/stop'
        params = {"id": tunnel_id}
        # print(f"[NPSManager] Preparing to stop tunnel {tunnel_id}") # 注释掉
        response = self._send_request(endpoint, data=params, method='POST')
        success = response is not None and response.get('status') == 1
        if success:
             # 保留: 操作成功信息
             print(f"[NPSManager] 隧道停止成功: ID={tunnel_id}") 
        else:
             error_msg = response.get('msg', 'Unknown error') if response else 'Request failed or no response'
             # 保留: 操作失败信息
             print(f"[NPSManager] Error: 停止隧道失败: ID={tunnel_id}, 原因: {error_msg}") 
        return success
    
    @classmethod
    def create_default_config(cls, config_path="config/nps_config.json", overwrite=False):
        """
        创建默认配置文件
        
        参数:
            config_path: 配置文件路径
            overwrite: 是否覆盖已存在的配置文件
            
        返回:
            成功返回 True，失败返回 False
        """
        if os.path.exists(config_path) and not overwrite:
            # 保留: 文件已存在信息
            print(f"NPS 配置文件 {config_path} 已存在，跳过创建。") 
            return False
            
        # 确保目录存在
        try:
             os.makedirs(os.path.dirname(config_path), exist_ok=True)
        except Exception as e:
             # 保留: 目录创建失败错误
             print(f"创建配置目录失败 ({os.path.dirname(config_path)}): {e}") 
             return False
        
        # 创建默认配置
        default_config = {
            "server": {
                "address": "127.0.0.1",
                "port": 8081
            },
            "auth": {
                "key": "YOUR_NPS_AUTH_KEY" # 提示用户修改
            },
            "clients": {
                "default_client_id": 2
            },
            "api": {
                "timeout": 10,
                "retry_count": 3
            },
            "nps_version_compatibility": {
                "post_content_type": "application/x-www-form-urlencoded"
            }
        }
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            # 保留: 文件创建成功信息
            print(f"已创建默认 NPS 配置文件: {config_path}，请修改 auth.key") 
            return True
        except Exception as e:
            # 保留: 文件创建失败错误
            print(f"创建 NPS 配置文件失败 ({config_path}): {e}") 
            return False


# 测试代码
if __name__ == "__main__":
    # 确保测试前 config 目录存在
    if not os.path.exists("config"):
         os.makedirs("config")
    # 检查是否存在配置文件，不存在则创建
    if not os.path.exists("config/nps_config.json"):
        print("未找到 NPS 配置文件，创建默认配置...")
        NPSManager.create_default_config()
    
    # 使用配置文件初始化
    print("初始化 NPSManager...")
    try:
         nps = NPSManager()
    except Exception as e:
         print(f"初始化 NPSManager 失败: {e}")
         print("请确保 NPS 服务正在运行且配置文件正确。")
         exit()
    
    # 获取默认客户端ID
    default_client_id = nps.config.get("clients", {}).get("default_client_id")
    if not default_client_id:
         print("错误: 配置文件中未找到 default_client_id，无法继续测试")
         exit()
    print(f"将使用默认客户端 ID: {default_client_id}")
    
    print("\n===== 1. 测试客户端管理 =====")
    # 1.1 获取客户端列表
    print("\n1.1 获取客户端列表:")
    clients_response = nps.list_clients()
    client_id_to_use = default_client_id # 默认使用配置的 ID
    if clients_response and 'rows' in clients_response:
        print(f"  获取到 {len(clients_response['rows'])} 个客户端")
        # 尝试找到默认 ID 对应的客户端信息
        found_default = False
        for client_info in clients_response['rows']:
             if client_info.get('Id') == default_client_id:
                  print(f"  找到默认客户端: ID={default_client_id}, 备注='{client_info.get('Remark')}'")
                  found_default = True
                  break
        if not found_default:
             print(f"  警告: 未在列表中找到 ID={default_client_id} 的客户端")
    else:
        print(f"  获取客户端列表失败或列表为空")
    
    print("\n===== 2. 测试隧道管理 =====")
    test_tunnel_id = None # 用于存储测试隧道的 ID
    
    # 2.1 测试添加隧道
    print("\n2.1 测试添加隧道 (TCP):")
    target_ip = "192.168.1.200" # 替换为你的测试目标 IP
    target_port = 8080
    tunnel_remark = f"NPSManager_Test_{int(time.time())}"
    add_success = nps.add_tunnel(
        client_id=client_id_to_use,
        tunnel_type="tcp",
        port=19999, # 使用一个临时端口，确保不冲突
        target=f"{target_ip}:{target_port}",
        remark=tunnel_remark
    )
    
    if add_success:
        # 为了获取 ID，需要重新列出隧道并查找
        time.sleep(1) # 等待 NPS 更新
        tunnels = nps.list_tunnels(client_id=client_id_to_use, search=tunnel_remark)
        if tunnels and 'rows' in tunnels and len(tunnels['rows']) > 0:
            test_tunnel_id = tunnels['rows'][0]['Id']
            print(f"  隧道添加成功，获取到 ID: {test_tunnel_id}")
        else:
            print(f"  隧道可能已添加，但无法通过备注 '{tunnel_remark}' 找回 ID")
    else:
        print(f"  添加隧道失败")

    # 2.2 获取隧道列表
    print(f"\n2.2 获取客户端 ID={client_id_to_use} 的隧道列表:")
    tunnels = nps.list_tunnels(client_id=client_id_to_use)
    if tunnels and 'rows' in tunnels:
        tunnel_count = len(tunnels['rows'])
        print(f"  找到 {tunnel_count} 条隧道")
    else:
        print(f"  获取隧道列表失败或列表为空")

    # 如果成功创建了测试隧道，则继续测试
    if test_tunnel_id:
        # 2.3 获取隧道详细信息
        print(f"\n2.3 获取隧道 ID={test_tunnel_id} 的详细信息:")
        tunnel_info = nps.get_tunnel(test_tunnel_id)
        if tunnel_info and tunnel_info.get('code') == 1 and 'data' in tunnel_info:
            print(f"  隧道详细信息获取成功")
            tunnel_data = tunnel_info['data']
            print(f"    端口: {tunnel_data.get('Port')}, 状态: {tunnel_data.get('Status')}, 目标: {tunnel_data.get('Target', {}).get('TargetStr')}")
            
            # 2.4 测试修改隧道 (修改备注)
            print(f"\n2.4 测试修改隧道 ID={test_tunnel_id} (修改备注):")
            new_remark = f"NPSManager_Test_Updated_{int(time.time())}"
            update_success = nps.update_tunnel(tunnel_id=test_tunnel_id, remark=new_remark)
            if update_success:
                 # 验证修改
                 time.sleep(1)
                 updated_info = nps.get_tunnel(test_tunnel_id)
                 if updated_info and updated_info.get('code') == 1 and updated_info['data'].get('Remark') == new_remark:
                      print(f"  隧道备注修改并验证成功: '{new_remark}'")
                 else:
                      print(f"  隧道备注修改成功，但验证失败")
            else:
                 print(f"  隧道修改失败")

            # 2.5 测试停止隧道
            print(f"\n2.5 测试停止隧道 ID={test_tunnel_id}:")
            stop_success = nps.stop_tunnel(test_tunnel_id)
            print(f"  停止隧道结果: {'成功' if stop_success else '失败'}")

            # 2.6 测试启动隧道
            print(f"\n2.6 测试启动隧道 ID={test_tunnel_id}:")
            start_success = nps.start_tunnel(test_tunnel_id)
            print(f"  启动隧道结果: {'成功' if start_success else '失败'}")

            # 2.7 测试删除隧道
            print(f"\n2.7 测试删除隧道 ID={test_tunnel_id}:")
            delete_success = nps.delete_tunnel(test_tunnel_id)
            print(f"  删除隧道结果: {'成功' if delete_success else '失败'}")
            if delete_success:
                 # 验证删除
                 time.sleep(1)
                 deleted_info = nps.get_tunnel(test_tunnel_id)
                 if deleted_info and deleted_info.get('code') == 0: # 假设获取不到算成功删除
                      print(f"  隧道删除验证成功 (无法获取 ID {test_tunnel_id})")
                 else:
                      print(f"  隧道删除成功，但验证失败 (仍能获取到信息或获取时出错)")
                      print(f"    获取结果: {deleted_info}")
        else:
            print(f"  获取隧道 ID={test_tunnel_id} 详细信息失败，跳过后续修改/删除测试")
    else:
        print("\n跳过隧道修改/停止/启动/删除测试 (因为未成功添加或获取测试隧道 ID)")

    print("\n===== 测试完成 =====")
    print("NPSManager 类功能测试总结:")
    print("1. 客户端管理: 可获取客户端列表")
    print("2. 隧道管理: 可获取隧道列表、查看隧道详情、修改隧道信息")
    print("3. 配置管理: 从配置文件加载配置信息，支持灵活配置") 