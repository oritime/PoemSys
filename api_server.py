#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import timedelta, datetime
import uvicorn
import time

from container_manager import DockerContainerManager, load_config
from dynamic_tunnel_manager import DynamicTunnelManager
from auth import authenticate_user, create_access_token, get_current_user, JWT_SETTINGS

app = FastAPI(title="GPU Container Management API")

try:
    tunnel_manager = DynamicTunnelManager()
except Exception as e:
    print(f"Fatal: Failed to initialize DynamicTunnelManager: {e}")
    print("Ensure NPS and Port Manager configs are correct.")
    tunnel_manager = None
    print("Warning: API starting without a functional Tunnel Manager. Tunnel operations will fail.")

if tunnel_manager:
    try:
        manager = DockerContainerManager(tunnel_manager=tunnel_manager)
    except Exception as e:
        print(f"Fatal: Failed to initialize DockerContainerManager: {e}")
        print("Ensure Docker daemon is running and accessible.")
        manager = None
        print("Warning: API starting without a functional Container Manager. Container operations will fail.")
else:
    manager = None

class Token(BaseModel):
    access_token: str
    token_type: str

class ContainerConfig(BaseModel):
    root_password: str = Field(default="password", description="Root password for SSH access")
    jupyter_token: str = Field(default="", description="Jupyter authentication token (empty for no token)")
    jupyter_base_url: str = Field(default="/jupyter", description="Base URL for JupyterLab")
    jupyter_dir: str = Field(default="/root", description="Notebook directory for Jupyter")

class ContainerCreate(BaseModel):
    image: str
    name: str
    config: Optional[ContainerConfig] = None

class PortInfo(BaseModel):
    ssh_port: Optional[int] = None
    jupyter_port: Optional[int] = None
    app_port: Optional[int] = None

class ContainerInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    id: Optional[str] = None
    status: str
    running: bool
    image: Optional[str] = None
    created: Optional[str] = None
    ip_address: Optional[str] = None
    public_ports: Optional[PortInfo] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class SnapshotCreate(BaseModel):
    commit_message: Optional[str] = None

class SnapshotInfo(BaseModel):
    tag: str
    index: int
    created: Optional[str] = None
    size_mb: Optional[float] = None
    message: Optional[str] = None
    id: Optional[str] = None
    found: bool

