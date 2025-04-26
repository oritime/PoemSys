#!/usr/bin/env python3

import sys
import json
import requests
from nps_manager import NPSManager

# 默认配置
SERVER_ADDR = "121.199.18.76"
SERVER_PORT = 8081
AUTH_KEY = "55ee6338f59c89d6ec04c9dc04a6bf0abJHSA"  # 替换为你的 AUTH_KEY

def main():
    # 初始化 NPS 管理器
    nps = NPSManager(
        server_addr=SERVER_ADDR,
        server_port=SERVER_PORT,
        auth_key=AUTH_KEY
    )
    
    if len(sys.argv) < 2:
        print("用法: python test_nps.py [命令]")
        print("可用命令:")
        print("  list_clients - 列出所有客户端")
        print("  list_tunnels [客户端ID] - 列出所有隧道，可选指定客户端ID")
        print("  check_tunnel [端口] - 检查指定端口的隧道是否存在")
        print("  get_tunnel_id [端口] - 通过端口查找隧道ID")
        print("  add_client [备注] [vkey] - 添加客户端")
        print("  delete_client [客户端ID] - 删除客户端")
        print("  add_tunnel [客户端ID] [端口] [目标地址] [备注] - 添加隧道")
        print("  delete_tunnel [隧道ID] - 删除隧道")
        print("  start_tunnel [隧道ID] - 启动隧道")
        print("  stop_tunnel [隧道ID] - 停止隧道")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "list_clients":
        result = nps.list_clients()
        print_json(result)
        if result and "rows" in result and result["rows"]:
            print("\n客户端ID列表:")
            for client in result["rows"]:
                print(f"ID: {client['Id']}, 备注: {client['Remark']}, 状态: {'在线' if client['IsConnect'] else '离线'}")
    
    elif command == "list_tunnels":
        client_id = ""
        if len(sys.argv) > 2:
            client_id = sys.argv[2]
        
        result = nps.list_tunnels(client_id=client_id)
        print_json(result)
    
    elif command == "check_tunnel":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py check_tunnel [端口]")
            sys.exit(1)
            
        port = sys.argv[2]
        print(f"检查端口 {port} 的隧道...")
        
        # 创建 session 并登录
        session = requests.Session()
        login_data = {
            "username": "admin",
            "password": "oritime123"
        }
        
        login_response = session.post(
            f"http://{SERVER_ADDR}:{SERVER_PORT}/login/verify",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code == 200:
            print("登录成功，检查隧道...")
            
            # 获取TCP隧道页面
            tcp_response = session.get(f"http://{SERVER_ADDR}:{SERVER_PORT}/index/tcp")
            
            if tcp_response.status_code == 200:
                html = tcp_response.text
                
                # 保存 HTML 以便查看
                with open(f"nps_check_tunnel_{port}.html", "w") as f:
                    f.write(html)
                print(f"已保存 HTML 到 nps_check_tunnel_{port}.html 文件中")
                
                # 检查 HTML 中是否包含指定端口
                import re
                
                # 尝试多种正则表达式找端口
                found = False
                patterns = [
                    f'<td[^>]*>{port}</td>',  # 标准表格单元格
                    f'>{port}<',               # 端口在标签之间
                    f'端口[：:]\s*{port}',      # 中文描述
                    f'port[：:]\s*{port}',     # 英文描述
                ]
                
                for pattern in patterns:
                    if re.search(pattern, html):
                        found = True
                        print(f"✅ 使用模式 '{pattern}' 找到端口 {port}!")
                        break
                        
                if found:
                    # 尝试查找该端口的相关信息
                    # 更强大的行匹配模式，尝试查找包含该端口的表格行
                    row_patterns = [
                        r'<tr[^>]*>.*?' + port + r'.*?</tr>',  # 宽松模式
                        r'<tr[^>]*>(.*?<td[^>]*>' + port + r'</td>.*?)</tr>',  # 更具体的匹配
                    ]
                    
                    for pattern in row_patterns:
                        port_row = re.search(pattern, html, re.DOTALL)
                        if port_row:
                            # 提取所有单元格
                            cells = re.findall(r'<td[^>]*>(.*?)</td>', port_row.group(0), re.DOTALL)
                            if cells:
                                print("找到包含该端口的行，单元格内容：")
                                for i, cell in enumerate(cells):
                                    # 移除 HTML 标签
                                    cell_content = re.sub(r'<[^>]*>', '', cell).strip()
                                    print(f"  单元格 {i}: {cell_content}")
                                break
                else:
                    print(f"❌ 端口 {port} 的隧道不存在，尝试了所有匹配模式。")
            else:
                print(f"获取隧道列表失败: {tcp_response.status_code}")
        else:
            print(f"登录失败: {login_response.status_code}")

    elif command == "get_tunnel_id":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py get_tunnel_id [端口]")
            sys.exit(1)
            
        port = sys.argv[2]
        print(f"查找端口 {port} 对应的隧道ID...")
        
        # 创建 session 并登录
        session = requests.Session()
        login_data = {
            "username": "admin",
            "password": "oritime123"
        }
        
        login_response = session.post(
            f"http://{SERVER_ADDR}:{SERVER_PORT}/login/verify",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code == 200:
            print("登录成功，查找隧道ID...")
            
            # 获取TCP隧道页面
            tcp_response = session.get(f"http://{SERVER_ADDR}:{SERVER_PORT}/index/tcp")
            
            if tcp_response.status_code == 200:
                html = tcp_response.text
                
                # 保存 HTML 以便查看
                with open(f"nps_get_tunnel_id_{port}.html", "w") as f:
                    f.write(html)
                print(f"已保存 HTML 到 nps_get_tunnel_id_{port}.html 文件中")
                
                # 尝试提取隧道ID
                import re
                
                # 适应各种不同的 HTML 结构
                tunnel_id_found = False
                
                # 尝试方法1: 查找包含端口的行，提取ID
                port_row = re.search(r'<tr[^>]*>.*?<td[^>]*>(\d+)</td>.*?' + port + r'.*?</tr>', html, re.DOTALL)
                if port_row:
                    tunnel_id = port_row.group(1)
                    print(f"✅ 找到端口 {port} 对应的隧道ID: {tunnel_id}")
                    tunnel_id_found = True
                
                # 尝试方法2: 查找隧道ID通过开始/停止按钮的URL
                if not tunnel_id_found:
                    port_row = re.search(r'<tr[^>]*>.*?' + port + r'.*?</tr>', html, re.DOTALL)
                    if port_row:
                        # 查找停止按钮的URL，通常包含ID
                        stop_url = re.search(r'href="[^"]*?/index/stop/(\d+)"', port_row.group(0))
                        if stop_url:
                            tunnel_id = stop_url.group(1)
                            print(f"✅ 通过操作按钮找到端口 {port} 对应的隧道ID: {tunnel_id}")
                            tunnel_id_found = True
                
                # 尝试方法3: 查找包含ID和端口的编辑按钮
                if not tunnel_id_found:
                    edit_url = re.search(r'href="[^"]*?/index/edit/(\d+)"[^>]*>.*?<tr[^>]*>.*?' + port + r'.*?</tr>', html, re.DOTALL)
                    if edit_url:
                        tunnel_id = edit_url.group(1)
                        print(f"✅ 通过编辑按钮找到端口 {port} 对应的隧道ID: {tunnel_id}")
                        tunnel_id_found = True
                
                # 如果都没找到，尝试解析整个页面找ID和端口的关联
                if not tunnel_id_found:
                    # 提取所有隧道行
                    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
                    for row in rows:
                        # 检查这一行是否包含我们要找的端口
                        if port in row:
                            # 尝试提取ID（通常是第一列）
                            id_match = re.search(r'<td[^>]*>(\d+)</td>', row)
                            if id_match:
                                tunnel_id = id_match.group(1)
                                print(f"✅ 通过表格行分析找到端口 {port} 对应的隧道ID: {tunnel_id}")
                                tunnel_id_found = True
                                break
                
                if not tunnel_id_found:
                    print(f"❌ 未能找到端口 {port} 对应的隧道ID")
                    print("请尝试手动查看网页或HTML文件确认隧道ID")
            else:
                print(f"获取隧道列表失败: {tcp_response.status_code}")
        else:
            print(f"登录失败: {login_response.status_code}")

    elif command == "add_client":
        if len(sys.argv) < 4:
            print("用法: python test_nps.py add_client [备注] [vkey]")
            sys.exit(1)
        
        remark = sys.argv[2]
        vkey = sys.argv[3]
        
        result = nps.add_client(remark=remark, vkey=vkey)
        print(f"添加客户端结果: {result}")
        
        # 如果添加成功，立即列出客户端以查看新客户端的ID
        if result:
            print("\n刚添加的客户端应该在下面的列表中:")
            clients = nps.list_clients()
            if clients and "rows" in clients:
                for client in clients["rows"]:
                    if client["Remark"] == remark:
                        print(f"新客户端 ID: {client['Id']}, 备注: {client['Remark']}")
    
    elif command == "delete_client":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py delete_client [客户端ID]")
            sys.exit(1)
        
        client_id = sys.argv[2]
        
        result = nps.delete_client(client_id)
        print(f"删除客户端结果: {result}")
    
    elif command == "add_tunnel":
        if len(sys.argv) < 6:
            print("用法: python test_nps.py add_tunnel [客户端ID] [端口] [目标地址] [备注]")
            sys.exit(1)
        
        client_id = sys.argv[2]
        port = sys.argv[3]
        target = sys.argv[4]
        remark = sys.argv[5]
        
        # 确保客户端 ID 是数字
        try:
            client_id = int(client_id)
        except ValueError:
            print(f"警告：客户端ID应该是数字，当前值: {client_id}")
        
        result = nps.add_tunnel(
            client_id=client_id,
            tunnel_type="tcp",  # 默认使用 TCP 类型
            port=port,
            target=target,
            remark=remark
        )
        print(f"添加隧道结果: {result}")
        
        # 添加成功后，检查这个端口的隧道是否存在
        if result:
            print(f"\n检查端口 {port} 的隧道是否添加成功...")
            
            # 创建 session 并登录
            session = requests.Session()
            login_data = {
                "username": "admin",
                "password": "oritime123"
            }
            
            login_response = session.post(
                f"http://{SERVER_ADDR}:{SERVER_PORT}/login/verify",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if login_response.status_code == 200:
                print("登录成功，检查隧道...")
                
                # 获取TCP隧道页面
                tcp_response = session.get(f"http://{SERVER_ADDR}:{SERVER_PORT}/index/tcp")
                
                if tcp_response.status_code == 200:
                    html = tcp_response.text
                    
                    # 保存 HTML 以便查看
                    with open(f"nps_add_tunnel_{port}.html", "w") as f:
                        f.write(html)
                    print(f"已保存 HTML 到 nps_add_tunnel_{port}.html 文件中")
                    
                    # 检查 HTML 中是否包含指定端口
                    import re
                    
                    # 尝试多种正则表达式找端口
                    found = False
                    patterns = [
                        f'<td[^>]*>{port}</td>',  # 标准表格单元格
                        f'>{port}<',               # 端口在标签之间
                        f'端口[：:]\s*{port}',      # 中文描述
                        f'port[：:]\s*{port}',     # 英文描述
                    ]
                    
                    for pattern in patterns:
                        if re.search(pattern, html):
                            found = True
                            print(f"✅ 使用模式 '{pattern}' 找到端口 {port}!")
                            break
                            
                    if found:
                        # 尝试查找该端口的相关信息
                        # 更强大的行匹配模式，尝试查找包含该端口的表格行
                        row_patterns = [
                            r'<tr[^>]*>.*?' + port + r'.*?</tr>',  # 宽松模式
                            r'<tr[^>]*>(.*?<td[^>]*>' + port + r'</td>.*?)</tr>',  # 更具体的匹配
                        ]
                        
                        for pattern in row_patterns:
                            port_row = re.search(pattern, html, re.DOTALL)
                            if port_row:
                                # 提取所有单元格
                                cells = re.findall(r'<td[^>]*>(.*?)</td>', port_row.group(0), re.DOTALL)
                                if cells:
                                    print("找到包含该端口的行，单元格内容：")
                                    for i, cell in enumerate(cells):
                                        # 移除 HTML 标签
                                        cell_content = re.sub(r'<[^>]*>', '', cell).strip()
                                        print(f"  单元格 {i}: {cell_content}")
                                    break
                    else:
                        print(f"❌ 端口 {port} 的隧道未找到，添加可能失败或需要刷新页面。")
                        
                        # 提供建议
                        print("\n可能的原因:")
                        print("1. 添加成功但网页需要刷新才能显示")
                        print("2. 客户端不在线，隧道未显示")
                        print("3. 添加成功但隧道ID尚未分配")
                        print("4. 添加操作实际失败，尽管API返回成功")
                        
                        print("\n建议操作:")
                        print("- 手动刷新NPS管理面板查看")
                        print("- 确保客户端处于在线状态")
                        print("- 等待几秒后再次检查")
                        print("- 使用 check_tunnel 命令再次检查: python test_nps.py check_tunnel " + port)
                else:
                    print(f"获取隧道列表失败: {tcp_response.status_code}")
            else:
                print(f"登录失败: {login_response.status_code}")
    
    elif command == "delete_tunnel":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py delete_tunnel [隧道ID]")
            sys.exit(1)
        
        tunnel_id = sys.argv[2]
        
        result = nps.delete_tunnel(tunnel_id)
        print(f"删除隧道结果: {result}")
    
    elif command == "start_tunnel":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py start_tunnel [隧道ID]")
            sys.exit(1)
        
        tunnel_id = sys.argv[2]
        
        result = nps.start_tunnel(tunnel_id)
        print(f"启动隧道结果: {result}")
    
    elif command == "stop_tunnel":
        if len(sys.argv) < 3:
            print("用法: python test_nps.py stop_tunnel [隧道ID]")
            sys.exit(1)
        
        tunnel_id = sys.argv[2]
        
        result = nps.stop_tunnel(tunnel_id)
        print(f"停止隧道结果: {result}")
    
    else:
        print(f"未知命令: {command}")
        sys.exit(1)

def print_json(data):
    """美化打印 JSON 数据"""
    if data is None:
        print("请求失败，无数据返回")
        return
    
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 