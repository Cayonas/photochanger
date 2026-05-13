# PhotoChanger

基于 `PRD.md` 实现的在线图片格式转换工具原型。

## 当前进度

- 已完成：Sprint 1 + Sprint 2 的开发版
  - Vue 前端工作台
  - 单文件与多文件上传
  - 输出格式、质量、尺寸、EXIF 设置
  - 队列状态与总体进度
  - 批量完成后 ZIP 下载
- 未完成：Redis 队列、数据库、账户体系、Webhook、计费

## 技术选型

- 后端：FastAPI
- 图片处理：Pillow
- 前端：Vue 3 + Vite
- 存储：本地文件系统（开发环境）

## 启动方式

先构建前端：

```powershell
cd frontend
npm install --cache .npm-cache
npm run build
```

再启动后端：

```powershell
cd ..
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload
```

访问 `http://127.0.0.1:8000`。

前端开发模式：

```powershell
cd frontend
npm run dev
```

## 目录结构

```text
backend/
  app/
    main.py
    services/converter.py
  storage/
frontend/
  src/
  dist/
docs/
  development-plan.md
```
