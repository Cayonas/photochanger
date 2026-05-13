<script setup>
import { computed, onBeforeUnmount, reactive, ref } from "vue";

const settings = reactive({
  targetFormat: "webp",
  quality: 82,
  width: "",
  height: "",
  keepExif: false,
  concurrency: 2,
});

const queue = ref([]);
const globalMessage = ref("把图片拖进来，批量转换和 ZIP 下载已经就绪。");
const isRunning = ref(false);
const batchDownloadUrl = ref("");
const batchSummary = ref(null);

const acceptedTypes = ".png,.jpg,.jpeg,.webp,.gif,.heic,.heif,image/png,image/jpeg,image/webp,image/gif,image/heic,image/heif";
const maxFilesHint = "支持 JPEG / PNG / WebP / GIF / HEIC，单文件限制 50MB。";

const completedCount = computed(() => queue.value.filter((item) => item.status === "completed").length);
const failedCount = computed(() => queue.value.filter((item) => item.status === "failed").length);
const overallProgress = computed(() => {
  if (queue.value.length === 0) {
    return 0;
  }
  return Math.round((completedCount.value / queue.value.length) * 100);
});
const originalCount = computed(() => queue.value.length);
const canConvert = computed(() => queue.value.length > 0 && !isRunning.value);
const completedItems = computed(() => queue.value.filter((item) => item.status === "completed"));

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
      originalMeta: `${file.name} · ${formatBytes(file.size)}`,
      resultMeta: "等待转换",
      outputSizeBytes: 0,
    });
  }

  if (files.length > 0) {
    globalMessage.value = `已加入 ${files.length} 个文件，准备开始转换。`;
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
  globalMessage.value = "正在转换队列中的图片...";

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
    globalMessage.value = `已完成 ${completedCount.value} 个文件，失败 ${failedCount.value} 个。`;
  } else {
    globalMessage.value = "本次没有成功输出文件，请检查输入格式或参数设置。";
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
    item.resultMeta = `${data.output_width} × ${data.output_height} · ${formatBytes(data.output_size_bytes)} · ${data.target_format.toUpperCase()}`;
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
  <main class="shell">
    <section class="poster">
      <div class="poster-copy">
        <p class="eyebrow">PhotoChanger / Sprint 2</p>
        <h1>把图片队列送进同一间数字暗房。</h1>
        <p class="lead">
          前端已经切到 Vue，批量转换和 ZIP 下载也接上了。现在这个工作台更适合继续向异步队列和历史任务扩展。
        </p>
      </div>
      <div class="poster-aside">
        <span>当前模式</span>
        <strong>多文件队列 + ZIP 打包</strong>
        <p>{{ maxFilesHint }}</p>
      </div>
    </section>

    <section class="workspace">
      <div class="controls">
        <label
          class="dropzone"
          @dragover.prevent
          @drop="onDrop"
        >
          <input type="file" multiple :accept="acceptedTypes" hidden @change="onFilePick">
          <span class="dropzone-title">拖拽图片到这里</span>
          <span class="dropzone-copy">或点击选择多个文件</span>
        </label>

        <div class="settings">
          <div class="settings-header">
            <h2>转换设置</h2>
            <p>队列里的文件将复用同一组参数，便于批量处理。</p>
            <p>HEIC 文件可直接上传并转换；受浏览器限制，原图预览可能会显示为占位状态。</p>
          </div>

          <div class="field-grid">
            <label>
              <span>输出格式</span>
              <select v-model="settings.targetFormat">
                <option value="webp">WebP</option>
                <option value="jpeg">JPEG</option>
                <option value="png">PNG</option>
                <option value="gif">GIF</option>
              </select>
            </label>

            <label>
              <span>并发数</span>
              <select v-model.number="settings.concurrency">
                <option :value="1">1</option>
                <option :value="2">2</option>
                <option :value="3">3</option>
              </select>
            </label>

            <label>
              <span>质量 {{ settings.quality }}</span>
              <input v-model.number="settings.quality" type="range" min="1" max="100">
            </label>

            <label>
              <span>宽度</span>
              <input v-model="settings.width" type="number" min="1" placeholder="保持原始">
            </label>

            <label>
              <span>高度</span>
              <input v-model="settings.height" type="number" min="1" placeholder="保持原始">
            </label>

            <label class="toggle">
              <input v-model="settings.keepExif" type="checkbox">
              <span>保留 EXIF 元数据</span>
            </label>
          </div>

          <div class="action-row">
            <button class="primary" :disabled="!canConvert" @click="runBatchConversion">
              {{ isRunning ? "转换中..." : "开始批量转换" }}
            </button>
            <button class="secondary" :disabled="isRunning || queue.length === 0" @click="clearQueue">
              清空队列
            </button>
          </div>
        </div>
      </div>

      <div class="queue-panel">
        <div class="queue-head">
          <div>
            <p class="mini-label">队列概览</p>
            <h2>{{ originalCount }} 个文件</h2>
          </div>
          <div class="progress-copy">
            <strong>{{ overallProgress }}%</strong>
            <span>{{ completedCount }} / {{ originalCount }} 已完成</span>
          </div>
        </div>

        <div class="progress-track">
          <span class="progress-fill" :style="{ width: `${overallProgress}%` }"></span>
        </div>

        <p class="status-line">{{ globalMessage }}</p>

        <div v-if="batchSummary" class="batch-banner">
          <div>
            <span>批量包已生成</span>
            <strong>{{ batchSummary.file_count }} 个文件已归档</strong>
          </div>
          <a class="download" :href="batchDownloadUrl">下载 ZIP</a>
        </div>

        <div class="queue-list">
          <article v-for="item in queue" :key="item.id" class="queue-item">
            <img
              v-if="item.resultUrl || item.previewable"
              class="thumb"
              :src="item.resultUrl || item.localUrl"
              :alt="item.filename"
            >
            <div v-else class="thumb thumb-fallback">HEIC</div>
            <div class="item-copy">
              <div class="item-topline">
                <h3>{{ item.filename }}</h3>
                <button class="remove" :disabled="isRunning" @click="removeItem(item.id)">移除</button>
              </div>
              <p class="meta">{{ item.originalMeta }}</p>
              <p class="meta">{{ item.resultMeta }}</p>
              <p class="badge" :data-state="item.status">
                {{ item.status === "queued" ? "等待中" : item.status === "processing" ? "处理中" : item.status === "completed" ? "已完成" : "失败" }}
              </p>
              <p v-if="item.error" class="error-copy">{{ item.error }}</p>
            </div>
            <a v-if="item.resultUrl" class="inline-download" :href="item.resultUrl" :download="item.downloadName">
              下载
            </a>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>
