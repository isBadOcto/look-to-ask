# 语音 GPU 加速与验收（0.4.5）

继续使用 faster-whisper 1.2.1 / CTranslate2 4.8.3、medium、中文、beam=5。
0.4.5 的「Language / 语言」仅切换界面；说普通话时仍在语音设置中选择中文，英文界面对应 Recognition language → Chinese。
程序优先尝试 NVIDIA CUDA / float16；没有显卡、缺少运行库、加载失败或推理时 CUDA 报错，自动回退 CPU / int8。
同一轮 GPU 推理错误时丢弃不完整转写，在 CPU 重试一次；之后复用 CPU，不反复重试 GPU。
不改 EyeTrax、注视目标冻结、录音关闭时机或松开后发送规则，音频仍不保存、不上传。

## 当前电脑怎么试

1. 关闭旧程序，运行根目录 `run.cmd`，或安装 `dist/LookToAsk-0.4.5-Setup.exe`。
2. 「API / 语音设置」选择 **medium + 中文**并保存，点击「准备语音模型」。
3. 确认状态显示 **语音模型 medium 已就绪（GPU 加速）**。
4. 按原流程启动摄像头并完成校准。看着目标，按住 **Ctrl+Alt+V**，等录音提示后说完整问题，松开。连续提问三次。
5. 检查原始转写及注视裁剪，确认录音中移动眼睛不改变起始目标。取消一次，再试新的问题。
6. 内存诊断 `asr_completed` 应有 `speech_device=cuda`、`speech_compute=float16` 和 `asr_ms`。
   GPU 回退时显示 CPU，日志 `speech_fallback` 只记录固定代码，没有底层错误内容或路径。

本轮已为当前电脑安装可选运行库，无需再次下载，模型缓存保持原位置。
初次模型加载与首次推理需要初始化，后续问题复用模型；AI 网络请求的等待不受本地语音 GPU 加速保证。

## 其他电脑的可选运行库

普通安装包不包含 NVIDIA DLL；没有 GPU 的电脑可直接使用 CPU。
脚本只写 `%LOCALAPPDATA%\LookToAsk\gpu`，不修改显卡驱动、系统 PATH、API 设置或主 Python 环境。
需要已安装支持 CUDA 12 的 NVIDIA 驱动，以及一个带 pip 的 Python。源码环境执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_speech_gpu.ps1
```

也可用 `-Python C:\path\to\python.exe` 指定 Python；安装版脚本位于 `_internal/tools/`。
脚本从 PyPI 下载官方 Windows wheels，总下载约 1.26 GB，解压后需要更多磁盘空间。
组件为 cuBLAS 12.8.4.1、cuDNN 9.10.2.21、CUDA Runtime 12.8.90，许可见 [DEPENDENCIES.md](DEPENDENCIES.md)。
它们是 **NVIDIA 专有运行库**；单独安装并保留 wheel 内许可证，不捆绑进项目安装包。
安装后重启程序，状态显示 GPU 才算启用，不能仅凭检测到显卡判定推理成功。

## 本机可复现结果

2026-10-17，Windows 11 / i9-10900K / RTX 3080 Ti 12 GB / 驱动 610.47。
同一 medium 修订 `08e178d48790749d25932bbc082711ddcfdfbc4f`、6 条 Windows Huihui 合成普通话，
中文、beam=5、VAD、每题独立识别；串行比较，预热后计时：

| 项目 | CPU / int8 / 4 线程 | GPU / float16 |
|---|---:|---:|
| 六句各自识别时间 | 3.79–4.12 秒 | 0.25–0.33 秒 |
| 平均单句识别时间 | 3.95 秒 | 0.29 秒 |
| 首次推理（单独测量） | 3.98 秒 | 0.42 秒 |
| 模型加载（缓存已存在） | 2.60 秒 | 1.60 秒 |
| 字符编辑差异 / 90 个参考字 | 1 | 1 |

这组音频约快 13 倍，仍有「作用域 → 作用与」错误，字符差异包含繁简差异。
没有真人录音、真实截图或外部 AI；不代表所有录音都具有相同速度/准确率，也不是完整问答耗时。
其他显卡、显存占用、真人收音需实测；Windows 10、摄像头并行与真人精度未验证。

```powershell
.\.venv\Scripts\python.exe tests/manual/benchmark_speech.py --models medium --devices cpu cuda --beams 5
$env:LOOK_TO_ASK_TEST_CUDA = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

基准只读取 tests 下的合成音频和已缓存模型，不自动录音/下载；CUDA 失败会明确失败，不冒充 GPU 结果。
`--check-speech --speech-device cuda` 只确认模型/VAD 加载，不能替代真实推理测试。

## 普通话收音与错字排查

语言选择中文，优先 medium；旧设置保留，升级后仍需确认所选模型。追求 CPU 速度可使用 small。
Windows 声音设置决定默认输入麦克风；看到录音提示后说完整句，末尾略停再松开。
检查实际转写，不能仅凭 AI 猜对意思判断识别准确。若有错词，记录「原话 → 转写」即可，无需提供私人录音。

内存日志的 `input_rate` 是输入采样率；`rms_dbfs` / `peak_dbfs` 是重采样前的平均/峰值强度；
`full_scale_fraction` 是接近数字满幅的样本比例。平均低于 -45 dBFS 或满幅比例达到 1% 时提示调整收音。
静音也会降低平均强度，不能仅凭数值判断麦克风质量。程序不自动改增益、不替换词语来掩盖识别错误。

实际采集按原生采样率进行，再转换为 16 kHz；先关麦克风再处理。日志只保留这些数值、模型安全标签、语言和时延，
不含音频、转写、私有模型路径、API Key 或截图。`asr_ms` 与 API 等待分开记录。
