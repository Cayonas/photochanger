const state = {
  file: null,
  originalPreviewUrl: "",
  resultPreviewUrl: "",
};

const form = document.getElementById("convert-form");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const qualityInput = document.getElementById("quality");
const qualityValue = document.getElementById("quality-value");
const originalPreview = document.getElementById("original-preview");
const resultPreview = document.getElementById("result-preview");
const originalMeta = document.getElementById("original-meta");
const resultMeta = document.getElementById("result-meta");
const message = document.getElementById("message");
const submitButton = document.getElementById("submit-button");
const downloadLink = document.getElementById("download-link");

qualityInput.addEventListener("input", () => {
  qualityValue.textContent = qualityInput.value;
});

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const [file] = event.dataTransfer.files;
  setFile(file);
});
fileInput.addEventListener("change", (event) => {
  const [file] = event.target.files;
  setFile(file);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.file) {
    setMessage("请先选择一张图片。", true);
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "转换中...";
  setMessage("正在上传并转换图片...");
  resultMeta.textContent = "转换中...";

  const payload = new FormData();
  payload.append("file", state.file);
  payload.append("target_format", document.getElementById("target-format").value);
  payload.append("quality", qualityInput.value);

  const width = document.getElementById("width").value;
  const height = document.getElementById("height").value;
  if (width) payload.append("width", width);
  if (height) payload.append("height", height);
  if (document.getElementById("keep-exif").checked) {
    payload.append("keep_exif", "true");
  }

  try {
    const response = await fetch("/api/v1/convert", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "转换失败");
    }

    if (state.resultPreviewUrl) {
      URL.revokeObjectURL(state.resultPreviewUrl);
    }

    const resultBlob = await fetch(data.download_url).then((res) => res.blob());
    state.resultPreviewUrl = URL.createObjectURL(resultBlob);
    resultPreview.src = state.resultPreviewUrl;
    resultMeta.textContent =
      `${data.output_width} × ${data.output_height} · ${formatBytes(data.output_size_bytes)} · ${data.target_format.toUpperCase()}`;
    downloadLink.href = data.download_url;
    downloadLink.classList.remove("disabled");
    setMessage("转换完成，可以下载结果。");
  } catch (error) {
    resultPreview.removeAttribute("src");
    resultMeta.textContent = "转换失败";
    setMessage(error.message || "转换失败，请稍后重试。", true);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "开始转换";
  }
});

function setFile(file) {
  if (!file) {
    return;
  }

  state.file = file;
  if (state.originalPreviewUrl) {
    URL.revokeObjectURL(state.originalPreviewUrl);
  }
  state.originalPreviewUrl = URL.createObjectURL(file);
  originalPreview.src = state.originalPreviewUrl;
  originalPreview.onload = () => {
    originalMeta.textContent =
      `${file.name} · ${originalPreview.naturalWidth} × ${originalPreview.naturalHeight} · ${formatBytes(file.size)}`;
  };
  resultPreview.removeAttribute("src");
  resultMeta.textContent = "等待转换";
  downloadLink.classList.add("disabled");
  downloadLink.href = "#";
  setMessage("文件已加载，可以开始转换。");
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}
