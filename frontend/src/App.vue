<script setup>
import { computed, onBeforeUnmount, reactive, ref } from "vue";

const settings = reactive({
  targetFormat: "webp",
  quality: 90,
  width: "",
  height: "",
  keepExif: false,
  concurrency: 2,
});

const queue = ref([]);
const globalMessage = ref("点击上传图片或拖拽文件到下方区域，即可开始转换。");
const isRunning = ref(false);
const batchDownloadUrl = ref("");
const batchSummary = ref(null);

const acceptedTypes =
  ".png,.jpg,.jpeg,.webp,.gif,.heic,.heif,image/png,image/jpeg,image/webp,image/gif,image/heic,image/heif";
const maxFilesHint = "支持 HEIC、HEIF、PNG、JPG、JPEG、WebP、GIF，单文件最大 50MB。";

const completedCount = computed(() => queue.value.filter((item) => item.status === "completed").length);
const failedCount = computed(() => queue.value.filter((item) => item.status === "failed").length);
const processingCount = computed(() => queue.value.filter((item) => item.status === "processing").length);
const queuedCount = computed(() => queue.value.filter((item) => item.status === "queued").length);
const originalCount = computed(() => queue.value.length);
const completedItems = computed(() => queue.value.filter((item) => item.status === "completed"));
const canConvert = computed(() => queue.value.length > 0 && !isRunning.value);
const overallProgress = computed(() => {
  if (queue.value.length === 0) {
    return 0;
  }

  return Math.round((completedCount.value / queue.value.length) * 100);
});

function onFilePick(event) {
  appendFiles(event.target.files);
  event.target.value = "";
}

function appendFiles(fileList) {
  const files = Array.from(fileList || []);

  for (const file of files) {
    const localUrl = URL.createObjectURL(file);
    queue.value.push({
      id: crypto.randomUUID(),
      file,
      localUrl,
      resultUrl: "",
      taskId: "",
      downloadName: "",
      filename: file.name,
      status: "queued",
      error: "",
      previewable: supportsInlinePreview(file),
      originalMeta: `${formatBytes(file.size)} / ${file.name}`,
      resultMeta: "等待转换",
      outputSizeBytes: 0,
    });
  }

  if (files.length > 0) {
    globalMessage.value = `已添加 ${files.length} 个文件，设置参数后点击“开始转换”。`;
    batchDownloadUrl.value = "";
    batchSummary.value = null;
  }
}

function onDrop(event) {
  event.preventDefault();
  appendFiles(event.dataTransfer?.files);
}

function clearQueue() {
  for (const item of queue.value) {
    URL.revokeObjectURL(item.localUrl);
    if (item.resultUrl) {
      URL.revokeObjectURL(item.resultUrl);
    }
  }

  queue.value = [];
  batchDownloadUrl.value = "";
  batchSummary.value = null;
  globalMessage.value = "队列已清空。";
}

async function runBatchConversion() {
  if (!canConvert.value) {
    return;
  }

  isRunning.value = true;
  batchDownloadUrl.value = "";
  batchSummary.value = null;
  globalMessage.value = "正在转换图片，请稍候...";

  for (const item of queue.value) {
    item.status = "queued";
    item.error = "";
    item.resultMeta = "等待转换";
  }

  const workers = Array.from({ length: Math.min(settings.concurrency, queue.value.length) }, () => workerLoop());
  await Promise.all(workers);

  const taskIds = completedItems.value.map((item) => item.taskId);
  if (taskIds.length > 0) {
    await buildZipArchive(taskIds);
  }

  isRunning.value = false;
  if (completedCount.value > 0) {
    globalMessage.value = `转换完成：成功 ${completedCount.value} 个，失败 ${failedCount.value} 个。`;
  } else {
    globalMessage.value = "没有成功输出文件，请检查格式与参数设置。";
  }
}

async function workerLoop() {
  while (true) {
    const nextItem = queue.value.find((item) => item.status === "queued");
    if (!nextItem) {
      return;
    }

    nextItem.status = "processing";
    nextItem.resultMeta = "转换中";
    await convertSingleItem(nextItem);
  }
}

