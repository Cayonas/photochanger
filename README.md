# PhotoChanger

基于 `PRD.md` 实现的在线图片格式转换工具原型。

## 当前进度

- 已完成：Sprint 1 的最小可运行版本
  - 单文件上传
  - 输出格式选择
  - 质量与尺寸设置
  - EXIF 保留开关
  - 原图/结果预览
  - 转换结果下载
- 未完成：批量队列、ZIP 下载、账户体系、Webhook、计费

## 技术选型

- 后端：FastAPI
- 图片处理：Pillow
- 前端：原生 HTML/CSS/JS（MVP 阶段，后续可替换为 Vue）
- 存储：本地文件系统（开发环境）

## 启动方式

```powershell
uvicorn backend.app.main:app --reload
```

然后访问 `http://127.0.0.1:8000`。

## 目录结构

```text
backend/
  app/
    main.py
    services/converter.py
  storage/
frontend/
  assets/
docs/
  development-plan.md
```
