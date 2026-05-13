# PhotoChanger

基于 `FastAPI + Vue 3 + Pillow` 的在线图片格式转换工具，支持单图转换、批量处理、ZIP 打包下载，以及 HEIC/HEIF 图片导入。

## 目前版本功能

- 支持上传格式：`JPEG`、`JPG`、`PNG`、`WebP`、`HEIC`
- 支持输出格式：`JPEG`、`PNG`、`WebP`、`GIF`
- 支持质量调节
- 支持按宽度或高度缩放
- 支持保留 EXIF
- 支持前端多文件队列与并发处理
- 支持单文件结果下载
- 支持批量结果打包为 ZIP 下载
- 支持 HEIC/HEIF 解码与转换

## 当前后端存储与限制

这是当前版本最重要的运行约束，和之前版本不同：

- 单文件转换结果不落盘，保存在后端内存中，并通过下载接口直接流式返回
- 批量下载时才会生成 ZIP 文件，ZIP 临时存放在 `backend/storage/batches/`
- 转换任务结果和批量 ZIP 都会在 30 分钟后过期
- 后端每 60 秒执行一次清理任务，删除过期残留数据
- 单文件上传大小限制为 `50MB`
- 后端总转换并发上限为 `4`
- 当并发已满时，接口会返回 `429 Too Many Requests`

## 技术栈

- 前端：Vue 3
- 前端构建：Vite
- 前端请求：Fetch API
- 后端：FastAPI
- 图片处理：Pillow
- HEIC 支持：pillow-heif
- 批量打包：Python `zipfile`

## 项目结构

```text
backend/
  app/
    main.py
    services/
      converter.py
  requirements.txt
  storage/
    batches/
    results/
    uploads/
frontend/
  src/
    App.vue
    main.js
    styles.css
  dist/
  package.json
  vite.config.js
docs/
  development-plan.md
  system-implementation-overview.md
```

说明：

- `backend/storage/batches/`：批量下载生成的临时 ZIP 文件目录
- `backend/storage/results/`：当前实现已不再使用，可视为历史目录
- `backend/storage/uploads/`：当前实现未持久化保存原始上传文件

## 本地启动

### 1. 创建虚拟环境

```powershell
python -m venv .venv
```

### 2. 安装后端依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 3. 安装前端依赖

```powershell
cd frontend
npm install --cache .npm-cache
```

### 4. 构建前端

```powershell
npm run build
```

### 5. 启动后端服务

```powershell
cd ..
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 前端开发模式

如果只调试前端页面，可以运行：

```powershell
cd frontend
npm run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

如果配置了 Vite 代理，前端开发环境可将 `/api` 请求转发到本地 FastAPI 服务。

## 主要接口

### `GET /api/health`

健康检查接口。

### `POST /api/v1/convert`

上传并转换单张图片。

表单字段：

- `file`
- `target_format`
- `quality`
- `width`
- `height`
- `keep_exif`

成功后返回任务信息和下载地址。

### `GET /api/v1/tasks/{task_id}`

获取单图转换任务状态。

### `GET /api/v1/tasks/{task_id}/result`

下载单图转换结果。结果由后端以内存流的方式返回，不落磁盘。

### `POST /api/v1/batches`

根据多个 `task_id` 生成 ZIP 批量下载包。

### `GET /api/v1/batches/{batch_id}`

获取批量打包任务状态。

### `GET /api/v1/batches/{batch_id}/result`

下载批量 ZIP 文件。