async function convertSingleItem(item) {
  const payload = new FormData();
  payload.append("file", item.file);
  payload.append("target_format", settings.targetFormat);
  payload.append("quality", String(settings.quality));
  if (settings.width) payload.append("width", settings.width);
  if (settings.height) payload.append("height", settings.height);
  if (settings.keepExif) payload.append("keep_exif", "true");

  try {
    const response = await fetch("/api/v1/convert", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "转换失败");
    }

    const resultBlob = await fetch(data.download_url).then((res) => res.blob());
    if (item.resultUrl) {
      URL.revokeObjectURL(item.resultUrl);
    }

    item.resultUrl = URL.createObjectURL(resultBlob);
    item.taskId = data.task_id;
    item.downloadName = `${item.filename.replace(/\.[^.]+$/, "")}-converted.${data.target_format === "jpeg" ? "jpg" : data.target_format}`;
    item.outputSizeBytes = data.output_size_bytes;
    item.status = "completed";
    item.resultMeta = `${data.target_format.toUpperCase()} / ${data.output_width} x ${data.output_height} / ${formatBytes(data.output_size_bytes)}`;
  } catch (error) {
    item.status = "failed";
    item.error = error.message || "转换失败";
    item.resultMeta = "转换失败";
  }
}

async function buildZipArchive(taskIds) {
  try {
    const response = await fetch("/api/v1/batches", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ task_ids: taskIds }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "ZIP 打包失败");
    }

    batchDownloadUrl.value = data.download_url;
    batchSummary.value = data;
  } catch (error) {
    globalMessage.value = error.message || "ZIP 打包失败";
  }
}

