# PhotoChanger

基于 `FastAPI + Vue 3 + Pillow` 实现的在线图片格式转换系统。

## 系统功能

- 支持单文件上传与转换
- 支持多文件队列上传与批量处理
- 支持输出格式选择：`JPEG`、`PNG`、`WebP`、`GIF`
- 支持上传格式：`JPEG`、`PNG`、`WebP`、`GIF`、`HEIC`
- 支持压缩质量调整
- 支持按宽度、高度进行尺寸调整
- 支持 EXIF 元数据保留开关
- 支持队列状态展示：等待中、处理中、已完成、失败
- 支持总体进度展示
- 支持单文件结果下载
- 支持批量结果 ZIP 打包下载
- 支持 HEIC 图片解码与转换到现有输出格式

## 技术栈

- 前端框架：Vue 3
- 前端构建工具：Vite
- 前端请求方式：Fetch API
- 后端框架：FastAPI
- 后端语言：Python 3
- 图片处理：Pillow
- HEIC 解码支持：pillow-heif
- 文件存储：本地文件系统
- 批量归档：Python `zipfile`

## 启动方式

### 1. 安装后端依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

如果还没有虚拟环境，可先执行：

```powershell
python -m venv .venv
```

### 2. 安装前端依赖

```powershell
cd frontend
npm install --cache .npm-cache
```

### 3. 构建前端

```powershell
npm run build
```

### 4. 启动后端服务

```powershell
cd ..
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 前端开发模式

如需单独调试前端页面，可运行：

```powershell
cd frontend
npm run dev
```

默认开发地址：

```text
http://127.0.0.1:5173
```

Vite 已代理 `/api` 请求到本地 FastAPI 服务。

## 目录结构

```text
backend/
  app/
    main.py
    services/
      converter.py
  requirements.txt
  storage/
    results/
    batches/
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