class ContainerSnapshotList(BaseModel):
    container_name: str
    versions: List[SnapshotInfo]
    
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """获取访问令牌"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=JWT_SETTINGS['access_token_expire_minutes'])
    access_token = create_access_token(
        data={"sub": user['username']}, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

def get_manager() -> DockerContainerManager:
    if manager is None:
        raise HTTPException(status_code=503, detail="Container Manager is not available")
    return manager

@app.post("/containers", response_model=ApiResponse)
async def api_create_container(
    container: ContainerCreate,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """创建新容器"""
    config_dict = None
    if container.config:
        config_dict = container.config.model_dump()
    
    ports_info = manager.create_container(container.image, container.name, config_dict)
    
    if ports_info is None:
        raise HTTPException(status_code=400, detail=f"Failed to create container '{container.name}'. Check logs for details.")
    
    ssh_password = (config_dict or {}).get('root_password', "password")
    jupyter_token = (config_dict or {}).get('jupyter_token', "")
    
    return ApiResponse(
        success=True,
        message=f"Container '{container.name}' created successfully",
        data={
            "name": container.name,
            "public_ports": ports_info,
            "credentials": {
                "ssh_password": ssh_password,
                "jupyter_token": jupyter_token
            }
        }
    )

@app.post("/containers/{name}/stop", response_model=ApiResponse)
async def api_stop_container(
    name: str,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """停止容器 (不创建快照)"""
    success = manager.stop_container(name)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to stop container '{name}'")
    return ApiResponse(
        success=True,
        message=f"Container '{name}' stopped successfully"
    )

@app.post("/containers/{name}/start", response_model=ApiResponse)
async def api_start_container(
    name: str,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """启动已停止的容器 (不通过快照启动)"""
    ports_info = manager.start_container(name)
    if ports_info is None:
        raise HTTPException(status_code=400, detail=f"Failed to start container '{name}'")
    return ApiResponse(
        success=True,
        message=f"Container '{name}' started successfully",
        data={"name": name, "public_ports": ports_info}
    )

@app.delete("/containers/{name}", response_model=ApiResponse)
async def api_remove_container(
    name: str,
    remove_snapshots: bool = False,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """删除容器 (可选删除快照)"""
    success = manager.remove_container(name, remove_snapshots)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to remove container '{name}' or operation partially failed. Check logs.")
    return ApiResponse(
        success=True,
        message=f"Container '{name}' removed successfully" + (" along with its snapshots" if remove_snapshots else "")
    )

@app.get("/containers/{name}", response_model=ContainerInfo)
async def api_get_container_status(
    name: str,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """获取单个容器的详细状态"""
    status_dict = manager.container_status(name)
    if status_dict is None:
        raise HTTPException(status_code=404, detail=f"Container '{name}' not found or failed to get status")
        
    public_ports_data = status_dict.get('public_ports')
    ports_model = PortInfo(**public_ports_data) if public_ports_data else None
    
    status_dict.pop('public_ports', None)
        
    return ContainerInfo(**status_dict, public_ports=ports_model)

@app.get("/containers", response_model=List[ContainerInfo])
async def api_list_containers(
    all_containers: bool = True,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """列出所有管理的容器"""
    containers_data = manager.list_containers(all_containers)
    result_list = []
    for status_dict in containers_data:
        public_ports_data = status_dict.get('public_ports')
        ports_model = PortInfo(**public_ports_data) if public_ports_data else None
        status_dict.pop('public_ports', None)
        result_list.append(ContainerInfo(**status_dict, public_ports=ports_model))
    return result_list

@app.post("/containers/{name}/snapshots", response_model=ApiResponse)
async def api_create_snapshot(
    name: str,
    snapshot_config: SnapshotCreate,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """为正在运行的容器创建快照 (会先停止容器)"""
    snapshot_tag = manager.stop_and_commit(name, snapshot_config.commit_message)
    if snapshot_tag is None:
        raise HTTPException(status_code=400, detail=f"Failed to create snapshot for container '{name}'")
    return ApiResponse(
        success=True,
        message=f"Snapshot '{snapshot_tag}' created successfully for container '{name}'",
        data={"snapshot_tag": snapshot_tag}
    )

@app.post("/containers/{name}/start_from_snapshot", response_model=ApiResponse)
async def api_start_from_snapshot(
    name: str,
    version_tag: Optional[str] = None,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """从指定快照启动容器 (会替换现有同名容器)"""
    ports_info = manager.start_from_snapshot(name, version_tag)
    if ports_info is None:
        raise HTTPException(status_code=400, detail=f"Failed to start container '{name}' from snapshot" + (f" '{version_tag}'" if version_tag else " (latest)"))
    return ApiResponse(
        success=True,
        message=f"Container '{name}' started successfully from snapshot"+ (f" '{version_tag}'" if version_tag else " (latest)"),
        data={"name": name, "public_ports": ports_info}
    )

@app.get("/containers/{name}/snapshots", response_model=List[ContainerSnapshotList])
async def api_list_container_snapshots(
    name: str,
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """列出指定容器的所有快照"""
    snapshots_data = manager.list_snapshots(name)
    if not snapshots_data:
        return []
    return snapshots_data

@app.get("/snapshots", response_model=List[ContainerSnapshotList])
async def api_list_all_snapshots(
    manager: DockerContainerManager = Depends(get_manager),
    current_user: dict = Depends(get_current_user)
):
    """列出所有容器的所有快照"""
    return manager.list_snapshots()

if __name__ == "__main__":
    config = load_config()
    uvicorn_config = config.get('uvicorn', {})
    host = uvicorn_config.get('host', "0.0.0.0")
    port = uvicorn_config.get('port', 8000)
    """自动重载"""
    reload = uvicorn_config.get('reload', False)
    
    print(f"Starting API server on {host}:{port}...")
    uvicorn.run("api_server:app", host=host, port=port, reload=reload)