function removeItem(id) {
  const item = queue.value.find((entry) => entry.id === id);
  if (!item || isRunning.value) {
    return;
  }

  URL.revokeObjectURL(item.localUrl);
  if (item.resultUrl) {
    URL.revokeObjectURL(item.resultUrl);
  }
  queue.value = queue.value.filter((entry) => entry.id !== id);
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

function supportsInlinePreview(file) {
  const name = file.name.toLowerCase();
  return !name.endsWith(".heic") && !name.endsWith(".heif");
}

function formatStateLabel(status) {
  if (status === "processing") return "处理中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  return "等待中";
}

onBeforeUnmount(() => {
  for (const item of queue.value) {
    URL.revokeObjectURL(item.localUrl);
    if (item.resultUrl) {
      URL.revokeObjectURL(item.resultUrl);
    }
  }
});
</script>

<template>
  <div class="page">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="brand" href="/">PhotoChanger</a>
        <nav class="nav">
          <a href="#converter">首页</a>
          <a href="#features">功能特色</a>
          <a href="#faq">常见问题</a>
        </nav>
      </div>
    </header>

    <main>
      <section id="converter" class="hero">
        <div class="hero-copy">
          <h1>免费图片格式转换工具</h1>
          <p>
            快速将 HEIC、PNG、JPG、WebP、GIF 图片转换为 JPG、PNG、WebP 或 GIF。
            支持批量处理、尺寸调整、质量控制与 ZIP 打包下载。
          </p>
        </div>

        <div class="hero-badges">
          <span>批量转换</span>
          <span>快速处理</span>
          <span>无需注册</span>
        </div>

        <section class="converter-card">
          <div class="settings-strip">
            <div class="settings-summary">{{ settings.targetFormat }} · {{ settings.quality }}%</div>

            <div class="settings-group">
              <label>输出格式</label>
              <div class="format-switch">
                <button
                  v-for="format in ['webp', 'jpeg', 'png', 'gif']"
                  :key="format"
                  type="button"
                  :class="{ active: settings.targetFormat === format }"
                  @click="settings.targetFormat = format"
                >
                  {{ format === "jpeg" ? "JPG" : format.toUpperCase() }}
                </button>
              </div>
            </div>

            <div class="settings-group">
              <label>转换质量 {{ settings.quality }}%</label>
              <input v-model.number="settings.quality" type="range" min="1" max="100">
            </div>

            <div class="inline-fields">
              <label>
                <span>宽度</span>
                <input v-model="settings.width" type="number" min="1" placeholder="自动">
              </label>
              <label>
                <span>高度</span>
                <input v-model="settings.height" type="number" min="1" placeholder="自动">
              </label>
              <label>
                <span>并发</span>
                <select v-model.number="settings.concurrency">
                  <option :value="1">1</option>
                  <option :value="2">2</option>
                  <option :value="3">3</option>
                </select>
              </label>
            </div>

            <label class="checkbox-row">
              <input v-model="settings.keepExif" type="checkbox">
              <span>保留 EXIF 元数据</span>
            </label>
          </div>

          <label class="upload-zone" @dragover.prevent @drop="onDrop">
            <input type="file" multiple :accept="acceptedTypes" hidden @change="onFilePick">
            <div class="upload-title">点击上传或拖拽图片到此处</div>
            <div class="upload-copy">{{ maxFilesHint }}</div>
            <div class="upload-action">选择文件</div>
          </label>

          <div class="action-row">
            <button class="primary-btn" :disabled="!canConvert" @click="runBatchConversion">
              {{ isRunning ? "正在转换..." : "开始转换" }}
            </button>
            <button class="ghost-btn" :disabled="isRunning || queue.length === 0" @click="clearQueue">
              清空队列
            </button>
          </div>

          <p class="status-copy">{{ globalMessage }}</p>
        </section>
      </section>

      <section v-if="queue.length > 0" class="content-section">
        <h2>转换队列与结果</h2>
        <p class="section-intro">
          当前队列 {{ originalCount }} 个文件，已完成 {{ completedCount }} 个，处理中 {{ processingCount }} 个，失败 {{ failedCount }} 个。
        </p>

        <div class="progress-bar">
          <span :style="{ width: `${overallProgress}%` }"></span>
        </div>

        <div v-if="batchSummary" class="zip-banner">
          <div>
            <strong>ZIP 批量包已生成</strong>
            <p>{{ batchSummary.file_count }} 个文件已归档，可直接下载。</p>
          </div>
          <a class="primary-btn" :href="batchDownloadUrl">下载 ZIP</a>
        </div>

        <div class="result-list">
          <article v-for="item in queue" :key="item.id" class="result-item">
            <img
              v-if="item.resultUrl || item.previewable"
              class="thumb"
              :src="item.resultUrl || item.localUrl"
              :alt="item.filename"
            >
            <div v-else class="thumb thumb-fallback">HEIC</div>

            <div class="result-copy">
              <div class="result-head">
                <h3>{{ item.filename }}</h3>
                <button class="link-btn" :disabled="isRunning" @click="removeItem(item.id)">移除</button>
              </div>
              <p>{{ item.originalMeta }}</p>
              <p>{{ item.resultMeta }}</p>
              <span class="state-pill" :data-state="item.status">{{ formatStateLabel(item.status) }}</span>
              <p v-if="item.error" class="error-text">{{ item.error }}</p>
            </div>

            <a v-if="item.resultUrl" class="ghost-btn inline-btn" :href="item.resultUrl" :download="item.downloadName">
              下载
            </a>
          </article>
        </div>
      </section>

      <section id="features" class="content-section">
        <h2>为什么选择 PhotoChanger？</h2>
        <p class="section-intro">
          一个适合日常和批量图片处理场景的在线转换工具，页面简洁，操作直接，覆盖常见图片格式转换需求。
        </p>

        <div class="feature-grid">
          <article>
            <h3>批量转换</h3>
            <p>一次上传多个文件，统一设置输出格式、质量与尺寸，减少重复操作。</p>
          </article>
          <article>
            <h3>多格式输出</h3>
            <p>支持输出 JPG、PNG、WebP、GIF，适合网页压缩、社媒发布和日常兼容需求。</p>
          </article>
          <article>
            <h3>HEIC 兼容</h3>
            <p>支持 HEIC 与 HEIF 文件导入，便于处理苹果设备拍摄的照片。</p>
          </article>
          <article>
            <h3>结果集中下载</h3>
            <p>支持单文件下载，也支持转换完成后自动生成 ZIP 批量包。</p>
          </article>
          <article>
            <h3>参数更可控</h3>
            <p>可设置输出质量、宽高尺寸与 EXIF 保留策略，满足更细的导出要求。</p>
          </article>
          <article>
            <h3>无需注册</h3>
            <p>打开页面即可开始使用，适合快速处理临时图片任务。</p>
          </article>
        </div>
      </section>

      <section class="content-section steps-section">
        <h2>如何使用 PhotoChanger</h2>
        <p class="section-intro">只需 3 个步骤，即可完成图片转换与下载。</p>

        <div class="steps-grid">
          <article>
            <h3>上传图片</h3>
            <p>拖拽图片或点击上传，支持多文件批量加入队列。</p>
          </article>
          <article>
            <h3>选择输出参数</h3>
            <p>设置目标格式、转换质量、尺寸与是否保留 EXIF 信息。</p>
          </article>
          <article>
            <h3>下载结果</h3>
            <p>转换完成后下载单个文件，或一键下载打包好的 ZIP 结果。</p>
          </article>
        </div>
      </section>

      <section id="faq" class="content-section faq-section">
        <h2>常见问题</h2>

        <div class="faq-list">
          <article>
            <h3>支持哪些输入格式？</h3>
            <p>当前支持 HEIC、HEIF、PNG、JPG、JPEG、WebP、GIF 输入。</p>
          </article>
          <article>
            <h3>可以输出哪些格式？</h3>
            <p>可输出 JPG、PNG、WebP、GIF，适用于不同展示和压缩场景。</p>
          </article>
          <article>
            <h3>可以批量处理吗？</h3>
            <p>可以。你可以一次上传多个文件，系统会按设置好的并发数量逐个处理。</p>
          </article>
          <article>
            <h3>转换后怎么下载？</h3>
            <p>每个结果都支持单独下载，成功文件还可以自动归档为 ZIP 批量下载。</p>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>
