#!/usr/bin/env python3
from container_manager import DockerContainerManager
import time

def test_port_management():
    """测试端口管理功能"""
    manager = DockerContainerManager()
    
    # 测试容器名称
    container_name = "test_container"
    
    print("\n1. 创建容器")
    success = manager.create_container(
        image="ubuntu20.04-cuda12.1-jupyter-v0.1",
        name=container_name,
        container_config={
            'root_password': '123456',
            'jupyter_token': '123456'
        }
    )
    
    if success:
        print("容器创建成功，等待5秒...")
        time.sleep(5)
        
        # 获取分配的端口
        ports = manager.port_pool.get_ports(container_name)
        print(f"分配的端口: {ports}")
        
        print("\n2. 停止容器")
        manager.stop_container(container_name)
        print("等待5秒检查端口释放情况...")
        time.sleep(5)
        
        # 检查端口是否已释放
        ports_after_stop = manager.port_pool.get_ports(container_name)
        print(f"停止后端口状态: {'已释放' if ports_after_stop is None else '未释放'}")
        
        print("\n3. 重新启动容器")
        manager.start_container(container_name)
        print("等待5秒...")
        time.sleep(5)
        
        # 检查新分配的端口
        new_ports = manager.port_pool.get_ports(container_name)
        print(f"重新分配的端口: {new_ports}")
        
        print("\n4. 删除容器")
        manager.remove_container(container_name)
        print("等待5秒检查最终端口释放情况...")
        time.sleep(5)
        
        # 最终检查端口状态
        final_ports = manager.port_pool.get_ports(container_name)
        print(f"最终端口状态: {'已释放' if final_ports is None else '未释放'}")
        
        # 检查端口分配文件
        print("\n5. 检查端口分配文件内容:")
        manager.port_pool._load_allocations()
        print(f"当前分配的端口: {manager.port_pool.allocated_ports}")

if __name__ == "__main__":
    test_port_management() 